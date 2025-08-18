import sqlite3
from os import makedirs
from os.path import join, dirname, exists
from contextlib import contextmanager

# -------------------------
# setup database
# -------------------------
DATA_DIR = 'data'
DB_PATH = join(DATA_DIR, 'expenses_tracker.db')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY,
    date TEXT,
    description TEXT,
    amount REAL,
    category TEXT,
    is_expense INTEGER
);
'''

# indexes for faster queries
INDEXES = [
    'CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);',
    'CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);',
    'CREATE INDEX IF NOT EXISTS idx_expenses_amount ON expenses(amount);'
]

def ensure_data_dir():
    if not exists(DATA_DIR):
        makedirs(DATA_DIR, exist_ok=True)

@contextmanager
def get_conn():
    """
    use as `with get_conn() as conn: cur = conn.cursor(); ...`
    """
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    # enable foreign keys
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """create schema and indexes, safe to call on startup"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executescript(SCHEMA)
        for idx_sql in INDEXES:
            cur.execute(idx_sql)
        conn.commit()

# -------------------------
# CRUD helpers
# -------------------------
def insert_transaction(date, description, amount, category, is_expense=1):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO expenses (date, description, amount, category, is_expense) VALUES (?, ?, ?, ?, ?)',
            (date, description, amount, category, is_expense)
        )
        conn.commit()
        return cur.lastrowid

def update_transaction(tx_id, date, description, amount, category, is_expense):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            'UPDATE expenses SET date=?, description=?, amount=?, category=?, is_expense=? WHERE id=?',
            (date, description, amount, category, is_expense, tx_id)
        )
        conn.commit()

def delete_transaction(tx_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM expenses WHERE id=?', (tx_id,))
        conn.commit()
        return cur.rowcount

def get_transaction(tx_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM expenses WHERE id=?', (tx_id,))
        return cur.fetchone()
    
# safe query helper: whitelist order_by column names
_VALID_ORDER_COLUMNS = {'date','amount','description','category','id'}

def query_transactions(where_clause='', params=(), order_by='date'):
    if order_by not in _VALID_ORDER_COLUMNS:
        order_by = 'date'
    direction = 'DESC' if order_by == 'date' else 'ASC'
    q = 'SELECT * FROM expenses ' + (where_clause or '') + f' ORDER BY {order_by} {direction}'
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(q, params)
        return cur.fetchall()

def sum_query(where_clause='', params=()):
    q = 'SELECT SUM(amount) as total FROM expenses ' + (where_clause or '')
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(q, params)
        row = cur.fetchone()
    return row['total'] if row and row['total'] is not None else 0.0