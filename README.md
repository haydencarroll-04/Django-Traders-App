# Django Traders App — Module 2

A Django application for ISM 672 (Application Design and Programming), built
against the classic Northwind-style "DjangoTraders" PostgreSQL database.

This branch is **Module 2**. It keeps every Module 1 customization and layers
the Module 2 features on top:

- **Logins** — separate employee login (pick a name; PIN is the birth year)
  and customer login (pick a company; password from the `customers` table),
  built on plain sessions rather than `django.contrib.auth`. The navbar shows
  who is logged in, and the project home page offers "start a new session".
- **Self-service access** — a logged-in customer only sees their own record;
  employees can view and act on any customer.
- **Customer edit / create / deactivate** — a crispy-forms `ModelForm` edit
  page with browser, server, and jQuery validation, employee-only "New
  Customer" with a generated 5-letter ID, and a soft delete that sets
  `inactive_date`.
- **Employee detail page** — landing page after an employee logs in.
- **Ordering** — a session-backed shopping cart with AJAX "Add to Cart",
  committed as one `Order` plus its `OrderDetail` rows in a single
  transaction. Same-day orders can be cancelled.
- **Order detail** — Shipping Info card, Supplier column, and product names
  linking to the Module 1 Product Detail page.

### Module 1 (carried forward)

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

   Module 2 adds `django-crispy-forms` and `crispy-bootstrap5` to
   `requirements.txt`, so re-run `pip install` if you are upgrading an
   existing Module 1 environment.

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
