from django.shortcuts import get_object_or_404, render

from .models import Category, Customer, Order, Product, Supplier

"""
View functions for the djtraders app.

  1. customer_list/product_list are ORM-based list views (Customer.objects/
    Product.objects), each with a search form whose GET parameters are
    handed to the model's own search() classmethod rather than building
    the filter here.
  2. customer_detail looks up one Customer, lists their orders
    (customer.order_set), and totals quantity/revenue across them.
  3. order_detail illustrates model traversal end to end: forward FKs
    to Customer/Employee/Shipper, a reverse relation to its line items,
    each reaching its own Product.
  4. product_detail is left as an assignment component -- students build
    that view (and its template/URL) themselves.
  5. customer_detail/order_detail read order.order_total/line.line_total
    (plain Python properties on the models) directly, instead of
    building the same math with ExpressionWrapper/F/Sum queryset
    annotations here.
"""


def home(request):
    """
    Landing page for the djtraders app.

    Deliberately simple: no database access, just a template with links
    into the app's other pages. render(request, template_name) builds the
    HttpResponse; no context dict here since this page has no per-request
    data (compare to customer_list()/product_list() below, which each
    pass one).
    """
    return render(request, "djtraders/home.html")


def customer_list(request):
    """
    Display a list of customers, searchable by company name and country.

    Uses the Customer model (djtraders/models.py) instead of raw SQL.
    company_name/country come from the search form's GET parameters (a
    plain string, "" when not submitted); Customer.search handles turning
    those into the actual filter, so this view doesn't build the
    queryset itself.
    """
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
    Display a list of products, searchable by product name and category,
    with an option to include discontinued products.

    Same shape as customer_list above -- product_name/category/show_all
    come from the search form's GET parameters; Product.search
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

    # Every category on record, for the search dropdown.
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

def customer_detail(request, customer_id):
    """
    Display a single customer's full record.

    customer_id comes from the URL itself (see djtraders/urls.py's
    customer_detail_url, which captures it with a path converter) rather
    than from a query string or form -- Django hands it to this view as
    a plain function argument with the same name used in the URL pattern.
    """
    # get_object_or_404 is shorthand for .objects.get(pk=...), except it
    # raises Http404 instead of letting DoesNotExist crash the request.
    customer = get_object_or_404(Customer, pk=customer_id)

    # customer.order_set is Order's reverse FK accessor -- every order
    # this customer has placed. Each order's own order_total property
    # (djtraders/models.py) sums its line items, so this view just adds
    # those totals together rather than computing revenue itself.
    orders = customer.order_set.order_by("-order_date")
    total_quantity = sum(
        line.quantity for order in orders for line in order.orderdetail_set.all()
    )
    total_revenue = sum(order.order_total for order in orders)

    context = {
        "customer": customer,
        "total_quantity": total_quantity,
        "total_revenue": total_revenue,
        "orders": orders,
    }
    return render(request, "djtraders/customer_detail.html", context)

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
    """
    order = get_object_or_404(Order, pk=order_id)

    # order.orderdetail_set is Django's default reverse accessor name for
    # OrderDetail's FK to Order. select_related("product") fetches each
    # line's Product via a JOIN in this same query, instead of a separate
    # query per line -- worth it since the template touches it every row.
    # Each line's own line_total property (djtraders/models.py) is used
    # directly in the template, no annotation needed here.
    order_lines = order.orderdetail_set.select_related("product")
    context = {"order": order, "order_lines": order_lines}
    return render(request, "djtraders/order_detail.html", context)

def product_detail(request, product_id):
 
    product = get_object_or_404(Product, pk=product_id)
    order_lines = product.orderdetail_set.select_related("order", "order__customer")

    context = {
        "product": product,
        "order_lines": order_lines,
    }
    return render(request, "djtraders/product_detail.html", context)
