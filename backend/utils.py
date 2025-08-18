import re
import calendar
from datetime import datetime
from backend.categories import get_categories_dict

def autocategory(description):
    """if description has an assigned category, the category is returned, else other"""
    categories_dict = get_categories_dict()
    for category, keywords in categories_dict.items():
        if description in keywords:
            return category
    return 'other'

def parse_date(date_obj, stri=True):
    if date_obj == '':
        date_obj = datetime.now()
    elif len(date_obj.split(' ')) == 1:
        day = int(date_obj)
        date_obj = datetime(datetime.now().year, datetime.now().month, day)
    elif len(date_obj.split(' ')) == 2:
        day, month = date_obj.split(' ')
        date_obj = datetime(datetime.now().year, int(month), int(day))
    elif len(date_obj.split()) == 3:
        day, month, year = date_obj.split(' ')
        date_obj = datetime(int(year), int(month), int(day))
        
    if stri:
        return date_obj.strftime('%Y-%m-%d')
    else:
        return date_obj
    
def validate_form_date(date_str):
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    return date_pattern.match(date_str)

def get_where_clause(where_clause, year=None, month=None, day=None, total=False):
    duration = ''

    if day is not None:
        where_clause += f"AND strftime('%d', date) = '{day:02}'"
        duration = str(day) + ' '
    if month is not None:
        where_clause += f"AND strftime('%m', date) = '{month:02}'"
        duration += calendar.month_name[month] + ' '
    if year is not None:
        where_clause += f"AND strftime('%Y', date) = '{year}'"
        duration += str(year)
    else:
        duration += str(datetime.now().year)
            
    duration = 'total duration' if total else duration

    return where_clause, duration

def safe_date(year, month, day):
    """return a valid date. If day > last day of month, use last day of month."""
    last_day = calendar.monthrange(year, month)[1]  # e.g. (2, 2025) -> 28
    return datetime(year, month, min(day, last_day))