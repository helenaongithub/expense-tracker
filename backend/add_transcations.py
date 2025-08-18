from backend import db as dbmod
from backend.utils import autocategory, parse_date

def execute_addition(cursor, date_str, description, amount, category, is_expense):
    """
    amount: expected positive number here; this function will apply negative sign for expenses,
            to keep parity with the rest of your code
    """
    if category == '':
        category = autocategory(description)

    amount = -abs(amount) if int(is_expense) == 1 else abs(amount)

    cursor.execute('''
        INSERT INTO expenses (date, description, amount, category, is_expense)
        VALUES (?, ?, ?, ?, ?)
    ''', (date_str, description, amount, category, int(is_expense)))


def create_transaction(date_str, description, amount, category='', is_expense=1):
    """
    helper for adding a transaction.
    date_str: '' or something accepted by parse_date()
    amount: positive float
    category: optional
    is_expense: 1 or 0
    """
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

    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        try:
            execute_addition(cur, date_str, description, amount_val, category, int(is_expense))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise