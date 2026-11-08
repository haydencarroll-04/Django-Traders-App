"""Product pages: the list, a product's detail page, and the cart's autocomplete search."""

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..forms import ProductEditForm
from ..models import Category, Product, Supplier

# region [WHY] LOW_STOCK_THRESHOLD: one named number, not a literal
# product_search_json flags any product with fewer units than this as low
# stock. One constant keeps the rule in a single place if the business changes it.
# endregion
LOW_STOCK_THRESHOLD = 5


def product_list(request):
    """
    The product list, searchable by product name, category and supplier, with an option
    to include discontinued products. Like customer_list, it hands the GET
    parameters to Product.search (models.py), which builds the filter.
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
    return render(request, "djtraders/products/product_list.html", context)


def product_detail(request, product_id):
    """A single product's page: its own fields, plus every order line it appears on."""
    product = get_object_or_404(Product, pk=product_id)

    # orderdetail_set is the reverse accessor for this product's order lines;
    # select_related("order") joins each line's Order in the same query.
    order_lines = product.orderdetail_set.select_related("order").order_by("-order__order_date")
    context = {"product": product, "order_lines": order_lines}
    return render(request, "djtraders/products/product_detail.html", context)


def product_search_json(request):
    """
    JSON for the cart's Product autocomplete. jQuery UI sends the typed text as
    "term" (and the cart's category filter as "category"); this returns up to 10
    non-discontinued matches as {label, value, id, units_in_stock, low_stock}.
    A NULL units_in_stock means stock isn't tracked, so it is never flagged low.
    """
    term = request.GET.get("term", "").strip()
    category_id = request.GET.get("category", "")

    products = Product.objects.filter(discontinued=0, product_name__icontains=term)
    if category_id:
        products = products.filter(category_id=category_id)

    results = []
    for product in products.order_by("product_name")[:10]:
        price = product.unit_price or 0
        results.append(
            {
                "label": f"{product.product_name} (${price:,.2f})",
                "value": product.product_name,
                "id": product.product_id,
                "units_in_stock": product.units_in_stock,
                "low_stock": (
                    product.units_in_stock is not None
                    and product.units_in_stock < LOW_STOCK_THRESHOLD
                ),
            }
        )
    return JsonResponse(results, safe=False)


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
    return render(request, "djtraders/products/product_edit.html", context)


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
    return render(request, "djtraders/products/product_edit.html", context)


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
