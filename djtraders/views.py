from django.db import connection
from django.shortcuts import render


def home(request):
    """
    Landing page for the djtraders app.

    Deliberately simple: no database access at all, just a template
    with a link into the app's other page(s) (currently customer_list).
    As more app features are added, this becomes the natural place to
    link out to them.
    
    # render(request, template_name) is Django's shortcut for building
    # an HttpResponse from a template:
    #   request        -- the incoming HttpRequest; render() needs it
    #                     to run template context processors (e.g. the
    #                     ones listed in settings.py's TEMPLATES
    #                     OPTIONS) and to build the final HttpResponse.
    #   "djtraders/home.html" -- the template path. Django searches
    #                     each app's templates/ folder (APP_DIRS=True
    #                     in settings.py) plus TEMPLATES['DIRS'] until
    #                     it finds a matching file.
    #   (no third argument) -- there's no context dict here because
    #                     this page has no per-request data to show;
    #                     compare to customer_list() below, which
    #                     passes one.
    """
    return render(request, "djtraders/home.html")


def customer_list(request):
    """
    Display a basic list of customers.

    This is a deliberate proof-of-concept: it talks to Postgres with
    raw SQL through Django's database connection, WITHOUT using a
    Django model or the ORM. We're doing it this way on purpose so
    students see what Django is doing "under the hood" before we
    introduce models next week and replace this raw SQL with
    Customer.objects.all().

    Because there's no model, cursor.fetchall() hands back plain
    tuples -- each customer is just (customer_id, company_name,
    contact_name, city, country) in that order, with no named
    attributes. The template will access fields by position
    (customer.0, customer.1, ...). A model-based version wouldn't need
    that -- the ORM would give us Customer objects with named
    attributes for free.
    """
    # Cap how many rows we display so the proof-of-concept page stays
    # short and fast.
    display_limit = 10

    with connection.cursor() as cursor:
        # Select a handful of "basic info" columns rather than every
        # column in the table, since this is just a proof-of-concept
        # display, not a full customer record view. LIMIT keeps the
        # result set to display_limit rows regardless of table size.
        cursor.execute(
            """
            SELECT customer_id, company_name, contact_name, city, country
            FROM customers
            ORDER BY company_name
            LIMIT %s
            """,
            [display_limit],
        )
        customers = cursor.fetchall()

    '''
    # render(request, template_name, context) -- same first two
    # arguments as home()'s render() call above, plus a third:
    #   request        -- the incoming HttpRequest (see home() above).
    #   "djtraders/customer_list.html" -- the template path, found the
    #                     same way as in home() (APP_DIRS=True).
    #   {"customers": customers} -- the context dict. Its keys become
    #                     variable names inside the template, so this
    #                     is what makes {% for customer in customers %}
    #                     work in customer_list.html -- without this
    #                     dict, the template would have no "customers"
    #                     to loop over.
    '''
    return render(request, "djtraders/customer_list.html", {"customers": customers})
