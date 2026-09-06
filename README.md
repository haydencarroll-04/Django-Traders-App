# Django Traders App — Module 1

A Django application for ISM 672 (Application Design and Programming), built
against the classic Northwind-style "DjangoTraders" PostgreSQL database.

This branch is **Module 1**, extending the Module 0 scaffold (`main`):

- **Customer search** — added Contact Name and City (free-text, case-insensitive
  partial match) and Contact Title (dropdown, exact match); all three also
  appear as result columns and stay filled in after a search.
- **Product search** — added a Supplier dropdown (exact match) and a Supplier
  company-name column in the results.
- **Product Detail page** — new view, URL, and template: Product Info,
  Supplier, and Revenue cards plus a full order history (each order links to
  its Order Detail page). Product names in the list now link here.
- **UI/UX** — Low Stock / Out of Stock status badges driven by real stock
  levels, and Font Awesome icons on the detail-page cards, extending the
  shared `static/common/css/DjangoTraders.css` design system.

## Running it locally

1. Create and activate a virtual environment, then install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Provide your local database credentials. Copy the example file and edit it:

   ```bash
   cp DjangoTraders/local_settings.example.py DjangoTraders/local_settings.py
   ```

   `local_settings.py` is git-ignored, so your password never gets committed.
   (Alternatively, set the `DJANGO_DB_PASSWORD` / `DJANGO_SECRET_KEY`
   environment variables — `settings.py` reads those as a fallback.)

3. Run the development server:

   ```bash
   python manage.py runserver
   ```

## Notes

- The models use `managed = False` — Django reads the existing database and
  does not migrate it.
- `SECRET_KEY` and database credentials are kept out of version control; see
  `DjangoTraders/local_settings.example.py`.
