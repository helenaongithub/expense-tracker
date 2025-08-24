from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import datetime
import os

from backend import db as dbmod
from backend import categories as catmod 
from backend import add_transcations as add_mod 
from backend import automations as auto_mod
from backend import sync as sync_mod
from backend import utils
from backend import rates

# -------------------------
# app & database setup
# -------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET')
app.config['MAIN_CURRENCY'] = os.environ.get('MAIN_CURRENCY', 'EUR')

# downlaod current database
download_script = os.environ.get('SYNC_DOWNLOAD_SCRIPT')
job = sync_mod.run_sync_job(download_script)

# ensure DB exists and automations run on startup (same as CLI main did)
dbmod.init_db()
catmod.init_categories_db()
auto_mod.init_automations_db()

# run automations once on startup to mirror CLI behaviour
try:
    auto_mod.update_fix_transactions()
except Exception as e:
    # non-fatal, show in logs and continue
    print('Automations update failed on startup:', e)

# -------------------------
# routes
# -------------------------

# ---- main page ----
@app.route('/')
def index():
    time = request.args.get('time', '') # (YYYY, YYYY-MM, YYYY-MM-DD, or 'all')
    order = request.args.get('order', 'date')

    # independent search inputs
    search_id = request.args.get('search_id', '').strip()
    search_amount = request.args.get('search_amount', '').strip()
    search_desc = request.args.get('search_desc', '').strip()
    search_cate = request.args.get('search_cate', '').strip()

    now = datetime.datetime.now()
    year = month = day = None
    total = False

    # --- TIME FILTER ---
    if not time:
        # default: current month
        year, month = now.year, now.month
    elif time.lower() in ('all', '-', 'total'):
        total = True
    else:
        try:
            # try exact date yyyy-mm-dd
            if '-' in time and len(time.split('-')) == 3:
                y, m, d = map(int, time.split('-'))
                year, month, day = y, m, d
            else:
                parts = time.split()
                if len(parts) == 1:
                    p = parts[0]
                    if p.lower() in ('-', 'total'):
                        total = True # total
                    elif p.isdigit():
                        if len(p) == 4:  # year only
                            year = int(p)
                        elif 1 <= len(p) <= 2:  # month only
                            month = int(p)
                            year = now.year
                    elif '-' in p:
                        # yyyy-mm
                        y_m = p.split('-')
                        if len(y_m) == 2:
                            year, month = map(int, y_m)
                elif len(parts) == 2:
                    # day month or month year
                    a, b = parts
                    if len(b) == 4 and b.isdigit():
                        # month year
                        month, year = int(a), int(b)
                    else:
                        # day month
                        day, month = int(a), int(b)
                        year = now.year
                elif len(parts) == 3:
                    # day month year
                    day, month, year = map(int, parts)

            # basic validation
            if month is not None and not 1 <= month <= 12:
                month = now.month
            if day is not None:
                try:
                    datetime.datetime(year, month or 1, day)  # check valid date
                except ValueError:
                    day = None

        except Exception:
            # fallback to current month if parsing fails
            total = False
            year, month, day = now.year, now.month, None



    # --- INDEPENDENT SEARCH ---
    params = []
    addon = ''
    if search_id:
        addon += ' AND id = ?'
        total = True
        year = month = day = None
        params.append(search_id)
    if search_amount:
        addon += ' AND ((amount BETWEEN ? AND ?) OR (amount BETWEEN ? AND ?)) '
        params.extend([float(search_amount) - 1, float(search_amount) + 1, -float(search_amount) - 1, -float(search_amount) + 1])
    if search_desc:
        addon += ' AND description LIKE ?'
        params.append(f'%{search_desc}%')
    if search_cate:
        addon += ' AND category LIKE ?'
        params.append(f'%{search_cate}%')

    # --- VISUALIZATION PARAM ---
    # if user passed a time param use it, otherwise compute the month/year that the index is using
    # ensures the "Visualize current table" button passes an explicit time param
    if time:
        effective_time = time
    else:
        # fallback to the month/year the index is currently showing (use now if None)
        now = datetime.datetime.now()
        eff_year = year or now.year
        eff_month = month or now.month
        effective_time = f"{eff_year}-{eff_month:02d}"

    where_clause, duration = utils.get_where_clause('WHERE 1=1 ', year, month, day, total)
    where_clause += addon

    # --- SORTING ---
    order_value = 'date'
    if order in ('amount', 'category', 'description', 'id'):
        order_value = order

    # --- QUERY ---
    txs = dbmod.query_transactions(where_clause=where_clause, params=tuple(params), order_by=order_value)
    total_amount = dbmod.sum_query(where_clause=where_clause, params=tuple(params))

    # build a case-insensitive mapping name -> emoji for fast lookup in template
    cats = catmod.list_categories_with_ids()
    cat_emoji_map = {}
    for c in cats:
        if c.get('name') is None:
            continue
        cat_emoji_map[c['name'].lower()] = c.get('emoji') or ''

    # pass to template
    return render_template('index.html',
                        transactions=txs,
                        total=round(total_amount, 2),
                        duration=duration,
                        order=order,
                        time=time,
                        search_id=search_id,
                        search_amount=search_amount,
                        search_desc=search_desc,
                        search_cate=search_cate,
                        effective_time=effective_time,
                        cat_emoji_map=cat_emoji_map)

# ---- add transaction ----
@app.route('/add', methods=['GET', 'POST'])
def add():
    today = datetime.date.today()
    today_date = today.strftime('%Y-%m-%d')
    
    errors = {}
    form = {
        'date': '',
        'description': '',
        'amount': '',
        'category': '',
        'is_expense': '1',
        'currency': app.config['MAIN_CURRENCY']
    }

    if request.method == 'POST':
        # collect raw inputs to re-populate the form if validation fails
        form['date'] = request.form.get('date', '').strip()
        form['description'] = request.form.get('description', '').strip()
        form['amount'] = request.form.get('amount', '').strip()
        form['category'] = request.form.get('category', '').strip()
        form['is_expense'] = request.form.get('is_expense', '1')
        form['currency'] = request.form.get('currency', app.config['MAIN_CURRENCY']).strip().lower()


        # validate amount
        try:
            if form['amount'] == '':
                raise ValueError('Amount is required')
            amount = float(form['amount'])
            # UI expects positive number
            if amount <= 0:
                raise ValueError('Amount must be greater than 0')
        except ValueError as e:
            errors['amount'] = str(e)

        # validate date
        try:
            # parse_date returns string YYYY-MM-DD or raises
            parsed_date = form['date'] if utils.validate_form_date(form['date']) else today_date
            form['date'] = parsed_date
        except Exception:
            errors['date'] = 'Invalid date format'

        # validate description
        if form['description'] == '':
            errors['description'] = 'Description is required'

        # validate is_expense
        if form['is_expense'] not in ('0', '1'):
            errors['is_expense'] = 'Invalid type'

        # if errors -> re-render form with error messages
        if errors:
            return render_template('add_edit.html', tx=None, today_date=today_date, errors=errors, form=form)

        # no errors — create transaction
        try:
            add_mod.create_transaction(form['date'], form['description'], amount, form['category'], int(form['is_expense']), form['currency'])
            flash('Transaction added', 'success')
            return redirect(url_for('index'))
        except RuntimeError as e:
            # conversion specific errors
            flash(f'Failed to add transaction: {e}', 'danger')
            errors['general'] = str(e)
            return render_template('add_edit.html', tx=None, today_date=today_date, errors=errors, form=form)
        except Exception as e:
            flash(f'Failed to add transaction: {e}', 'danger')
            # fall through and show form again
            errors['general'] = 'Failed to add transaction'
            return render_template('add_edit.html', tx=None, today_date=today_date, errors=errors, form=form)

    # GET
    return render_template('add_edit.html', tx=None, today_date=today_date, errors=errors, form=form)

# ---- edit transaction ----
@app.route('/edit/<int:tx_id>', methods=['GET', 'POST'])
def edit(tx_id):
    today = datetime.date.today()
    today_date = today.strftime('%Y-%m-%d')

    tx = dbmod.get_transaction(tx_id)
    if not tx:
        flash('Transaction not found', 'danger')
        return redirect(url_for('index'))

    # convert tx row to dict for default form values
    tx_dict = dict(tx)

    main_ccy = app.config.get('MAIN_CURRENCY', 'EUR').strip().lower()
    displayed_amount = abs(float(tx_dict.get('amount', 0)))

    form = {
        'date': tx_dict.get('date', ''),
        'description': tx_dict.get('description', ''),
        'amount': str(displayed_amount),
        'category': tx_dict.get('category', ''),
        'is_expense': str(tx_dict.get('is_expense', 1)),
        'currency': tx_dict.get('currency', app.config['MAIN_CURRENCY'].strip().lower()) 
    }
    errors = {}

    if request.method == 'POST':
        # retrieve the referrer we stored in hidden input (or fallback)
        redirect_url = request.form.get('redirect_url', url_for('index'))

        # get new values
        form['date'] = request.form.get('date', '').strip()
        form['description'] = request.form.get('description', '').strip() or form['description']
        form['amount'] = request.form.get('amount', '').strip()
        form['category'] = request.form.get('category', '').strip() or form['category']
        form['is_expense'] = request.form.get('is_expense', form['is_expense'])
        form['currency'] = request.form.get('currency', app.config['MAIN_CURRENCY']).strip().lower()

        # validate amount
        try:
            if form['amount'] == '':
                # if empty, keep old amount
                amount_val = displayed_amount
            else:
                amount_val = float(form['amount'])
                if amount_val <= 0:
                    raise ValueError('Amount must be greater than 0')
        except ValueError as e:
            errors['amount'] = str(e)

        # validate date
        try:
            parsed_date = form['date'] if utils.validate_form_date(form['date']) else today_date
            form['date'] = parsed_date
        except Exception:
            errors['date'] = 'Invalid date format'

        # validate description
        if form['description'] == '':
            errors['description'] = 'Description is required'

        # validate is_expense
        if form['is_expense'] not in ('0', '1'):
            errors['is_expense'] = 'Invalid type'

        if errors:
            # re-render edit form with errors and previously entered values
            return render_template('add_edit.html', tx=form, errors=errors, redirect_url=request.form.get('redirect_url', url_for('index')))
        
        # convert entered amount to main currency if needed
        try:
            if form['currency'] != main_ccy:
                converted = rates.convert(amount_val, form['currency'], main_ccy, parsed_date)
            else:
                converted = amount_val
        except Exception as e:
            flash(f'Currency conversion failed: {e}', 'danger')
            errors['general'] = f'Currency conversion failed: {e}'
            return render_template('add_edit.html', tx=form, errors=errors, redirect_url=redirect_url, main_ccy=main_ccy)

        # store amount according to convention
        is_exp = True if form['is_expense'] == '1' else False
        stored_amount = -abs(converted) if is_exp else abs(converted)

        with dbmod.get_conn() as conn:
            c = conn.cursor()
            try:
                c.execute("""UPDATE expenses SET date=?, description=?, amount=?, category=?, is_expense=? WHERE id=?""",
                            (form['date'], form['description'], stored_amount, form['category'], 1 if is_exp else 0, tx_id))
                conn.commit()
                flash('Transaction updated', 'success')
                return redirect(redirect_url or url_for('index'))
            except Exception as e:
                flash(f'Failed to update: {e}', 'danger')
                errors['general'] = 'Failed to update transaction'
                return render_template('add_edit.html', tx=form, errors=errors, redirect_url=redirect_url)

    # GET - prefill form; convert Row to dict-like for template
    tx_display = dict(tx)
    tx_display['amount'] = abs(tx_display['amount'])
    return render_template('add_edit.html', tx=tx_display, errors=errors, redirect_url=request.referrer or url_for('index'))

# ---- delete transaction ----
@app.route('/delete/<int:tx_id>', methods=['POST'])
def delete(tx_id):
    try:
        with dbmod.get_conn() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM expenses WHERE id = ?', (tx_id,))
            if c.rowcount == 0:
                flash('No transaction found with that id', 'warning')
            else:
                conn.commit()
                flash('Transaction deleted', 'warning')
    except Exception as e:
        flash(f'Failed to delete: {e}', 'danger')
    return redirect(request.referrer or url_for('index'))


@app.route('/transaction/<int:tx_id>')
def transaction(tx_id):
    tx = dbmod.get_transaction(tx_id)
    if not tx:
        flash('Transaction not found', 'danger')
        return redirect(url_for('index'))
    txd = dict(tx)
    txd['amount'] = abs(txd['amount'])
    return render_template('add_edit.html', tx=txd, view_only=True)

# ---- automations ----
@app.route('/automations', methods=['GET', 'POST'])
def automations_view():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            auto_mod.add_automation(
                request.form['day'],
                request.form['description'],
                request.form['amount'],
                request.form.get('category', ''),
                request.form.get('is_expense', '1'),
                request.form.get('start', ''),
                request.form.get('end', '')
            )
            flash('Automation added', 'success')
        elif action == 'run':
            auto_mod.update_fix_transactions()
            flash('Automations executed', 'success')
        return redirect(url_for('automations_view'))

    automations = auto_mod.list_automations()
    return render_template('automations.html', automations=automations)

@app.route('/automations/delete/<int:aid>', methods=['POST'])
def automation_delete(aid):
    if auto_mod.delete_automation(aid):
        flash('Automation deleted', 'success')
    else:
        flash('Automation not found', 'danger')
    return redirect(url_for('automations_view'))

@app.route('/automations/edit/<int:aid>', methods=['GET', 'POST'])
def automation_edit(aid):
    automation = auto_mod.get_automation_by_id(aid)
    if not automation:
        flash('Automation not found', 'danger')
        return redirect(url_for('automations_view'))

    if request.method == 'POST':
        new_data = {
            'day': request.form['day'],
            'description': request.form['description'],
            'amount': request.form['amount'],
            'category': request.form.get('category', ''),
            'is_expense': request.form.get('is_expense', '1'),
            'start': request.form.get('start', ''),
            'end': request.form.get('end', '')
        }
        auto_mod.update_automation(aid, new_data)
        flash('Automation updated', 'success')
        return redirect(url_for('automations_view'))

    return render_template('automation_edit.html', automation=automation, aid=aid)

# ---- categories ----
@app.route('/categories')
def categories():
    cats = catmod.list_categories_with_ids()
    return render_template('categories.html', categories=cats)

@app.route('/categories/add', methods=['POST'])
def add_category():
    name = request.form.get('name','').strip()
    emoji = request.form.get('emoji', '').strip() or None
    if not name:
        flash('Category name required', 'warning')
        return redirect(url_for('categories'))
    catmod.add_category(name, emoji)
    flash('Category added', 'success')
    return redirect(url_for('categories'))

@app.route('/categories/<int:cat_id>/edit', methods=['POST'])
def edit_category(cat_id):
    new_name = request.form.get('name','').strip()
    new_emoji = request.form.get('emoji','').strip() or None
    if not new_name:
        flash('Name required', 'warning')
        return redirect(url_for('categories'))
    ok = catmod.update_category_name(cat_id, new_name, new_emoji)
    flash('Category updated' if ok else 'Update failed', 'success' if ok else 'danger')
    return redirect(url_for('categories'))

@app.route('/categories/<int:cat_id>/delete', methods=['POST'])
def delete_category(cat_id):
    ok = catmod.delete_category(cat_id)
    flash('Category deleted' if ok else 'Delete failed', 'success' if ok else 'danger')
    return redirect(url_for('categories'))

@app.route('/categories/<int:cat_id>/keywords/add', methods=['POST'])
def add_keyword(cat_id):
    kw = request.form.get('keyword','').strip()
    if not kw:
        flash('Keyword required', 'warning')
    else:
        catmod.add_keyword(cat_id, kw)
        flash('Keyword added', 'success')
    return redirect(url_for('categories'))

@app.route('/categories/keywords/<int:kw_id>/delete', methods=['POST'])
def delete_keyword(kw_id):
    ok = catmod.delete_keyword(kw_id)
    flash('Keyword removed' if ok else 'Keyword delete failed', 'success' if ok else 'danger')
    return redirect(url_for('categories'))

# ---- dashboard ----
def _parse_time_from_arg(time_str, default_total_if_empty=False):
    """
    parse the `time` query param into (year, month, day, total).
    if default_total_if_empty, an empty time string means 'all time' (total=True).
    otherwise empty means current month, to match index page behaviour
    """
    now = datetime.datetime.now()
    year = month = day = None
    total = False

    if not time_str:
        # dashboard shows all data by default, index wants current month.
        if default_total_if_empty:
            return None, None, None, True
        return now.year, now.month, None, False

    ts = time_str.strip()
    if ts.lower() in ('all', '-', 'total'):
        return None, None, None, True

    # full date yyyy-mm-dd
    if '-' in ts and len(ts.split('-')) == 3:
        try:
            y, m, d = map(int, ts.split('-'))
            return y, m, d, False
        except Exception:
            pass

    parts = ts.split()
    try:
        if len(parts) == 1:
            p = parts[0]
            if p.lower() in ('-', 'total'):
                total = True
            elif p.isdigit():
                if len(p) == 4:
                    year = int(p)
                elif 1 <= len(p) <= 2:
                    month = int(p)
                    year = now.year
            elif '-' in p:
                y_m = p.split('-')
                if len(y_m) == 2 and y_m[0].isdigit() and y_m[1].isdigit():
                    year, month = map(int, y_m)
        elif len(parts) == 2:
            a, b = parts
            if len(b) == 4 and b.isdigit():
                month, year = int(a), int(b)
            else:
                day, month = int(a), int(b)
                year = now.year
        elif len(parts) == 3:
            day, month, year = map(int, parts)
    except Exception:
        year, month, day = now.year, now.month, None
        total = False

    # sanitize
    if month is not None and not (1 <= month <= 12):
        month = now.month
    if day is not None:
        try:
            datetime(year or now.year, month or 1, day)
        except Exception:
            day = None

    return year, month, day, total


def _build_where_and_params_from_request(default_total_if_empty=False):
    """
    build SQL WHERE clause + params tuple from request args
    default_total_if_empty: if True, an empty time param becomes 'all time' for the dashboard.
    """
    time = request.args.get('time', '')
    search_id = request.args.get('search_id', '').strip()
    search_amount = request.args.get('search_amount', '').strip()
    search_desc = request.args.get('search_desc', '').strip()
    search_cate = request.args.get('search_cate', '').strip()

    year, month, day, total = _parse_time_from_arg(time, default_total_if_empty=default_total_if_empty)

    where_clause, duration = utils.get_where_clause('WHERE 1=1 ', year, month, day, total)

    params = []

    # if search_id present, ignore time filter and look up exact id
    if search_id:
        where_clause = 'WHERE id = ?'
        params.append(int(search_id))
        # if searching by id we intentionally ignore other search fields
        return where_clause, tuple(params), duration

    # for amount: use absolute value to match both positive and negative stored amounts
    if search_amount:
        try:
            amt_val = float(search_amount)
            where_clause += ' AND ABS(amount) = ?'
            params.append(amt_val)
        except ValueError:
            # ignore invalid amount on server side (no match)
            where_clause += ' AND 0 = 1'  # force empty result set
    if search_desc:
        where_clause += ' AND description LIKE ?'
        params.append(f'%{search_desc}%')
    if search_cate:
        where_clause += ' AND category LIKE ?'
        params.append(f'%{search_cate}%')

    return where_clause, tuple(params), duration

@app.route('/dashboard')
def dashboard():
    # the template will fetch /dashboard/data (and pass the query string)
    return render_template('dashboard.html')

@app.route('/dashboard/data')
def dashboard_data():
    # read time param raw to decide view granularity
    time = request.args.get('time', '')
    year, month, day, total = _parse_time_from_arg(time, default_total_if_empty=True)

    # build where clause & params (dashboard wants all-time default)
    where_clause, params, duration = _build_where_and_params_from_request(default_total_if_empty=True)

    # always limit visuals to expenses (keep behaviour consistent)
    where_expense = where_clause + ' AND is_expense = 1'

    with dbmod.get_conn() as conn:
        cur = conn.cursor()

        # if user requested an exact day -> DAILY view: return individual transactions
        if day is not None:
            # where_clause already restricts by that day via get_where_clause
            q = f'SELECT id, date, description, amount, category FROM expenses {where_expense} ORDER BY date, id'
            cur.execute(q, params)
            rows = cur.fetchall()
            transactions = []
            for r in rows:
                transactions.append({
                    'id': r['id'],
                    'date': r['date'],
                    'description': r['description'],
                    'amount': round(abs(float(r['amount'] or 0.0)), 2),
                    'category': r['category'] or ''
                })

            # category distribution for the day
            q_cats = f"""
                SELECT COALESCE(category, '(none)') AS category, -SUM(amount) AS total
                FROM expenses
                {where_expense}
                GROUP BY category
                ORDER BY total DESC
                LIMIT 50
            """
            cur.execute(q_cats, params)
            cat_rows = cur.fetchall()
            categories = [{'category': r['category'], 'total': round(float(r['total'] or 0.0), 2)} for r in cat_rows]

            empty = (len(transactions) == 0 and len(categories) == 0)
            return jsonify({
                'view': 'daily',
                'duration': duration,
                'transactions': transactions,
                'categories': categories,
                'empty': empty
            })

        # if user requested a month -> show daily totals for that month
        if month is not None and year is not None and not total:
            q_days = f"""
                SELECT strftime('%Y-%m-%d', date) AS day, -SUM(amount) AS total
                FROM expenses
                {where_expense}
                GROUP BY day
                ORDER BY day
            """
            cur.execute(q_days, params)
            day_rows = cur.fetchall()
            labels = [r['day'] for r in day_rows]
            totals = [round(float(r['total'] or 0.0), 2) for r in day_rows]

            # categories for that month
            q_cats = f"""
                SELECT COALESCE(category, '(none)') AS category, -SUM(amount) AS total
                FROM expenses
                {where_expense}
                GROUP BY category
                ORDER BY total DESC
                LIMIT 50
            """
            cur.execute(q_cats, params)
            cat_rows = cur.fetchall()
            categories = [{'category': r['category'], 'total': round(float(r['total'] or 0.0), 2)} for r in cat_rows]

            empty = (len(labels) == 0 and len(categories) == 0)
            return jsonify({
                'view': 'monthly_by_day',
                'duration': duration,
                'labels': labels,
                'values': totals,
                'categories': categories,
                'empty': empty
            })

        # otherwise: year-only or all-time -> monthly grouping
        q_months = f"""
            SELECT strftime('%Y-%m', date) AS ym, -SUM(amount) AS total
            FROM expenses
            {where_expense}
            GROUP BY ym
            ORDER BY ym
        """
        cur.execute(q_months, params)
        month_rows = cur.fetchall()
        months = [r['ym'] for r in month_rows]
        month_totals = [round(float(r['total'] or 0.0), 2) for r in month_rows]

        # category distribution for the same filter
        q_cats = f"""
            SELECT COALESCE(category, '(none)') AS category, -SUM(amount) AS total
            FROM expenses
            {where_expense}
            GROUP BY category
            ORDER BY total DESC
            LIMIT 50
        """
        cur.execute(q_cats, params)
        cat_rows = cur.fetchall()
        categories = [{'category': r['category'], 'total': round(float(r['total'] or 0.0), 2)} for r in cat_rows]

    empty = (len(months) == 0 and len(categories) == 0)
    return jsonify({
        'view': 'monthly',
        'duration': duration,
        'months': months,
        'month_totals': month_totals,
        'categories': categories,
        'empty': empty
    })

# ---- sync ----
@app.route('/sync_data', methods=['POST'])
def sync_data():
    script = os.environ.get('SYNC_UPLOAD_SCRIPT')
    if not script:
        return jsonify({'ok': False, 'error': 'SYNC_UPLOAD_SCRIPT not set'}), 500

    try:
        job = sync_mod.start_sync_job(script)
    except FileNotFoundError as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

    # return job id & pid
    return jsonify({'ok': True, 'job_id': job['job_id'], 'pid': job['pid'], 'log_url': url_for('sync_log', job_id=job['job_id'])}), 200


@app.route('/sync_status/<job_id>')
def sync_status(job_id):
    job = sync_mod.get_job(job_id)
    if not job:
        return jsonify({'ok': False, 'error': 'job not found'}), 404
    return jsonify({'ok': True, 'running': job['running'], 'pid': job['pid'], 'started_at': job['started_at'], 'returncode': job['returncode'], 'error': job.get('error')})

@app.route('/sync_log/<job_id>')
def sync_log(job_id):
    res = sync_mod.tail_log(job_id)
    if res is None:
        return jsonify({'ok': False, 'error': 'job not found'}), 404
    return jsonify(res)

if __name__ == '__main__':
    app.run(debug=False)