# Django Traders App

A Django application for ISM 672 (Application Design and Programming), built
against the classic Northwind-style "DjangoTraders" PostgreSQL database.

This repository is **Module 0** — the initial project scaffold: models
reverse-engineered from the existing database, a customer list page, and the
shared base template.

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
