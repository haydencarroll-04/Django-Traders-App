"""
Order pages and the shopping cart.

A customer's in-progress order lives in request.session["cart"], a plain dict
with no database row, until order_commit writes it out as a real Order plus its
OrderDetail rows inside one transaction. order_create, order_build,
order_add_line, order_remove_line, order_clear_cart and order_commit walk
through that flow; every one is open to the cart's own customer or to any
employee (customer_access_denied in access.py). order_delete cancels an
already-placed order on the day it was placed.
"""

from types import SimpleNamespace

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from ..forms import (
    OrderCommitForm,
    OrderDetailForm,
    OrderLineQuantityForm,
    default_required_date,
    default_shipped_date,
)
from ..models import Category, Customer, Order, OrderDetail, Product
from .access import customer_access_denied, order_access_denied


def order_detail(request, order_id):
    """
    A single order: its info, shipping details, customer and line items. The
    page follows the Order model in every direction: order.customer, employee
    and ship_via are forward foreign keys, and the lines are the reverse
    relationship (order.orderdetail_set), each reaching its Product and that
    Product's Supplier through another forward key.

    Anyone may view the page. Only Cancel Order (order_delete) is gated, so
    can_cancel_order is computed here: a placed order from today, for the
    order's own customer or an employee.
    """
    order = get_object_or_404(Order, pk=order_id)

    # select_related("product__supplier") fetches every line's Product and
    # Supplier in this one query, instead of one extra query per line.
    order_lines = order.orderdetail_set.select_related("product__supplier")

    can_cancel_order = order.order_date == timezone.now().date() and not order_access_denied(
        request, order
    )

    context = {
        "order": order,
        "order_lines": order_lines,
        "can_cancel_order": can_cancel_order,
    }
    return render(request, "djtraders/orders/order_detail.html", context)


def order_delete(request, order_id):
    """
    Cancels a placed order with a real DELETE (OrderDetail's CASCADE removes its
    lines), but only on the day it was placed; order_date is the placed flag and
    is never touched after commit. A still-open cart (order_date is None) is
    refused. Open to the order's own customer or an employee. There is no
    confirm step, like Commit Order. order_detail only shows the button when this
    would succeed; any other way here (a stale page, a typed URL) fails the same
    checks and is redirected back.
    """
    order = get_object_or_404(Order, pk=order_id)

    if order_access_denied(request, order):
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


# Ordering more than this many units of one product earns an automatic discount.
VOLUME_DISCOUNT_THRESHOLD = 10
VOLUME_DISCOUNT_RATE = 0.10


def _cart_lines(cart):
    """
    Turns the session cart's "lines" dict into a list of OrderDetail-shaped
    objects (.product, .unit_price, .quantity, .discount, .discount_percent,
    .line_total, .is_volume_discount). A SimpleNamespace stands in for a model instance, since a cart
    that is abandoned never gets a real OrderDetail row, but the line template
    and the running total are built the same either way.

    Each line stores a quantity and a discount, the discount as the same 0.0-1.0
    fraction OrderDetail.discount uses (order_add_line converts the form's
    percentage once); discount_percent exists only for display. unit_price is the
    product's current price, looked up on every call, including at commit. A
    product that no longer exists is skipped.
    """
    product_ids = [int(product_id) for product_id in cart.get("lines", {})]
    products_by_id = Product.objects.in_bulk(product_ids)

    lines = []
    for product_id_str, line_data in cart.get("lines", {}).items():
        product = products_by_id.get(int(product_id_str))
        if product is None:
            continue
        quantity = line_data["quantity"]
        manual_discount = line_data["discount"]
        volume_discount = VOLUME_DISCOUNT_RATE if quantity > VOLUME_DISCOUNT_THRESHOLD else 0.0
        discount = max(manual_discount, volume_discount)
        unit_price = product.unit_price or 0.0
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


def order_create(request, customer_id):
    """
    Starts (or resumes) this customer's cart in request.session["cart"], then
    goes to order_build. POST only, because it writes session data. A cart is
    reused only if it already belongs to this customer_id; otherwise a fresh
    empty one replaces it, so a different customer on the same browser never sees
    someone else's leftovers. There is at most one open cart per browser session.
    """
    if customer_access_denied(request, customer_id):
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    if request.method != "POST":
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    cart = request.session.get("cart")
    if not cart or cart.get("customer_id") != customer_id:
        request.session["cart"] = {"customer_id": customer_id, "lines": {}}

    return redirect("djtraders:order_build", customer_id=customer_id)


def _add_to_cart_context(request, customer, category_id=""):
    """
    Everything the Add to Cart card (_order_add_card.html) needs, as one dict,
    shared by the four views that render it. category_id narrows the Product
    search the way product_list's Category filter does; "" means every
    non-discontinued product. product_stock is {product_id: units_in_stock} for
    those products, embedded in the page so orders.js can block a too-large
    quantity early; OrderDetailForm.clean() (forms.py) is the real check.
    """
    detail_form = OrderDetailForm(
        category_id=category_id,
        employee_initiated=bool(request.session.get("current_user")),
    )
    return {
        "customer": customer,
        "detail_form": detail_form,
        "categories": Category.objects.order_by("category_name"),
        "search_category_id": category_id,
        "product_stock": dict(
            detail_form.fields["product"].queryset.values_list("product_id", "units_in_stock")
        ),
    }


def order_add_card(request, customer_id):
    """
    AJAX endpoint behind the cart's Filter by Category dropdown: returns just the
    Add to Cart card, rendered for the "category" GET parameter (empty means all),
    which orders.js swaps in. It reads nothing from the cart and writes nothing.
    """
    if customer_access_denied(request, customer_id):
        return HttpResponse("Not allowed.", status=403)

    customer = get_object_or_404(Customer, pk=customer_id)
    return render(
        request,
        "djtraders/orders/_order_add_card.html",
        _add_to_cart_context(request, customer, category_id=request.GET.get("category", "")),
    )


def order_build(request, customer_id):
    """
    The shopping cart page. There is no Order row until commit: the page is built
    from request.session["cart"] (see _cart_lines) and a fresh Customer lookup. A
    missing cart, or one for another customer, is started here, so a typed or
    bookmarked URL still reaches a working page.

    The Place Order form starts with the customer's on-file name and address and
    default dates, all editable (OrderCommitForm and its default_* helpers in
    forms.py). It requires an employee, a business rule rather than a database one.
    """
    if customer_access_denied(request, customer_id):
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    customer = get_object_or_404(Customer, pk=customer_id)

    cart = request.session.get("cart")
    if not cart or cart.get("customer_id") != customer_id:
        cart = {"customer_id": customer_id, "lines": {}}
        request.session["cart"] = cart

    cart_lines = _cart_lines(cart)
    cart_total = sum(line.line_total for line in cart_lines)
    commit_form = OrderCommitForm(
        initial={
            "required_date": default_required_date(),
            "shipped_date": default_shipped_date(),
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
        "commit_form": commit_form,
        **_add_to_cart_context(request, customer),
    }
    return render(request, "djtraders/orders/order_build.html", context)


def order_add_line(request, customer_id):
    """
    AJAX endpoint behind the Add to Cart form (orders.js): adds a product and
    quantity to request.session["cart"]["lines"], or raises the quantity of a
    product already there. Returns JSON, not a redirect, so the page never
    reloads while lines are added.

    On success the JSON carries row_html (the line's table row), card_html (a
    fresh, empty Add to Cart card) and the new total. A validation failure
    returns only error messages, so the user keeps what they typed. unit_price is
    never submitted: _cart_lines prices every line fresh. Stock and the discount
    ceiling (10% for a customer's own cart, 100% when an employee is driving it)
    are checked by OrderDetailForm (forms.py).
    """
    if customer_access_denied(request, customer_id):
        return JsonResponse({"success": False, "errors": {"__all__": ["Not allowed."]}}, status=403)

    cart = request.session.get("cart")
    if not cart or cart.get("customer_id") != customer_id:
        return JsonResponse(
            {"success": False, "errors": {"__all__": ["Your cart isn't open anymore -- reload the page."]}},
            status=400,
        )

    employee_initiated = bool(request.session.get("current_user"))
    form = OrderDetailForm(request.POST, employee_initiated=employee_initiated)
    if not form.is_valid():
        # get_json_data() gives plain {field: [{"message", "code"}]} dicts, which
        # JsonResponse can encode; Django's own ErrorDict cannot be.
        return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

    product = form.cleaned_data["product"]
    quantity = form.cleaned_data["quantity"]
    # The form validates the typed percentage; it becomes the 0.0-1.0 fraction
    # OrderDetail.discount uses here, once.
    discount = form.cleaned_data["discount_percent"] / 100

    product_key = str(product.product_id)
    existing = cart["lines"].get(product_key, {"quantity": 0, "discount": 0.0})
    # Adding a product again sums the quantity but replaces the discount: a line
    # has one discount, not one per click.
    cart["lines"][product_key] = {
        "quantity": existing["quantity"] + quantity,
        "discount": discount,
    }
    # Changing cart["lines"] in place isn't noticed by the session, so say so.
    request.session.modified = True

    cart_lines = _cart_lines(cart)
    line = next(line for line in cart_lines if line.product.product_id == product.product_id)
    row_html = render_to_string(
        "djtraders/orders/_order_line_row.html",
        {"line": line, "customer_id": customer_id},
        request=request,
    )
    cart_total = sum(line.line_total for line in cart_lines)
    # A fresh, empty card: what "starting over" looks like is decided here, not
    # by JavaScript clearing fields one at a time.
    customer = get_object_or_404(Customer, pk=customer_id)
    card_html = render_to_string(
        "djtraders/orders/_order_add_card.html",
        _add_to_cart_context(request, customer),
        request=request,
    )
    return JsonResponse(
        {
            "success": True,
            "row_html": row_html,
            "card_html": card_html,
            "product_id": product.product_id,
            "order_total": f"{cart_total:,.2f}",
        }
    )


def order_commit(request, customer_id):
    """
    Places the cart: the one point where anything is written to the database.
    Inside one transaction it saves an Order (employee, dates and ship_* from
    OrderCommitForm; order_date is today), one OrderDetail per cart line, and
    subtracts each line's quantity from the product's units_in_stock, so either
    all of it is written or none. The session cart is cleared only after that
    succeeds.

    Stock is re-read from the database and checked again first, because the check
    made when a line was added may be out of date; any shortfall (stock_errors)
    cancels the whole commit. A missing or empty cart goes back to order_build.
    """
    if customer_access_denied(request, customer_id):
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
    # The stock each cart line carries was current when the line was added, not
    # necessarily now, so it is re-read here, right before anything is written.
    fresh_products = Product.objects.in_bulk(
        [line.product.product_id for line in cart_lines]
    )
    stock_errors = []
    for line in cart_lines:
        product = fresh_products[line.product.product_id]
        if product.units_in_stock is not None and line.quantity > product.units_in_stock:
            stock_errors.append(
                f"Only {product.units_in_stock} of {product.product_name} left in stock."
            )

    if form.is_valid() and not stock_errors:
        # ship_* is one of OrderCommitForm's own fields, so save(commit=False)
        # already set it from what was submitted.
        order = form.save(commit=False)
        order.customer = customer
        order.order_date = timezone.now().date()

        with transaction.atomic():
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
                product = fresh_products[line.product.product_id]
                if product.units_in_stock is not None:
                    product.units_in_stock -= line.quantity
                    product.save(update_fields=["units_in_stock"])

        del request.session["cart"]
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    cart_total = sum(line.line_total for line in cart_lines)
    context = {
        "customer": customer,
        "cart_lines": cart_lines,
        "cart_total": cart_total,
        "commit_form": form,
        "stock_errors": stock_errors,
        **_add_to_cart_context(request, customer),
    }
    return render(request, "djtraders/orders/order_build.html", context)


def order_remove_line(request, customer_id, product_id):
    """
    Removes one product line from the cart entirely. It only pops product_id out
    of request.session["cart"]["lines"]; there is no database row before commit.
    POST only, like the other cart-changing views.
    """
    if customer_access_denied(request, customer_id):
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    if request.method != "POST":
        return redirect("djtraders:order_build", customer_id=customer_id)

    cart = request.session.get("cart")
    if cart and cart.get("customer_id") == customer_id:
        cart["lines"].pop(str(product_id), None)
        request.session.modified = True

    return redirect("djtraders:order_build", customer_id=customer_id)


def order_clear_cart(request, customer_id):
    """
    Empties the cart without committing it, like order_remove_line but for every
    line, with the same one-click, no-confirm convention.
    """
    if customer_access_denied(request, customer_id):
        return redirect("djtraders:customer_detail", customer_id=customer_id)

    if request.method != "POST":
        return redirect("djtraders:order_build", customer_id=customer_id)

    cart = request.session.get("cart")
    if cart and cart.get("customer_id") == customer_id:
        cart["lines"] = {}
        request.session.modified = True

    return redirect("djtraders:order_build", customer_id=customer_id)


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

    if customer_access_denied(request, customer_id):
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

    cart["lines"][product_key]["quantity"] = form.cleaned_data["quantity"]
    # Mutating the nested dict in place isn't noticed by the session
    # middleware on its own -- same reason order_add_line sets this.
    request.session.modified = True

    if not wants_json:
        return redirect("djtraders:order_build", customer_id=customer_id)

    cart_lines = _cart_lines(cart)
    line = next(line for line in cart_lines if line.product.product_id == product_id)
    row_html = render_to_string(
        "djtraders/orders/_order_line_row.html",
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
