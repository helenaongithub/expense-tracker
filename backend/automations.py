from datetime import datetime
from dateutil.relativedelta import relativedelta

from backend import db as dbmod
from backend.add_transcations import execute_addition
from backend.utils import autocategory, safe_date

# -------------------------
# database
# -------------------------

def init_automations_db():
    """create automations table (safe to call multiple times)"""
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS automations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day INTEGER NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT,
            is_expense INTEGER NOT NULL DEFAULT 1,
            start DATE,
            end DATE
        );
        """)
        conn.commit()

# -------------------------
# CRUD helpers
# -------------------------
def check_for_end_day(end_date_str):
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    current_date = datetime.now()
    if end_date > current_date:
        return current_date.strftime('%Y-%m-%d')
    return end_date_str

def list_automations():
    """return list of dicts"""
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id, day, description, amount, category, is_expense, start, end FROM automations ORDER BY id')
        rows = cur.fetchall()

    out = []
    for r in rows:
        out.append({
            'id': r['id'],
            'day': str(r['day']) if r['day'] is not None else '',
            'description': r['description'] or '',
            'amount': str(r['amount']) if r['amount'] is not None else '',
            'category': r['category'] or '',
            'is_expense': str(r['is_expense']),
            'start': r['start'] or '',
            'end': r['end'] or ''
        })
    return out

def get_automation_by_id(aid):
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id, day, description, amount, category, is_expense, start, end FROM automations WHERE id = ?', (aid,))
        r = cur.fetchone()
    return dict(r) if r else None

def add_automation(day, description, amount, category, is_expense, start, end):
    """
    insert an automation row. amount (positive), is_expense 1/0
    returns the new id
    """
    if day == '' or description == '' or amount == '':
        raise ValueError('day, description and amount are required')

    # coerce types
    try:
        day_i = int(day)
    except Exception:
        raise ValueError('day must be an integer (1-31)')
    try:
        amount_f = float(amount)
    except Exception:
        raise ValueError('amount must be numeric')

    is_exp = 1 if str(is_expense) == '1' else 0

    # normalize end date
    end_checked_str = None
    if end:
        try:
            end_dt = datetime.strptime(end, '%Y-%m-%d')
            end_checked_str = end_dt.strftime('%Y-%m-%d')
        except Exception:
            raise ValueError('end must be YYYY-MM-DD')

    # validate start date
    start_str = None
    if start:
        try:
            sd = datetime.strptime(start, '%Y-%m-%d')
            start_str = sd.strftime('%Y-%m-%d')
        except Exception:
            raise ValueError('start must be YYYY-MM-DD')

    if category == '':
        category = autocategory(description)

    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO automations (day, description, amount, category, is_expense, start, end)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (day_i, description, amount_f, category or '', is_exp, start_str, end_checked_str))
        conn.commit()
        return cur.lastrowid

def update_automation(aid, new_data):
    """
    update automation by id, new_data is dict with same keys as add,
    returns True if row updated
    """
    existing = get_automation_by_id(aid)
    if not existing:
        return False

    day = int(new_data.get('day', existing['day']))
    description = new_data.get('description', existing['description'])
    amount = float(new_data.get('amount', existing['amount']))
    category = new_data.get('category', existing['category'])
    is_expense = 1 if str(new_data.get('is_expense', existing['is_expense'])) == '1' else 0
    start = new_data.get('start', existing['start']) or None
    end = new_data.get('end', existing['end']) or None

    start_val = None
    if start:
        try:
            _ = datetime.strptime(start, '%Y-%m-%d')
            start_val = start
        except Exception:
            raise ValueError('start must be YYYY-MM-DD')

    end_val = None
    if end:
        try:
            end_dt = datetime.strptime(end, '%Y-%m-%d')
            # do not force-cap end to today here unless you intend to
            end_val = end_dt.strftime('%Y-%m-%d')
        except Exception:
            raise ValueError('end must be YYYY-MM-DD')

    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
           UPDATE automations
           SET day=?, description=?, amount=?, category=?, is_expense=?, start=?, end=?
           WHERE id=?
        """, (day, description, amount, category or '', is_expense, start_val, end_val, aid))
        conn.commit()
        return cur.rowcount > 0

def delete_automation(aid):
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM automations WHERE id = ?', (aid,))
        conn.commit()
        return cur.rowcount > 0

def update_fix_transactions():
    """
    read automations from DB and add missing monthly entries into expenses
    """
    # read automations first
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT day, description, amount, category, is_expense, start, end FROM automations')
        rows = cur.fetchall()

    if not rows:
        return

    # use same DB for expense insertion (commit once at the end)
    with dbmod.get_conn() as conn_exp:
        cexp = conn_exp.cursor()
        for r in rows:
            day_str = str(r['day'])
            # validate day is integer in sensible range
            try:
                day_i = int(day_str)
                if not (1 <= day_i <= 31):
                    # invalid day-of-month, skip
                    continue
            except Exception:
                continue

            
            description = r['description']
            amount = r['amount']
            category = r['category']
            is_expense = r['is_expense']
            start = r['start']
            end = r['end']

            # parse start date
            try:
                start_date = datetime.strptime(str(start), '%Y-%m-%d')
            except Exception:
                # invalid start format -> skip this automation
                # happends
                continue

             # parse end date if provided, otherwise default to today
            if end and str(end).strip() != '':
                try:
                    end_date = datetime.strptime(str(end), '%Y-%m-%d')
                except Exception:
                    # invalid end format -> skip
                    continue
            else:
                end_date = datetime.now()

            # logical check: end must be >= start
            if end_date < start_date:
                # skip invalid automation
                continue

            # find first candidate date >= start_date
            year = start_date.year
            month = start_date.month
            first_candidate = None

            while True:
                if datetime(year, month, 1) > end_date:
                    break

                candidate = safe_date(year, month, day_i)

                if candidate >= start_date:
                    first_candidate = candidate
                    break
                else:
                    next_month = (datetime(year, month, 1) + relativedelta(months=1))
                    year, month = next_month.year, next_month.month

            if first_candidate is None:
                continue

            # iterate month-by-month from first_candidate to end_date
            current_date = first_candidate
            while current_date <= end_date:
                current_date_str = current_date.strftime('%Y-%m-%d')

                # avoid duplicates: same date + same category + same description
                cexp.execute(
                    'SELECT 1 FROM expenses WHERE date = ? AND category = ? AND description = ?',
                    (current_date_str, category, description)
                )
                existing_entry = cexp.fetchone()
                if not existing_entry:
                    execute_addition(cexp, current_date_str, description, float(amount), category, int(is_expense))

                # move to next month using safe_date
                next_month = (current_date.replace(day=1) + relativedelta(months=1))
                current_date = safe_date(next_month.year, next_month.month, day_i)

        # commit all inserted transactions
        conn_exp.commit()