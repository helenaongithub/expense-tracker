# Expenses Tracker — Web (Flask)

A simple personal expenses tracker.
Tracks transactions (expenses & income), categories and recurring automations (fixed monthly transactions). Includes search, time filters, sorting, category management and a visualization dashboard.

## Quick overview

* Backend: Python + Flask + SQLite
* Frontend: Bootstrap + Jinja templates + Chart.js for visualizations
* Data:

  * Transactions in `data/expenses_tracker.db` (table `expenses`)
  * Categories + keywords stored in DB (`categories`, `category_keywords`)
  * Automations stored in DB (`automations`)

## Features

* Add / Edit / Delete transactions
* Time filter (day / month / year / all) and independent searches (id, amount, description, category)
* Sorting by date / amount / description / index
* Category management (create, rename, delete, add/remove keywords)
* Automations (monthly recurring transactions)
* Visualization dashboard: monthly/daily trends + pie chart by category
* Basic client-side and server-side validation for forms
* Sync helper so that user-provided sync scripts can be executed
* Currency exchange to main currency

## Quickstart — run locally

1. **Clone**

```bash
git clone https://github.com/<your-username>/expenses-tracker-web.git
cd expenses-tracker-web
```

2. **Create a virtualenv & install**

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows Powershell

pip install -r requirements.txt
```

3. **Environment / secret key**

Create a `.env` file (do **not** commit this file). A template can be viewed in .env.template. Thre you set the flask secret, the sync upload and download scripts and the main currency.

Copy `.env.template` to `.env` and edit values before starting the app.
Adding sync scripts is only optional. The expense tracker can run only locally.

4. **Init DB**

The app calls the DB init helper on startup automatically, but you can run it manually:

```bash
python -c "from backend.db import init_db; init_db()"
python -c "from backend.categories import init_categories_db; init_categories_db()"
python -c "from backend.automations import init_automations_db; init_automations_db()"
```

5. **Run**

You can run the app directly:

```bash
python app.py
```

or with Flask CLI:

```bash
export FLASK_APP=app.py
export FLASK_ENV=development
flask run
```

Then open: `http://127.0.0.1:5000/`

## Routes / UI

* `/` — Main transactions listing, filtering, sorting, search
* `/add` — Add a transaction
* `/edit/<id>` — Edit transaction
* `/delete/<id>` — POST to delete
* `/transaction/<id>` — View-only transaction details
* `/categories` — Manage categories & keywords
* `/automations` — Manage monthly automations
* `/visualization` — Dashboard for charts
* `/dashboard/data` — JSON endpoint used by charts

## Open To-Dos

* unit tests (pytest) for core helpers (date parsing, category logic, add/edit/delete)
* schedule daily automations (APScheduler or system cron)
* Dockerfile / docker-compose for easier local deployment
* introduce import/export UX (XLSX, CSV import pages + mapping)
* improve accessibility, keyboard navigation, and mobile layout
* add pagination for the transactions list
* split expenses application, sharable