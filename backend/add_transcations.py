from backend import db as dbmod
from backend.utils import autocategory, parse_date
from backend import rates


def execute_addition(cursor, date_str, description, amount, category, is_expense):
    """
    amount: expected positive number here; this function will apply negative sign for expenses,
            to keep parity with the rest of the code
    """
    if category == '':
        category = autocategory(description)

    cursor.execute('''
        INSERT INTO expenses (date, description, amount, category, is_expense)
        VALUES (?, ?, ?, ?, ?)
    ''', (date_str, description, amount, category, int(is_expense)))


def create_transaction(date_str, description, amount, category='', is_expense=1, currency=None):
    """
    helper for adding a transaction.
    date_str: '' or something accepted by parse_date()
    amount: positive float
    category: optional
    is_expense: 1 or 0
    currency: 3-letter currency code of the entered amount (if None or same as app main currency, no conversion)
    """
    from flask import current_app

    if date_str == '':
        date_str = parse_date('')
    else:
        # allow both YYYY-MM-DD and other user-friendly formats via parse_date
        try:
            # if already in YYYY-MM-DD format we still pass through parse_date for safety
            date_str = parse_date(date_str)
        except Exception:
            # fallback: keep passed string
            pass

    # ensure numeric amount
    amount_val = abs(float(amount))

    currency = (currency or current_app.config.get('MAIN_CURRENCY', 'EUR')).strip().lower()
    main_ccy = current_app.config.get('MAIN_CURRENCY', 'EUR').strip().lower()

    # convert if needed
    if currency != main_ccy:
        try:
            converted = rates.convert(amount_val, currency, main_ccy, date_str)
        except Exception as e:
            # bubble up the error to caller
            raise RuntimeError(f"Currency conversion failed: {e}")
    else:
        converted = amount_val

    # stored amount: signed according to is_expense
    stored_amount = -abs(converted) if int(is_expense) == 1 else abs(converted)

    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        try:
            execute_addition(cur, date_str, description, stored_amount, category, int(is_expense))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise