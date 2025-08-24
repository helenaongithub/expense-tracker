from typing import Dict, List
from backend import db as dbmod

# -------------------------
# database
# -------------------------
def init_categories_db():
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          emoji TEXT DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS category_keywords (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          category_id INTEGER NOT NULL,
          keyword TEXT NOT NULL,
          FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        );
        """)
        conn.commit()

# -------------------------
# CRUD helpers
# -------------------------
def get_categories_dict() -> Dict[str, List[str]]:
    """return a dict: {category_name: [keyword, ...], ...}"""
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.id, c.name, k.keyword
            FROM categories c
            LEFT JOIN category_keywords k ON k.category_id = c.id
            ORDER BY c.name, k.keyword
        """)
        rows = cur.fetchall()

    cats = {}
    for r in rows:
        name = r['name']
        cats.setdefault(name, [])
        if r['keyword'] is not None:
            cats[name].append(r['keyword'])
    return cats

def list_categories_with_ids():
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id, name, emoji FROM categories ORDER BY name')
        cats = []
        for c in cur.fetchall():
            cur.execute('SELECT id, keyword FROM category_keywords WHERE category_id = ? ORDER BY keyword', (c['id'],))
            keywords = [{'id': k['id'], 'keyword': k['keyword']} for k in cur.fetchall()]
            cats.append({'id': c['id'], 'name': c['name'], 'emoji': c['emoji'], 'keywords': keywords})
    return cats

def add_category(name: str, emoji: str = None):
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute('INSERT OR IGNORE INTO categories (name, emoji) VALUES (?, ?)', (name, emoji))
        conn.commit()
        cur.execute('SELECT id FROM categories WHERE name = ?', (name,))
        row = cur.fetchone()
        return row['id'] if row else None

def update_category_name(cat_id: int, new_name: str, new_emoji: str = None):
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        # get old name first
        cur.execute('SELECT name FROM categories WHERE id = ?', (cat_id,))
        row = cur.fetchone()
        if not row:
            return False
        old_name = row[0]

        # update categories table (name + optional emoji)
        if new_emoji is None:
            cur.execute('UPDATE categories SET name = ? WHERE id = ?', (new_name, cat_id))
        else:
            cur.execute('UPDATE categories SET name = ?, emoji = ? WHERE id = ?', (new_name, new_emoji, cat_id))
        updated = cur.rowcount > 0

        # update all existing transactions for the name change
        cur.execute('UPDATE expenses SET category = ? WHERE category = ?', (new_name, old_name))
        conn.commit()
        return updated

def delete_category(cat_id: int):
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM categories WHERE id = ?', (cat_id,))
        conn.commit()
        return cur.rowcount > 0

def add_keyword(category_id: int, keyword: str):
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute('INSERT INTO category_keywords (category_id, keyword) VALUES (?, ?)', (category_id, keyword))
        conn.commit()
        return cur.lastrowid

def delete_keyword(keyword_id: int):
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM category_keywords WHERE id = ?', (keyword_id,))
        conn.commit()
        return cur.rowcount > 0

def find_category_by_name(name: str):
    with dbmod.get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id, name FROM categories WHERE name = ?', (name,))
        return cur.fetchone()