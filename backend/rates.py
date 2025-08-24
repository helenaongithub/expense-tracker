import json
import time
from pathlib import Path
import requests

CACHE_PATH = Path('data/rates_cache.json')
CACHE_TTL = 24 * 3600 # 1 day
JSDELIVR = 'https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{date}/v1/currencies/{base}.min.json'
PAGES_DEV = 'https://{date}.currency-api.pages.dev/v1/currencies/{base}.json'

# using https://github.com/fawazahmed0/exchange-api

def _load_cache():
    try:
        return json.loads(CACHE_PATH.read_text())
    except:
        return {}


def _save_cache(obj):
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(obj), encoding='utf-8')
    except Exception:
        pass

def get_rates_for(base, date_str):
    base = base.strip().lower()
    now = time.time()
    cache = _load_cache()

    entry = cache.get(base, {})
    if entry and now - entry.get('ts', 0) < CACHE_TTL and entry.get('date', '') == date_str:
        return entry['rates']

    cnt = 0
    for url in [JSDELIVR, PAGES_DEV]:
        try:
            r = requests.get(url.format(base=base, date=date_str), timeout=5)
            r.raise_for_status()
            data = r.json()
            rates = data.get(base.lower())
            if not rates:
                # for some versions rates may be directly under 'rates' key
                rates = data.get('rates')
            if rates:
                cache[base] = {'rates': rates, 'ts': now, 'date' : date_str}
                _save_cache(cache)
                return rates
        except Exception:
            cnt += 1
            if cnt >= 2:
                break

    if entry:
        return entry['rates']
    raise RuntimeError('Failed to fetch rates for ' + base)

def convert(amount, from_ccy, to_ccy, date_str):
    from_ccy = from_ccy.strip().lower()
    to_ccy = to_ccy.strip().lower()

    if from_ccy.upper() == to_ccy:
        return amount

    rates = get_rates_for(from_ccy, date_str)
    rate = rates.get(to_ccy)
    if rate is None:
        raise RuntimeError(f'No rate {from_ccy}->{to_ccy}')
    return round(amount * rate, 2)