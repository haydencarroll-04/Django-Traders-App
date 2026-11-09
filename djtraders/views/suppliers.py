"""
Supplier pages: the page shell, its four tabs (Dashboard, Info, Order History,
Product Revenue), the dashboard's chart views and the supplier login. A supplier
sees only their own page; employees may open any (see supplier_access_denied in
access.py).
"""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from ..models import Supplier
from .access import supplier_access_denied


def supplier_login_view(request):
    """
    Supplier login: pick a company from a dropdown and enter the shared password
    (Supplier.authenticate, models.py). On success supplier_id goes into the
    session and the supplier lands on their own page. Like the other logins, it
    first logs out whoever was logged in.
    """
    request.session.pop("current_user", None)
    request.session.pop("customer_id", None)
    request.session.pop("supplier_id", None)

    error = None
    if request.method == "POST":
        supplier = Supplier.authenticate(
            request.POST.get("supplier_id", ""), request.POST.get("password", "")
        )
        if supplier is not None:
            request.session["supplier_id"] = supplier.supplier_id
            return redirect("djtraders:supplier_detail", supplier_id=supplier.supplier_id)
        error = "Incorrect supplier/password combination."

    suppliers = Supplier.objects.order_by("company_name")
    return render(request, "djtraders/suppliers/supplier_login.html", {"suppliers": suppliers, "error": error})


def supplier_logout_view(request):
    """Clears "supplier_id" from the session and returns to the home page."""
    request.session.pop("supplier_id", None)
    return redirect("djtraders:home")


def supplier_detail(request, supplier_id):
    """
    The supplier page shell: a header and a tab control (Dashboard, Info,
    Order History, Product Revenue), each tab a partial loaded by AJAX like the customer page.
    A visitor goes to the supplier login; a supplier asking for another
    supplier's page is sent back to their own.
    """
    logged_in_supplier_id = request.session.get("supplier_id")
    if logged_in_supplier_id and logged_in_supplier_id != supplier_id:
        return redirect("djtraders:supplier_detail", supplier_id=logged_in_supplier_id)
    if supplier_access_denied(request, supplier_id):
        return redirect("djtraders:supplier_login")
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    return render(request, "djtraders/suppliers/supplier_detail.html", {"supplier": supplier})


def supplier_info(request, supplier_id):
    """Info tab: contact details and headline numbers."""
    if supplier_access_denied(request, supplier_id):
        return HttpResponse(status=403)
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    return render(request, "djtraders/suppliers/_supplier_info.html", {
        "supplier": supplier,
        "summary": supplier.summary(),
    })


def supplier_orders(request, supplier_id):
    """Order History tab: placed orders that include this supplier's products."""
    if supplier_access_denied(request, supplier_id):
        return HttpResponse(status=403)
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    return render(request, "djtraders/suppliers/_supplier_orders.html", {
        "supplier": supplier,
        "orders": supplier.order_history(),
    })


def supplier_products(request, supplier_id):
    """Product Revenue tab: a table of units and revenue per product."""
    if supplier_access_denied(request, supplier_id):
        return HttpResponse(status=403)
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    return render(request, "djtraders/suppliers/_supplier_products.html", {
        "supplier": supplier,
        "rows": supplier.product_revenue(),
    })


# region [CONCEPT] the dashboard's controls
# The Dashboard tab is one partial. Each chart that has a control also has a view
# below that returns just that chart's HTML; the control's JavaScript (suppliers.js)
# fetches it and swaps it into the page, so a change never reloads the page. The
# supplier is always the one in the session or an employee viewing that supplier's
# page (supplier_access_denied); no view takes a supplier from a query string.
# Values from the browser are checked against fixed lists before they are used.
# endregion
def supplier_dashboard(request, supplier_id):
    """
    Dashboard tab: the four summary cards, revenue by year, monthly revenue (its
    year dropdown loads the chart itself), the category charts, top products, top
    customers, the comparison with all suppliers and, last, the chart that asks where
    the supplier's sales come from (by customer country). The first version of each
    chart that has a control arrives already drawn; its control swaps it later.
    """
    if supplier_access_denied(request, supplier_id):
        return HttpResponse(status=403)
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    context = {
        "supplier": supplier,
        "stats": supplier.dashboard_stats(),
        "annual_plot": supplier.annual_revenue_plot(),
        "order_years": supplier.order_years(),
        "category_revenue_plot": supplier.category_revenue_plot(),
        "category_units_plot": supplier.category_units_plot(),
        "top_products_plot": supplier.top_products_plot(),
        "top_measures": Supplier.TOP_MEASURES,
        "top_customers": supplier.top_customers(),
        "comparison_plot": supplier.comparison_plot(),
        "comparison_measures": Supplier.SUPPLIER_MEASURES,
        "country_plot": supplier.country_sales_plot(),
        "country_measures": Supplier.COUNTRY_MEASURES,
    }
    return render(request, "djtraders/suppliers/_supplier_dashboard.html", context)


def supplier_monthly_chart(request, supplier_id):
    """The monthly chart's Year dropdown: Supplier.monthly_revenue_plot for ?year=, as just the chart HTML."""
    if supplier_access_denied(request, supplier_id):
        return HttpResponse(status=403)
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    year = supplier.parse_year(request.GET.get("year", ""))
    if not year:
        return HttpResponse("Choose a valid year.", status=400)
    return HttpResponse(supplier.monthly_revenue_plot(year) or "<p>No orders on record.</p>")


def supplier_category_charts(request, supplier_id):
    """
    The category section's controls (?year= a year or "all", ?kind= bar or pie for
    the unit share): both category charts together, as the HTML that fills
    #dashboard-categories, so one control changes both.
    """
    if supplier_access_denied(request, supplier_id):
        return HttpResponse(status=403)
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    year = supplier.parse_year(request.GET.get("year", "all"))
    kind = request.GET.get("kind", "bar")
    if year is False or kind not in ("bar", "pie"):
        return HttpResponse("Choose a valid year and chart.", status=400)
    return render(request, "djtraders/suppliers/_supplier_category_charts.html", {
        "category_revenue_plot": supplier.category_revenue_plot(year),
        "category_units_plot": supplier.category_units_plot(year, kind),
    })


def supplier_top_products_chart(request, supplier_id):
    """
    The top-products chart for ?top= (5, 10 or 20), ?measure= (revenue or quantity) and
    ?discontinued= (1 to include discontinued products), as just the chart HTML. The top
    and measure are checked against fixed lists. The chart's title names the top asked
    for, and says how many products have sales when that is fewer.
    """
    if supplier_access_denied(request, supplier_id):
        return HttpResponse(status=403)
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    top = request.GET.get("top", "10")
    measure = request.GET.get("measure", "revenue")
    if top not in ("5", "10", "20") or measure not in Supplier.TOP_MEASURES:
        return HttpResponse("Choose a valid top and measure.", status=400)
    plot = supplier.top_products_plot(
        int(top), measure, include_discontinued=request.GET.get("discontinued") == "1"
    )
    return HttpResponse(plot or "<p>No products to show.</p>")


def supplier_comparison_chart(request, supplier_id):
    """The comparison's Compare dropdown: Supplier.comparison_plot for ?measure=, as just the chart HTML."""
    if supplier_access_denied(request, supplier_id):
        return HttpResponse(status=403)
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    measure = request.GET.get("measure", "revenue")
    if measure not in Supplier.SUPPLIER_MEASURES:
        return HttpResponse("Choose a valid measure.", status=400)
    return HttpResponse(supplier.comparison_plot(measure) or "<p>Nothing to compare yet.</p>")


def supplier_country_chart(request, supplier_id):
    """
    The where-do-my-sales-come-from chart for ?year= (a year or "all") and ?measure=
    (revenue, units or orders), as just the chart HTML. Both are checked: the year
    against this supplier's years, the measure against Supplier.COUNTRY_MEASURES.
    """
    if supplier_access_denied(request, supplier_id):
        return HttpResponse(status=403)
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    year = supplier.parse_year(request.GET.get("year", "all"))
    measure = request.GET.get("measure", "revenue")
    if year is False or measure not in Supplier.COUNTRY_MEASURES:
        return HttpResponse("Choose a valid year and measure.", status=400)
    return HttpResponse(supplier.country_sales_plot(year, measure) or "<p>No orders on record.</p>")
