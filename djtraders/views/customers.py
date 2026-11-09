"""
Customer pages: the list, the detail page and its three tabs, edit / create /
deactivate / reactivate, self-signup, and the customer login.

A logged-in customer may only see and edit their own record (and build their own
cart); an employee may act on any customer's (see access.py).
"""

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..forms import CustomerEditForm, CustomerSignupForm
from ..models import Customer
from .access import customer_access_denied, customer_tab_denied, own_customer_redirect


def customer_list(request):
    """
    The customer list, searchable by company name, contact name, contact title,
    city and country. The five search values come from GET parameters ("" when
    not submitted) and Customer.search (models.py) turns them into the filter.
    Choosing a country narrows the city dropdown to that country's cities.

    A logged-in customer is sent straight to their own page instead
    (own_customer_redirect); employees and visitors see the full list.
    """
    redirect_response = own_customer_redirect(request, customer_id=None)
    if redirect_response:
        return redirect_response

    search_company_name = request.GET.get("company_name", "")
    search_contact_name = request.GET.get("contact_name", "")
    search_contact_title = request.GET.get("contact_title", "")
    search_city = request.GET.get("city", "")
    search_country = request.GET.get("country", "")

    # The dropdowns list the distinct, non-blank values on record.
    # Cities are narrowed to the selected country, if there is one.
    cities_queryset = Customer.objects.exclude(city__isnull=True).exclude(city__exact="")
    if search_country:
        cities_queryset = cities_queryset.filter(country=search_country)
    cities = cities_queryset.order_by("city").values_list("city", flat=True).distinct()

    countries = (
        Customer.objects.exclude(country__isnull=True)
        .exclude(country__exact="")
        .order_by("country")
        .values_list("country", flat=True)
        .distinct()
    )

    contact_titles = (
        Customer.objects.exclude(contact_title__isnull=True)
        .exclude(contact_title__exact="")
        .order_by("contact_title")
        .values_list("contact_title", flat=True)
        .distinct()
    )

    # A city left over from a different country would match nothing, so drop it.
    if search_city and search_city not in cities:
        search_city = ""

    customers = Customer.search(
        company_name=search_company_name,
        contact_name=search_contact_name,
        contact_title=search_contact_title,
        city=search_city,
        country=search_country,
    )

    context = {
        "customers": customers,
        "cities": cities,
        "countries": countries,
        "contact_titles": contact_titles,
        "search_company_name": search_company_name,
        "search_contact_name": search_contact_name,
        "search_contact_title": search_contact_title,
        "search_city": search_city,
        "search_country": search_country,
    }
    return render(request, "djtraders/customers/customer_list.html", context)


def customer_detail(request, customer_id):
    """
    A customer's page shell: the header and a Dashboard / Customer Info / Order
    History tab control. customer_id comes from the URL (see urls.py). A
    logged-in customer is redirected to their own page if the URL asks for
    another; employees and visitors may view any customer.
    """
    redirect_response = own_customer_redirect(request, customer_id)
    if redirect_response:
        return redirect_response

    customer = get_object_or_404(Customer, pk=customer_id)

    # Only the shell is built here; each tab's content comes from one of the
    # tab views below, loaded by AJAX once the page is open.
    return render(request, "djtraders/customers/customer_detail.html", {"customer": customer})


def customer_edit(request, customer_id):
    """
    Edits a customer with CustomerEditForm (forms.py); customer_edit.html draws
    it with django-crispy-forms. Open to an employee, or to that customer's own
    login (customer_access_denied).
    """
    customer = get_object_or_404(Customer, pk=customer_id)

    if customer_access_denied(request, customer_id):
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    if request.method == "POST":
        form = CustomerEditForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            return redirect("djtraders:customer_detail", customer_id=customer.customer_id)
    else:
        form = CustomerEditForm(instance=customer)

    # ?confirm_delete=1 (the Delete icon on the list) shows an in-page "are you
    # sure?" prompt instead of the form; its Confirm button posts to customer_delete.
    confirm_delete = request.GET.get("confirm_delete") == "1"

    context = {"customer": customer, "form": form, "confirm_delete": confirm_delete}
    return render(request, "djtraders/customers/customer_edit.html", context)


def customer_create(request):
    """
    Creates a customer on the same page and form as customer_edit, for a Customer
    that is not in the database yet. Employees only. GET shows a blank form
    (new_customer=True, so the page says "New Customer"). A valid POST asks
    Customer.generate_customer_id (models.py) for a new ID built from the company
    name, saves once, and returns to the list.
    """
    if not request.session.get("current_user"):
        return redirect("djtraders:customer_list")

    if request.method == "POST":
        form = CustomerEditForm(request.POST, instance=Customer())
        if form.is_valid():
            # The ID needs the validated company name, so it is made after validation.
            form.instance.customer_id = Customer.generate_customer_id(
                form.cleaned_data["company_name"]
            )
            form.save()
            return redirect("djtraders:customer_list")
    else:
        form = CustomerEditForm(instance=Customer())

    context = {"customer": form.instance, "form": form, "new_customer": True}
    return render(request, "djtraders/customers/customer_edit.html", context)


def customer_delete(request, customer_id):
    """
    Marks a customer inactive (inactive_date = today) instead of deleting the
    row, which keeps their order history. Employees only, and POST only because
    it changes data.
    """
    if not request.session.get("current_user"):
        return redirect("djtraders:customer_list")

    if request.method == "POST":
        customer = get_object_or_404(Customer, pk=customer_id)
        customer.inactive_date = timezone.now().date()
        customer.save()

    return redirect("djtraders:customer_list")


# region [CONCEPT] the customer page's tabs are partial pages
# customer_detail renders only the shell. Each tab's content comes from a view
# below, fetched by AJAX (LoadPageTab in DjangoTraders.js) and returned as an
# HTML fragment with no base.html around it. A logged-in customer only gets
# their own tabs (another customer's gets a 403); employees and visitors may
# view any customer's.
# endregion
def customer_dashboard(request, customer_id):
    """
    Dashboard tab: the four summary cards, revenue by year, monthly revenue (its year
    dropdown loads the chart itself), the category charts and the top products, or a
    message when there are no placed orders. The first version of each chart that has
    a control arrives already drawn; its control swaps it later.
    """
    if customer_tab_denied(request, customer_id):
        return HttpResponse(status=403)
    customer = get_object_or_404(Customer, pk=customer_id)

    context = {
        "customer": customer,
        "stats": customer.dashboard_stats(),
        "annual_plot": customer.annual_revenue_plot(),
        "order_years": customer.order_years(),
        "category_revenue_plot": customer.category_revenue_plot(),
        "category_units_plot": customer.category_units_plot(),
        "top_revenue_plot": customer.top_products_plot(measure="revenue"),
        "top_units_plot": customer.top_products_plot(measure="quantity"),
    }
    return render(request, "djtraders/customers/_customer_dashboard.html", context)


def customer_monthly_chart(request, customer_id):
    """
    The dashboard's year dropdown: Customer.monthly_revenue_plot for ?year=, as
    just the chart HTML that fills #dashboard-monthly. The year comes from the
    browser, so it is checked: 400 unless it is one of this customer's order years.
    """
    if customer_tab_denied(request, customer_id):
        return HttpResponse(status=403)
    customer = get_object_or_404(Customer, pk=customer_id)
    year = customer.parse_year(request.GET.get("year", ""))
    if not year:
        return HttpResponse("Choose a valid year.", status=400)
    plot = customer.monthly_revenue_plot(year)
    return HttpResponse(plot or "<p>No orders on record.</p>")


def customer_category_charts(request, customer_id):
    """
    The category section's controls (?year= a year or "all", ?kind= bar or pie for
    the unit share): both category charts together, as the HTML that fills
    #dashboard-categories, so one control changes both. The year is checked against
    this customer's order years and the kind against a fixed list (400 otherwise).
    """
    if customer_tab_denied(request, customer_id):
        return HttpResponse(status=403)
    customer = get_object_or_404(Customer, pk=customer_id)
    year = customer.parse_year(request.GET.get("year", "all"))
    kind = request.GET.get("kind", "bar")
    if year is False or kind not in ("bar", "pie"):
        return HttpResponse("Choose a valid year and chart.", status=400)
    return render(request, "djtraders/customers/_customer_category_charts.html", {
        "category_revenue_plot": customer.category_revenue_plot(year),
        "category_units_plot": customer.category_units_plot(year, kind),
    })


def customer_top_products_chart(request, customer_id):
    """
    The top-products section's controls (?year= a year or "all", ?top= 5, 10 or 20):
    the by-revenue and by-units charts together, as the HTML that fills
    #dashboard-top-products. Both values are checked (400 otherwise).
    """
    if customer_tab_denied(request, customer_id):
        return HttpResponse(status=403)
    customer = get_object_or_404(Customer, pk=customer_id)
    year = customer.parse_year(request.GET.get("year", "all"))
    top = request.GET.get("top", "10")
    if year is False or top not in ("5", "10", "20"):
        return HttpResponse("Choose a valid year and number of products.", status=400)
    return render(request, "djtraders/customers/_customer_top_product_charts.html", {
        "top_revenue_plot": customer.top_products_plot(int(top), "revenue", year),
        "top_units_plot": customer.top_products_plot(int(top), "quantity", year),
    })


def customer_info(request, customer_id):
    """
    Customer Info tab: the contact details and the Order Summary card, with its
    Start New Order button for an employee or the customer's own login.
    """
    if customer_tab_denied(request, customer_id):
        return HttpResponse(status=403)
    customer = get_object_or_404(Customer, pk=customer_id)

    # order_set is the reverse accessor for this customer's orders. An order with
    # no order_date is a cart that was never committed, so it is left out.
    orders = customer.order_set.filter(order_date__isnull=False)
    total_quantity = sum(
        line.quantity for order in orders for line in order.orderdetail_set.all()
    )
    total_revenue = sum(order.order_total for order in orders)

    context = {
        "customer": customer,
        "total_quantity": total_quantity,
        "total_revenue": total_revenue,
        "can_start_order": not customer_access_denied(request, customer.customer_id),
    }
    return render(request, "djtraders/customers/_customer_info.html", context)


def customer_orders(request, customer_id):
    """Order History tab: the customer's placed orders, newest first, in a DataTable."""
    if customer_tab_denied(request, customer_id):
        return HttpResponse(status=403)
    customer = get_object_or_404(Customer, pk=customer_id)
    orders = customer.order_set.filter(order_date__isnull=False).order_by("-order_date")
    return render(request, "djtraders/customers/_customer_orders.html", {
        "customer": customer,
        "orders": orders,
    })


def customer_login_view(request):
    """
    Customer login: pick a company from a dropdown (Customer.authenticate,
    models.py). On success customer_id goes into the session and the customer
    lands on their own page. Landing here first logs out whoever was logged in,
    so there is only ever one login at a time.
    """
    request.session.pop("current_user", None)
    request.session.pop("customer_id", None)
    request.session.pop("supplier_id", None)

    error = None
    if request.method == "POST":
        customer_id = request.POST.get("customer_id", "")
        password = request.POST.get("password", "")
        customer = Customer.authenticate(customer_id, password)
        if customer is not None:
            request.session["customer_id"] = customer.customer_id
            return redirect("djtraders:customer_detail", customer_id=customer.customer_id)
        error = "Incorrect customer/password combination."

    customers = Customer.objects.order_by("company_name")
    context = {"customers": customers, "error": error}
    return render(request, "djtraders/customers/customer_login.html", context)


def customer_logout_view(request):
    """Clears "customer_id" from the session and returns to the home page."""
    request.session.pop("customer_id", None)
    return redirect("djtraders:home")


def customer_signup(request):
    """
    Public "Create a FREE Account" page, linked from customer_login.html:
    a brand-new customer registers themselves. Compare to customer_create,
    the employee-only version of the same idea, where an employee adds a
    customer on their behalf and nobody is logged in as a result.

    CustomerSignupForm (djtraders/forms.py) asks for every column the
    customers table tracks, except customer_id (generated here, from the
    validated company name, by Customer.generate_customer_id -- a customer
    never picks it) and inactive_date (left blank, so the account starts
    out active). Nothing is written until the whole form passes validation.

    On success the new customer is logged straight in (the same
    "customer_id" session key customer_login_view sets) and sent to their
    own customer_detail page with a welcome message, instead of being made
    to find their company in the login dropdown they just joined.

    Same one-session-at-a-time rule as the two login views: landing on this
    page logs out whoever was logged in before, employee or customer.

    The ID is generated and saved inside one transaction, as an insert-only
    save. If two people register the same company name at the very same
    instant, both can be handed the same ID and the database's primary key
    rejects the second -- shown as an ordinary "try again" form error
    rather than a server error (or, worse, overwriting the first customer).
    """
    request.session.pop("current_user", None)
    request.session.pop("customer_id", None)
    request.session.pop("supplier_id", None)

    if request.method == "POST":
        form = CustomerSignupForm(request.POST, instance=Customer())
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.instance.customer_id = Customer.generate_customer_id(
                        form.cleaned_data["company_name"]
                    )
                    # force_insert=True: a plain save() on a row whose primary
                    # key is already set quietly UPDATES an existing row with
                    # that ID instead of failing, so a collision would
                    # overwrite another customer. Insert-only makes the
                    # database's primary key reject it, caught just below.
                    customer = form.save(commit=False)
                    customer.save(force_insert=True)
            except IntegrityError:
                form.add_error(
                    None, "We couldn't create your account just now -- please try again."
                )
            else:
                request.session["customer_id"] = customer.customer_id
                messages.success(
                    request,
                    "Welcome to The Marketplace at Carroll Trading Company, "
                    f"{customer.company_name}! Your account has been created and "
                    "you're logged in.",
                )
                return redirect("djtraders:customer_detail", customer_id=customer.customer_id)
    else:
        form = CustomerSignupForm(instance=Customer())

    return render(request, "djtraders/customers/customer_signup.html", {"form": form})


def customer_reactivate(request, customer_id):
    """
    Reverses customer_delete(): clears inactive_date so the customer is
    active again. Same access rule as Delete (employee-only) and same
    POST-only convention, since it changes data. Offered on
    customer_list.html, customer_detail.html, and the employee action bar
    on customer_edit.html. Order history is never touched.
    """
    if not request.session.get("current_user"):
        return redirect("djtraders:customer_list")

    if request.method == "POST":
        customer = get_object_or_404(Customer, pk=customer_id)
        customer.inactive_date = None
        customer.save()

    return redirect("djtraders:customer_list")
