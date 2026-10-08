"""
View functions for the djtraders app.

Browsing (open to anyone): home, customer_list/product_list (search
handled by each model's own search() classmethod, djtraders/models.py --
customer search by company/contact name, city, country, and contact
title; product search by name, category, and supplier),
customer_detail/product_detail, order_detail.

Two logins, each hand-rolled with plain sessions instead of Django's
own auth system: login_view/logout_view (employee, session key
"current_user") and customer_login_view/customer_logout_view (customer,
session key "customer_id"). Only one of the two can be logged in at a
time -- landing on either login page logs out whoever was there before.

Self-service access rule: a logged-in customer may only view/edit their
own record; an employee may act on any customer's. The four helpers at
the top of this file (_own_customer_redirect, _own_employee_redirect,
_customer_edit_denied, _order_access_denied) enforce that rule wherever
it applies, instead of repeating the same session checks in every view.

Customer edit/create: customer_edit is a Django ModelForm
(CustomerEditForm, djtraders/forms.py) rendered through
django-crispy-forms. customer_create reuses customer_edit's own
template and form for a Customer that doesn't exist yet.
customer_delete marks a customer inactive instead of deleting the row.

Ordering: a customer's in-progress order lives in
request.session["cart"] (a plain dict, no database row) until
order_commit writes it out as a real Order plus its OrderDetail rows,
inside one transaction. order_create/order_build/order_add_line/
order_update_line/order_remove_line/order_clear_cart/order_commit walk
through that flow; order_delete cancels an already-placed order on the
same day it was placed.
"""

from types import SimpleNamespace

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from .forms import CustomerEditForm, CustomerSignupForm, OrderCommitForm, OrderDetailForm, OrderLineQuantityForm, ProductEditForm, default_required_date, default_shipped_date
from .models import Category, Customer, Employee, Order, OrderDetail, Product, Supplier


def _own_customer_redirect(request, customer_id):
    """
    If a logged-in customer (request.session["customer_id"]) is asking
    for a different customer_id than their own, returns a redirect to
    their own customer_detail page instead. Returns None (proceed
    normally) for an employee, an anonymous visitor, or a customer
    already looking at their own page.

    Used by customer_list (called with customer_id=None, so any
    logged-in customer counts as "asking for a different one") and
    customer_detail (called with the customer_id from the URL).
    """
    logged_in_customer_id = request.session.get("customer_id")
    if logged_in_customer_id and logged_in_customer_id != customer_id:
        return redirect("djtraders:customer_detail", customer_id=logged_in_customer_id)
    return None


def _own_employee_redirect(request, employee_id):
    """
    Same idea as _own_customer_redirect above, for the employee side --
    if a logged-in employee (request.session["current_user"]) is asking
    for a different employee_id than their own, returns a redirect to
    their own employee_detail page instead; None otherwise.
    """
    logged_in_employee_id = request.session.get("current_user")
    if logged_in_employee_id and logged_in_employee_id != employee_id:
        return redirect("djtraders:employee_detail", employee_id=logged_in_employee_id)
    return None


def _order_access_denied(request, order):
    """
    True if the current session may NOT view/build/commit this order --
    neither an employee (who can act on any order) nor the order's own
    logged-in customer. Same shape as _customer_edit_denied below, just
    checked against order.customer_id instead of a customer_id URL
    parameter.

    order.customer can be None (a SET_NULL foreign key, djtraders/
    models.py) if the customer row it pointed to is ever gone -- treated
    as employee-only access, since there's no customer session left to
    match against.
    """
    logged_in_employee = request.session.get("current_user")
    if logged_in_employee:
        return False
    if order.customer_id is None:
        return True
    logged_in_customer_id = request.session.get("customer_id")
    return order.customer_id != logged_in_customer_id


def _cart_access_denied(request, customer_id):
    """
    True if the current session may NOT use this customer's shopping cart
    -- neither an employee (who can start and build a cart on behalf of any
    customer) nor that customer's own logged-in session. Same shape as
    _customer_edit_denied below; used by every cart view (order_create/
    build/add_line/update_line/remove_line/clear_cart/commit).

    The cart itself is still just request.session["cart"], tagged with the
    customer_id it belongs to -- only who is allowed to touch it changed.
    """
    if request.session.get("current_user"):
        return False
    return request.session.get("customer_id") != customer_id


def _customer_edit_denied(request, customer_id):
    """
    True if the current session may NOT edit this customer_id -- neither
    an employee (who can edit any customer) nor this customer's own
    logged-in session. Used by customer_edit to gate the whole view;
    unlike _own_customer_redirect above, an anonymous visitor (or a
    different customer) is denied outright here rather than redirected
    to their own page, since there's no "own edit page" to send them to
    instead.
    """
    logged_in_employee = request.session.get("current_user")
    logged_in_customer_id = request.session.get("customer_id")
    return not logged_in_employee and logged_in_customer_id != customer_id


def home(request):
    """
    Landing page for the djtraders app.

    Deliberately simple: no database access, just a template with links
    into the app's other pages -- no context dict either, since this
    page has no per-request data (compare to customer_list()/
    product_list() below, which each pass one).

    No login required to see this page -- Products stays a public
    catalog link for every visitor. current_employee/current_customer
    (djtraders/session_context.py) are already available in every
    template's context, so home.html decides on its own whether to show
    the Customers card or the Customer/Employee Login buttons instead.
    """
    return render(request, "djtraders/home.html")


def customer_list(request):
    """
    Display a list of customers, searchable by company name, city,
    country, contact name, and contact title.

    Uses the Customer model (djtraders/models.py) instead of raw SQL.
    The search fields come from the search form's GET parameters (a
    plain string, "" when not submitted); Customer.search handles
    turning those into the actual filter, so this view doesn't build
    the queryset itself.

    A logged-in customer only ever needs their own record, not the full
    roster -- _own_customer_redirect sends them straight to their own
    customer_detail page instead. Employees (and anonymous visitors)
    still see the full list.
    """
    redirect_response = _own_customer_redirect(request, customer_id=None)
    if redirect_response:
        return redirect_response

    search_company_name = request.GET.get("company_name", "")
    search_city = request.GET.get("city", "")
    search_country = request.GET.get("country", "")
    search_contact_name = request.GET.get("contact_name", "")
    search_contact_title = request.GET.get("contact_title", "")
    customers = Customer.search(company_name=search_company_name, city=search_city, country=search_country, contact_name=search_contact_name, contact_title=search_contact_title)

    # Distinct, non-blank country values on record, for the search
    # dropdown -- not every customer has a country, so blanks are excluded.
    countries = (
        Customer.objects.exclude(country__isnull=True)
        .exclude(country__exact="")
        .order_by("country")
        .values_list("country", flat=True)
        .distinct()
    )
    # Distinct, non-blank contact_title values on record, for the search dropdown.
    contact_titles = (
        Customer.objects.exclude(contact_title__isnull=True)
        .exclude(contact_title__exact="")
        .order_by("contact_title")
        .values_list("contact_title", flat=True)
        .distinct()
    )

    context = {
        "customers": customers,
        "countries": countries,
        "search_company_name": search_company_name,
        "search_city": search_city,
        "search_country": search_country,
        "search_contact_name": search_contact_name,
        "contact_titles": contact_titles,
        "search_contact_title": search_contact_title,
    }
    return render(request, "djtraders/customer_list.html", context)


def product_list(request):
    """
    Display a list of products, searchable by product name, category,
    and supplier, with an option to include discontinued products.

    Same shape as customer_list above -- product_name/category/supplier/
    show_all come from the search form's GET parameters; Product.search
    (djtraders/models.py) handles turning those into the actual filter.
    """
    search_product_name = request.GET.get("product_name", "")
    search_category_id = request.GET.get("category", "")
    search_supplier_id = request.GET.get("supplier", "")
    show_all = request.GET.get("show_all") == "on"

    products = Product.search(
        product_name=search_product_name,
        category_id=search_category_id,
        supplier_id=search_supplier_id,
        show_all=show_all,
    )

    # Every category/supplier on record, for the search dropdowns.
    categories = Category.objects.order_by("category_name")
    suppliers = Supplier.objects.order_by("company_name")

    context = {
        "products": products,
        "categories": categories,
        "suppliers": suppliers,
        "search_product_name": search_product_name,
        "search_category_id": search_category_id,
        "search_supplier_id": search_supplier_id,
        "show_all": show_all,
    }
    return render(request, "djtraders/product_list.html", context)


def product_detail(request, product_id):
    """
    Display a single product's full record: its own fields, its
    supplier, plus every order line it's appeared on
    (product.orderdetail_set).

    Units Sold/Total Revenue are read straight from Product's own
    units_sold/total_revenue properties (djtraders/models.py) rather
    than computed here.
    """
    product = get_object_or_404(Product, pk=product_id)

    # select_related("order", "order__customer") fetches each line's
    # Order and that order's Customer via JOINs, since the template
    # shows both on every row (the two-hop traversal).
    order_lines = product.orderdetail_set.select_related("order", "order__customer")

    context = {
        "product": product,
        "order_lines": order_lines,
    }
    return render(request, "djtraders/product_detail.html", context)

def product_create(request):
    """
    "Create Empty and Edit", same as customer_create: an unsaved Product()
    is shown in product_edit.html and only written on a valid Save.
    Employee-only -- customers shouldn't change the catalog or prices.
    """
    if not request.session.get("current_user"):
        return redirect("djtraders:product_list")

    if request.method == "POST":
        form = ProductEditForm(request.POST, instance=Product())
        if form.is_valid():
            # product_id has no auto-increment and discontinued is NOT NULL
            # with no default, so both are set here, after validation.
            form.instance.product_id = Product.generate_product_id()
            form.instance.discontinued = 0
            form.save()
            return redirect("djtraders:product_detail", product_id=form.instance.product_id)
    else:
        form = ProductEditForm(instance=Product())

    context = {"product": form.instance, "form": form, "new_product": True}
    return render(request, "djtraders/product_edit.html", context)


def product_edit(request, product_id):
    """
    Edits an existing product. Employee-only. ?confirm_delete=1 shows the
    in-page "are you sure?" prompt instead of the form, same as customer_edit.
    """
    product = get_object_or_404(Product, pk=product_id)

    if not request.session.get("current_user"):
        return redirect("djtraders:product_detail", product_id=product_id)

    if request.method == "POST":
        form = ProductEditForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            return redirect("djtraders:product_detail", product_id=product.product_id)
    else:
        form = ProductEditForm(instance=product)

    confirm_delete = request.GET.get("confirm_delete") == "1"
    context = {"product": product, "form": form, "confirm_delete": confirm_delete}
    return render(request, "djtraders/product_edit.html", context)


def product_delete(request, product_id):
    """
    Soft delete: sets discontinued=1 and date_discontinued=today instead of
    removing the row, so order history stays intact. Employee-only and
    POST-only, mirroring customer_delete. Reversed by product_renew below.
    """
    if not request.session.get("current_user"):
        return redirect("djtraders:product_list")

    if request.method == "POST":
        product = get_object_or_404(Product, pk=product_id)
        product.discontinued = 1
        product.date_discontinued = timezone.now().date()
        product.save()

    return redirect("djtraders:product_list")


def product_renew(request, product_id):
    """
    Reverses product_delete(): sets discontinued back to 0 and clears
    date_discontinued, so the product is back in the active catalog (and
    in the cart's product dropdown). Same access rule as Discontinue
    (employee-only) and same POST-only convention, since it changes
    data. Offered on product_list.html and product_detail.html; order
    history and stock levels are never touched.
    """
    if not request.session.get("current_user"):
        return redirect("djtraders:product_list")

    if request.method == "POST":
        product = get_object_or_404(Product, pk=product_id)
        product.discontinued = 0
        product.date_discontinued = None
        product.save()

    return redirect("djtraders:product_list")


def customer_detail(request, customer_id):
    """
    Display a single customer's full record.

    customer_id comes from the URL itself (see djtraders/urls.py's
    customer_detail_url, which captures it with a path converter) rather
    than from a query string or form -- Django hands it to this view as
    a plain function argument with the same name used in the URL pattern.

    A logged-in customer can only view their own record --
    _own_customer_redirect sends them back to their own page if the URL
    asks for a different customer_id. Employees (and anonymous visitors)
    can view any customer's page.
    """
    redirect_response = _own_customer_redirect(request, customer_id)
    if redirect_response:
        return redirect_response

    # get_object_or_404 is shorthand for .objects.get(pk=...), except it
    # raises Http404 instead of letting DoesNotExist crash the request.
    customer = get_object_or_404(Customer, pk=customer_id)

    # customer.order_set is Order's reverse FK accessor -- every order
    # this customer has placed. order_date__isnull=False excludes a cart
    # that was started (order_create below) but never committed
    # (order_commit below) -- order_date doubles as the "placed" flag.
    # Each order's own order_total property (djtraders/models.py) sums
    # its line items, so this view just adds those totals together
    # rather than computing revenue itself.
    orders = customer.order_set.filter(order_date__isnull=False).order_by("-order_date")
    total_quantity = sum(
        line.quantity for order in orders for line in order.orderdetail_set.all()
    )
    total_revenue = sum(order.order_total for order in orders)

    # "Start New Order" is self-service only -- only the logged-in
    # customer viewing their own page gets the button.
    can_start_order = not _cart_access_denied(request, customer.customer_id)

    context = {
        "customer": customer,
        "total_quantity": total_quantity,
        "total_revenue": total_revenue,
        "orders": orders,
        "can_start_order": can_start_order,
    }
    return render(request, "djtraders/customer_detail.html", context)


def customer_edit(request, customer_id):
    """
    Edit a customer's record with a Django ModelForm: CustomerEditForm
    (djtraders/forms.py) declares the fields/widgets once as a class,
    request.POST is bound to it and checked with form.is_valid(), and
    form.save() writes every validated field onto the Customer instance
    at once -- no manual field-by-field assignment. company_name being
    required is enforced automatically (a ModelForm reads that off the
    model field itself).

    customer_edit.html renders the form with django-crispy-forms'
    {% crispy %} tag. Available to an employee editing any customer, or a
    logged-in customer editing their own record only
    (_customer_edit_denied, above).
    """
    customer = get_object_or_404(Customer, pk=customer_id)

    if _customer_edit_denied(request, customer_id):
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    if request.method == "POST":
        form = CustomerEditForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            return redirect("djtraders:customer_detail", customer_id=customer.customer_id)
    else:
        form = CustomerEditForm(instance=customer)

    # confirm_delete=1 (customer_list.html's Delete icon, or the Delete
    # button on this page's own employee action bar) shows an in-page
    # "are you sure?" prompt instead of the edit form -- see
    # customer_edit.html. Employee-only, like customer_delete itself: a
    # customer editing their own record never sees the prompt, even with
    # ?confirm_delete=1 typed into the address. Its own Confirm button is
    # a real POST to customer_delete, not a browser confirm() popup (see
    # CLAUDE.md).
    confirm_delete = request.GET.get("confirm_delete") == "1" and bool(
        request.session.get("current_user")
    )

    context = {"customer": customer, "form": form, "confirm_delete": confirm_delete}
    return render(request, "djtraders/customer_edit.html", context)


def customer_create(request):
    """
    "Create Empty and Edit": renders the exact same page as
    customer_edit above -- same template, same CustomerEditForm, same
    field grid -- for a Customer that doesn't exist in the database yet,
    and writes it to the database exactly once, only when Save is
    actually clicked. Employee-only, same as customer_delete; a customer
    edits their own existing record but never creates a new one.

    GET builds a blank, unsaved Customer() and hands it to
    CustomerEditForm/customer_edit.html with new_customer=True in the
    context, so that template can tell "New Customer" from "Edit
    <existing customer>" and point its own Cancel link at customer_list
    instead of a customer_detail page that doesn't exist yet. Clicking
    Cancel from here is a plain link, not a form submission -- nothing
    was ever saved, so there's nothing to undo or delete.

    POST validates the submitted fields through that same form -- no
    different from customer_edit's own POST handling above, since
    customer_id was never one of CustomerEditForm's fields to begin
    with (djtraders/forms.py). Only on success does this view do the two
    things customer_edit's POST never has to: ask
    Customer.generate_customer_id (djtraders/models.py) to invent a new,
    unique customer_id from the now-validated company_name -- a customer
    never picks or types their own ID -- and redirect to customer_list
    rather than customer_detail, so the employee who just created this
    customer sees it appear in the roster right away.
    """
    if not request.session.get("current_user"):
        return redirect("djtraders:customer_list")

    if request.method == "POST":
        # instance=Customer() -- an unsaved, blank row -- so is_valid()
        # runs the exact same field checks customer_edit's POST runs
        # against an existing customer.
        form = CustomerEditForm(request.POST, instance=Customer())
        if form.is_valid():
            # Only generated once everything else has already passed
            # validation -- generate_customer_id needs a real,
            # validated company_name to build a sensible ID from.
            form.instance.customer_id = Customer.generate_customer_id(
                form.cleaned_data["company_name"]
            )
            form.save()
            return redirect("djtraders:customer_list")
    else:
        form = CustomerEditForm(instance=Customer())

    context = {"customer": form.instance, "form": form, "new_customer": True}
    return render(request, "djtraders/customer_edit.html", context)


def customer_delete(request, customer_id):
    """
    Marks a customer inactive (sets inactive_date to today) instead of
    actually deleting the row -- reversible, and keeps their order
    history intact. Employee-only action, available from the Actions
    column on customer_list.html and from the employee action bar on
    customer_edit.html (which asks "are you sure?" first); POST-only,
    since it changes data.
    """
    if not request.session.get("current_user"):
        return redirect("djtraders:customer_list")

    if request.method == "POST":
        customer = get_object_or_404(Customer, pk=customer_id)
        customer.inactive_date = timezone.now().date()
        customer.save()

    return redirect("djtraders:customer_list")

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



def order_detail(request, order_id):
    """
    Display a single order: who placed it, who processed/shipped it, and
    every product line item on it.

    This view exists mainly to illustrate model traversal end to end.
    Starting from one Order: order.customer and order.employee/
    order.ship_via are forward ForeignKeys (Order holds those FK
    columns), while the order's line items are a reverse relationship
    (order.orderdetail_set -- OrderDetail holds the FK to Order, not the
    other way around), and each of those lines reaches its own Product
    via yet another forward FK (order_detail.product). Reached from
    customer_detail.html's Orders table.

    The page itself has no access check -- an order's detail page is
    viewable by anyone, the same as a product or employee's detail page.
    can_cancel_order (below) is the one thing on this page that IS
    gated, since Cancel Order (order_delete below) is a real,
    destructive, self-service action.
    """
    order = get_object_or_404(Order, pk=order_id)

    # order.orderdetail_set is Django's default reverse accessor name for
    # OrderDetail's FK to Order. select_related("product__supplier")
    # fetches each line's Product AND that Product's Supplier via one
    # JOIN in this same query, instead of a separate query per line --
    # worth it since the template touches both every row. Each line's
    # own line_total property (djtraders/models.py) is used directly in
    # the template, no annotation needed here.
    order_lines = order.orderdetail_set.select_related("product__supplier")

    # Cancel Order (order_delete below) is only shown for a placed order
    # (order_date set) from today, to the order's own customer or an
    # employee -- computed once here, not left for the template to
    # reason about, since order_delete itself re-checks both halves of
    # this same condition server-side regardless.
    can_cancel_order = order.order_date == timezone.now().date() and not _order_access_denied(
        request, order
    )

    context = {
        "order": order,
        "order_lines": order_lines,
        "can_cancel_order": can_cancel_order,
    }
    return render(request, "djtraders/order_detail.html", context)


def login_view(request):
    """
    Employee login: pick a name from a dropdown instead of typing one,
    and enter the 4-digit year of that employee's own birth_date as the
    password (see Employee.authenticate, djtraders/models.py).

    On success, employee_id goes into request.session under
    "current_user" -- Django's session framework stores that in a
    per-visitor cookie-backed session, so it's remembered across
    requests without Django's own auth system (django.contrib.auth)
    being involved. The employee is then sent to their own
    employee_detail page (self-service), not straight into the full
    customer_list.

    Only one employee or customer can be logged in at a time, not both
    at once -- landing on this page (clicking "Employee Login") logs out
    whoever was previously logged in, employee or customer, before the
    form is even shown.
    """
    request.session.pop("current_user", None)
    request.session.pop("customer_id", None)

    error = None
    if request.method == "POST":
        employee_id = request.POST.get("employee_id", "")
        password = request.POST.get("password", "")
        employee = Employee.authenticate(employee_id, password)
        if employee is not None:
            request.session["current_user"] = employee.employee_id
            return redirect("djtraders:employee_detail", employee_id=employee.employee_id)
        error = "Incorrect employee/password combination."

    employees = Employee.objects.order_by("last_name", "first_name")
    context = {"employees": employees, "error": error}
    return render(request, "djtraders/login.html", context)


def logout_view(request):
    """
    Clears "current_user" from the session, logging the employee out,
    then sends them back to the app home page -- home always renders
    regardless of login state (see its own docstring), so this just
    lands them back on the page with the login buttons showing again.
    """
    request.session.pop("current_user", None)
    return redirect("djtraders:home")


def customer_login_view(request):
    """
    Customer login: pick a company name from a dropdown instead of
    typing a customer_id (see Customer.authenticate, djtraders/models.py),
    same reasoning as the employee login's dropdown -- easier than
    remembering a 5-character ID.

    On success, customer_id goes into request.session under
    "customer_id" -- a separate session key from the employee login's
    "current_user". The customer is then sent straight to their own
    customer_detail page, not the full customer list an employee sees
    after logging in.

    Only one employee or customer can be logged in at a time, not both
    at once -- landing on this page (clicking "Customer Login") logs
    out whoever was previously logged in, employee or customer, before
    the form is even shown.
    """
    request.session.pop("current_user", None)
    request.session.pop("customer_id", None)

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
    return render(request, "djtraders/customer_login.html", context)


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

    return render(request, "djtraders/customer_signup.html", {"form": form})


def customer_logout_view(request):
    """
    Clears "customer_id" from the session, logging the customer out,
    then sends them back to the app home page -- same as logout_view
    above, home always renders regardless of login state, landing them
    back on the page with the login buttons showing again.
    """
    request.session.pop("customer_id", None)
    return redirect("djtraders:home")


def employee_detail(request, employee_id):
    """
    Display a single employee's own record -- the page login_view sends
    an employee to on a successful login, showing who they are plus
    quick links into Customers and Products, the two things an employee
    actually needs to get to next.

    Same restriction as customer_detail: a logged-in employee can only
    view their own record, not another employee's, by URL
    (_own_employee_redirect, above). Anonymous visitors can still view
    any employee's page, same as customer_detail's own rule.
    """
    redirect_response = _own_employee_redirect(request, employee_id)
    if redirect_response:
        return redirect_response

    employee = get_object_or_404(Employee, pk=employee_id)
    context = {"employee": employee}
    return render(request, "djtraders/employee_detail.html", context)

# Volume discount (Extra Credit A): a line with MORE THAN this many units
# automatically gets this rate off, with nothing typed in. It never stacks
# with an employee-entered discount -- the line gets the larger of the two.
VOLUME_DISCOUNT_THRESHOLD = 10
VOLUME_DISCOUNT_RATE = 0.10

def _cart_lines(cart):
    """
    Turns a session cart's "lines" dict ({str(product_id): quantity}, no
    database row backing any of it) into a list of lightweight,
    OrderDetail-shaped objects: .product, .unit_price, .quantity,
    .discount, .line_total. A plain types.SimpleNamespace, not a real
    model instance -- there might never be a real OrderDetail row, if
    this cart is abandoned -- but shaped so _order_line_row.html and the
    running total can be built exactly the same way as when these are
    real rows, with no template changes needed either way.

    discount comes from cart["discounts"], a {str(product_id): fraction}
    dict kept beside "lines" (0.10 = 10%, same as OrderDetail.discount);
    0.0 when none was entered.

    A cart line whose product_id no longer resolves to a real product
    (e.g. deleted) is silently skipped rather than raising -- nothing
    here enforces referential integrity the way a real ForeignKey would.
    """
    product_ids = [int(product_id) for product_id in cart.get("lines", {})]
    products_by_id = Product.objects.in_bulk(product_ids)

    discounts = cart.get("discounts", {})
    lines = []
    for product_id_str, quantity in cart.get("lines", {}).items():
        product = products_by_id.get(int(product_id_str))
        if product is None:
            continue
        unit_price = product.unit_price or 0.0
        manual_discount = discounts.get(product_id_str, 0.0)
        volume_discount = VOLUME_DISCOUNT_RATE if quantity > VOLUME_DISCOUNT_THRESHOLD else 0.0
        # The better of the two, never both added together.
        discount = max(manual_discount, volume_discount)
        lines.append(
            SimpleNamespace(
                product=product,
                unit_price=unit_price,
                quantity=quantity,
                discount=discount,
                discount_percent=round(discount * 100, 2),
                is_volume_discount=volume_discount > 0 and volume_discount >= manual_discount,
                line_total=unit_price * quantity * (1 - discount),
            )
        )
    return lines


def _product_picker_context(detail_form):
    """
    Extra context for order_build.html's product picker (enhancement #2):
    the Category dropdown's choices, plus {product_id: category_id} for
    every product the Product dropdown offers, so the browser can narrow
    that list as the user types or picks a category -- no extra request.
    """
    products = detail_form.fields["product"].queryset
    return {
        "categories": Category.objects.order_by("category_name"),
        "product_category_map": {p.product_id: p.category_id for p in products},
    }


def order_create(request, customer_id):
    """
    Starts (or resumes) this customer's shopping cart in
    request.session["cart"] -- no database row at all until commit
    (order_commit below). POST-only (customer_detail.html's own "Start
    New Order" button is a real <form method="post">, not a link, since
    this writes session data). Self-service only: the logged-in customer
    starting an order for themselves (see customer_detail's own
    can_start_order flag above).

    request.session["cart"] is only reused if it already belongs to this
    same customer_id -- a different customer logging in on the same
    browser never sees someone else's leftover cart; a mismatch is
    treated as no cart at all, and a fresh, empty one is started. At
    most one open cart per browser session -- clicking "Start New Order"
    again just returns to the same cart already open, instead of
    starting a second one.

    Redirects straight into order_build to start adding line items.
    """
    if _cart_access_denied(request, customer_id):
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    if request.method != "POST":
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    cart = request.session.get("cart")
    if not cart or cart.get("customer_id") != customer_id:
        request.session["cart"] = {"customer_id": customer_id, "lines": {}}

    return redirect("djtraders:order_build", customer_id=customer_id)


def order_build(request, customer_id):
    """
    The shopping cart page. There is no Order row and no order_id at all
    until commit (order_commit below) -- everything here comes from
    request.session["cart"] (a plain {"customer_id": ...,
    "lines": {product_id: quantity}} dict, see _cart_lines above) and a
    fresh Customer/Product lookup, never a database Order. The Place
    Order card's "Ship To" fields start out filled in with the customer's
    own on-file address, read live off Customer every time this renders,
    but they are real, editable form fields (OrderCommitForm) -- order_commit
    saves whatever was submitted onto the Order's ship_* columns.
    OrderCommitForm's employee field
    is required -- no order commits without one picked, a business rule,
    not a database one (see that form's own docstring, djtraders/forms.py).

    Access is self-service only: request.session["customer_id"] must
    match customer_id, same rule order_create uses -- there is no
    employee-side access to someone else's session cart (unlike
    order_detail/order_delete's own _order_access_denied, which allows
    an employee too, because those act on a real, already-placed Order
    row instead of another browser's session state). A cart missing or
    belonging to a different customer_id is treated as empty and
    (re)started here, same as order_create -- this view alone is enough
    to reach a working cart page, even without ever visiting
    order_create first (e.g. a bookmarked or re-typed URL).
    """
    if _cart_access_denied(request, customer_id):
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    customer = get_object_or_404(Customer, pk=customer_id)

    cart = request.session.get("cart")
    if not cart or cart.get("customer_id") != customer_id:
        cart = {"customer_id": customer_id, "lines": {}}
        request.session["cart"] = cart

    cart_lines = _cart_lines(cart)
    cart_total = sum(line.line_total for line in cart_lines)
    detail_form = OrderDetailForm(is_employee=bool(request.session.get("current_user")))
    # required_date/shipped_date default to a business-convention guess
    # (order_date, today at commit, plus two weeks / one week) but stay
    # real, editable fields on this form -- see OrderCommitForm/
    # default_required_date/default_shipped_date (djtraders/forms.py).
    commit_form = OrderCommitForm(
        initial={
            "required_date": default_required_date(),
            "shipped_date": default_shipped_date(),
            "employee": request.session.get("current_user"),
            "ship_name": customer.company_name,
            "ship_address": customer.address,
            "ship_city": customer.city,
            "ship_region": customer.region,
            "ship_postal_code": customer.postal_code,
            "ship_country": customer.country,
        }
    )

    context = {
        "customer": customer,
        "cart_lines": cart_lines,
        "cart_total": cart_total,
        "detail_form": detail_form,
        "stock_map": {p.product_id: (p.units_in_stock or 0) for p in detail_form.fields["product"].queryset},
        **_product_picker_context(detail_form),
        "commit_form": commit_form,
    }
    return render(request, "djtraders/order_build.html", context)


def order_add_line(request, customer_id):
    """
    AJAX endpoint (order_build.html's Add Line Item form,
    DjangoTraders.js) -- adds a product/quantity line to
    request.session["cart"]["lines"], or increases an already-existing
    line's quantity instead of a second entry for the same product_id (a
    plain dict key, doing by hand what a real OrderDetail row's own
    composite primary key would guarantee for free -- there is no
    database backstop here at all until commit).

    unit_price/discount are never asked for on the form -- _cart_lines
    (above) prices every line fresh, including this one, whenever it's
    next read, right up through commit. Returns JSON, not a redirect/
    render -- this is the one genuinely AJAX-driven workflow in the app,
    so the page itself never reloads while lines are being added.

    The stock rule (what's already in the cart plus this quantity can't
    exceed units_in_stock) is enforced by OrderDetailForm.clean(), so
    an over-stock add comes back as an ordinary field error here.
    """
    if _cart_access_denied(request, customer_id):
        return JsonResponse({"success": False, "errors": {"__all__": ["Not allowed."]}}, status=403)

    cart = request.session.get("cart")
    if not cart or cart.get("customer_id") != customer_id:
        return JsonResponse(
            {"success": False, "errors": {"__all__": ["Your cart isn't open anymore -- reload the page."]}},
            status=400,
        )

    form = OrderDetailForm(
        request.POST,
        in_cart=cart["lines"],
        is_employee=bool(request.session.get("current_user")),
    )
    if not form.is_valid():
        # get_json_data(), not the bare ErrorDict form.errors itself --
        # Django's own error objects aren't directly JSON-serializable;
        # this returns a plain {field: [{"message": ..., "code": ...}]}
        # dict instead, which JsonResponse can actually encode.
        return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

    product = form.cleaned_data["product"]
    quantity = form.cleaned_data["quantity"]

    product_key = str(product.product_id)
    cart["lines"][product_key] = cart["lines"].get(product_key, 0) + quantity
    discount_percent = form.cleaned_data.get("discount_percent")
    if discount_percent is not None:
        cart.setdefault("discounts", {})[product_key] = discount_percent / 100
    # Session middleware only notices a *replaced* top-level key by
    # default -- mutating cart["lines"] in place (as just above) doesn't
    # trigger that on its own, so this has to be set explicitly or the
    # change is silently dropped at the end of the request.
    request.session.modified = True

    cart_lines = _cart_lines(cart)
    line = next(line for line in cart_lines if line.product.product_id == product.product_id)
    row_html = render_to_string(
        "djtraders/_order_line_row.html",
        {"line": line, "customer_id": customer_id},
        request=request,
    )

    cart_total = sum(line.line_total for line in cart_lines)
    return JsonResponse(
        {
            "success": True,
            "row_html": row_html,
            "product_id": product.product_id,
            "order_total": f"{cart_total:,.2f}",
        }
    )


def order_update_line(request, customer_id, product_id):
    """
    AJAX endpoint (the Quantity box on each row of order_build.html,
    DjangoTraders.js's UpdateCartQuantities) -- sets one cart line's
    quantity to exactly the number typed, where order_add_line would add
    that number on top of what's already there. Returns JSON in the same
    shape as order_add_line (row_html, product_id, order_total), so the
    page can swap in the refreshed row and the new total without a reload.

    Only quantity is ever read from the POST. The line's discount is not
    touched, so this can't be used to get one (a customer can't) and an
    employee's discount survives the change; _cart_lines re-prices the line
    from its new quantity, so crossing the volume-discount threshold in
    either direction (more than 10 units) adds or drops that automatic 10%
    on its own. The rules for the number itself (at least 1, no more than
    the stock on hand) are OrderLineQuantityForm's.

    Only a product that is already in the cart can be updated -- this never
    creates a line (that's order_add_line), and a quantity below 1 is
    refused rather than treated as a removal (that's order_remove_line).
    POST-only, same self-service access check as the other cart views.

    JSON is only the answer to an AJAX call (jQuery marks every one with
    an X-Requested-With header). If the row's form is submitted the
    ordinary way instead -- JavaScript blocked, or the page is running an
    old saved copy of DjangoTraders.js that has no UpdateCartQuantities
    yet -- the same checks run, but the answer is a redirect back to the
    cart, with any problem shown as a red message at the top of the page.
    Either way nobody is left looking at a page of raw JSON.
    """
    wants_json = request.headers.get("x-requested-with") == "XMLHttpRequest"

    def refuse(errors, status):
        # errors is {field: [str or {"message": ..., "code": ...}]} -- the
        # shape the JSON branch sends as-is. A plain form submit gets each
        # message as a red banner (base.html) on the redirected cart page.
        if wants_json:
            return JsonResponse({"success": False, "errors": errors}, status=status)
        for field_errors in errors.values():
            for error in field_errors:
                messages.error(request, error if isinstance(error, str) else error["message"])
        return redirect("djtraders:order_build", customer_id=customer_id)

    if _cart_access_denied(request, customer_id):
        if wants_json:
            return JsonResponse({"success": False, "errors": {"__all__": ["Not allowed."]}}, status=403)
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    if request.method != "POST":
        return refuse({"__all__": ["Not allowed."]}, 405)

    cart = request.session.get("cart")
    if not cart or cart.get("customer_id") != customer_id:
        return refuse({"__all__": ["Your cart isn't open anymore -- reload the page."]}, 400)

    product_key = str(product_id)
    product = Product.objects.filter(pk=product_id).first()
    if product is None or product_key not in cart["lines"]:
        return refuse({"__all__": ["That item isn't in your cart anymore -- reload the page."]}, 400)

    form = OrderLineQuantityForm(request.POST, product=product)
    if not form.is_valid():
        # Same get_json_data() shape order_add_line returns -- see the
        # comment there for why it isn't the bare form.errors.
        return refuse(form.errors.get_json_data(), 400)

    cart["lines"][product_key] = form.cleaned_data["quantity"]
    # Mutating the nested dict in place isn't noticed by the session
    # middleware on its own -- same reason order_add_line sets this.
    request.session.modified = True

    if not wants_json:
        return redirect("djtraders:order_build", customer_id=customer_id)

    cart_lines = _cart_lines(cart)
    line = next(line for line in cart_lines if line.product.product_id == product_id)
    row_html = render_to_string(
        "djtraders/_order_line_row.html",
        {"line": line, "customer_id": customer_id},
        request=request,
    )

    cart_total = sum(line.line_total for line in cart_lines)
    return JsonResponse(
        {
            "success": True,
            "row_html": row_html,
            "product_id": product_id,
            "order_total": f"{cart_total:,.2f}",
        }
    )


def order_remove_line(request, customer_id, product_id):
    """
    Removes one product from the session cart entirely (not just a lower
    quantity). There's no database row to delete before commit -- the cart
    is just request.session["cart"]["lines"], a {str(product_id): quantity}
    dict, so this pops one key. POST-only, same self-service access check
    as order_add_line/order_commit.
    """
    if _cart_access_denied(request, customer_id):
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    cart = request.session.get("cart")
    if request.method == "POST" and cart and cart.get("customer_id") == customer_id:
        cart["lines"].pop(str(product_id), None)
        cart.get("discounts", {}).pop(str(product_id), None) 
        # Mutating the nested dict in place isn't noticed by the session
        # middleware on its own -- same reason order_add_line sets this.
        request.session.modified = True

    return redirect("djtraders:order_build", customer_id=customer_id)


def order_clear_cart(request, customer_id):
    """
    Empties the session cart without committing it:
    request.session["cart"]["lines"] = {}. Nothing is written to the
    database. POST-only, same access check as order_remove_line.
    """
    if _cart_access_denied(request, customer_id):
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    cart = request.session.get("cart")
    if request.method == "POST" and cart and cart.get("customer_id") == customer_id:
        cart["lines"] = {}
        cart["discounts"] = {}
        request.session.modified = True

    return redirect("djtraders:order_build", customer_id=customer_id)



def order_commit(request, customer_id):
    """
    Places the cart -- the one point where any of it is written to the
    database at all. Builds one real Order (order_date set to today,
    employee/required_date/shipped_date and the ship_* ship-to address,
    all from OrderCommitForm) and one real OrderDetail per
    cart line, inside a single transaction -- either the whole order is
    written, or, on any failure partway through, none of it is left
    half-written behind. The session cart is only cleared after that
    succeeds.

    OrderCommitForm is used unbound here (no instance=) -- it builds a
    brand-new Order via form.save(commit=False), rather than updating an
    existing one.

    Refuses to commit when there's no open cart for this customer, or it
    has no lines -- an order with nothing on it isn't a meaningful
    "placed" order -- redirecting back to order_build either way, which
    will itself (re)start an empty cart if needed. Self-service only:
    request.session["customer_id"] must match customer_id, same as
    order_create/order_build -- see order_build's own docstring for why
    there is no employee-side access to someone else's session cart
    here, unlike order_detail/order_delete's own _order_access_denied.
    """
    if _cart_access_denied(request, customer_id):
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    if request.method != "POST":
        return redirect("djtraders:order_build", customer_id=customer_id)

    cart = request.session.get("cart")
    if not cart or cart.get("customer_id") != customer_id or not cart.get("lines"):
        return redirect("djtraders:order_build", customer_id=customer_id)

    customer = get_object_or_404(Customer, pk=customer_id)
    cart_lines = _cart_lines(cart)
    if not cart_lines:
        return redirect("djtraders:order_build", customer_id=customer_id)

    form = OrderCommitForm(request.POST)
    if form.is_valid():
        order = form.save(commit=False)
        order.customer = customer
        order.order_date = timezone.now().date()
        # The ship_* columns are not set here: form.save(commit=False) above has
        # already filled them from the Ship To section (OrderCommitForm).

        stock_problems = []
        with transaction.atomic():
            # select_for_update() locks these product rows until the
            # transaction ends, so two buyers can't both take the last units.
            # The stock is re-read here, not trusted from when the line was
            # added -- someone else may have bought it since.
            locked = Product.objects.select_for_update().in_bulk(
                [line.product.product_id for line in cart_lines]
            )
            for line in cart_lines:
                product = locked[line.product.product_id]
                available = product.units_in_stock or 0
                if line.quantity > available:
                    stock_problems.append(
                        f"{product.product_name}: only {available} in stock now, "
                        f"but your cart has {line.quantity}."
                    )

            if not stock_problems:
                order.save()
                OrderDetail.objects.bulk_create(
                    OrderDetail(
                        order=order,
                        product=line.product,
                        unit_price=line.unit_price,
                        quantity=line.quantity,
                        discount=line.discount,
                    )
                    for line in cart_lines
                )
                for line in cart_lines:
                    product = locked[line.product.product_id]
                    product.units_in_stock = (product.units_in_stock or 0) - line.quantity
                Product.objects.bulk_update(locked.values(), ["units_in_stock"])

        if stock_problems:
            # Nothing was written. Fall through to the re-render below, which
            # shows these in the Place Order card.
            for message in stock_problems:
                form.add_error(None, message)
        else:
            del request.session["cart"]
            return redirect("djtraders:customer_detail", customer_id=customer_id)

    cart_total = sum(line.line_total for line in cart_lines)
    detail_form = OrderDetailForm(is_employee=bool(request.session.get("current_user")))
    context = {
        "customer": customer,
        "cart_lines": cart_lines,
        "cart_total": cart_total,
        "detail_form": detail_form,
        "stock_map": {p.product_id: (p.units_in_stock or 0) for p in detail_form.fields["product"].queryset},
        **_product_picker_context(detail_form),
        "commit_form": form,
    }
    return render(request, "djtraders/order_build.html", context)


def order_delete(request, order_id):
    """
    Cancels a placed order -- a real, hard DELETE (OrderDetail's own
    CASCADE on its order FK, models.py, cleans up its lines for free) --
    but only on the same calendar day it was placed. order_date itself
    is the placed/draft flag and never touched after commit, so "today"
    here is compared against that same value order_commit set, not
    recomputed some other way.

    A still-open cart (order_date is None) is refused here too -- there
    is nothing "placed" yet to cancel. Access is the order's own
    customer, or an employee (_order_access_denied, above), same as
    build/commit.

    No confirmation step (no "are you sure?" page or JS dialog) -- a
    single-click POST, the same convention Commit Order itself already
    uses. order_detail.html's own Cancel Order button is gated
    (can_cancel_order, order_detail above) so it's only shown when this
    would actually succeed; reaching this view any other way (a stale
    page, a same-day order that ticks past midnight while the tab is
    still open, or the URL typed directly) fails this same check and is
    silently redirected back, same as every other guard in this file.
    """
    order = get_object_or_404(Order, pk=order_id)

    if _order_access_denied(request, order):
        return redirect("djtraders:home")

    if request.method != "POST":
        return redirect("djtraders:order_detail", order_id=order.order_id)

    if order.order_date is None or order.order_date != timezone.now().date():
        return redirect("djtraders:order_detail", order_id=order.order_id)

    customer_id = order.customer_id
    order.delete()

    if customer_id:
        return redirect("djtraders:customer_detail", customer_id=customer_id)
    return redirect("djtraders:home")