"""
URL configuration for the djtraders app.

Each Django *app* gets its own urls.py so its routes stay self-contained;
the project-level urls.py (DjangoTraders/urls.py) "includes" this file
under a prefix.

  1. Added product_list_url
        Same shape as customer_list_url, routing to views.product_list.

  2. Added customer_detail_url
        Captures the row's primary key in the URL path (e.g.
        /djtraders/customers/ALFKI/) and passes it to the matching view.

  3. Added order_detail_url
        Same shape, routing /djtraders/orders/<order_id>/ to
        views.order_detail with an <int:...> converter.

  4. Removed product_detail_url
        product_detail (view, template, and this route) is left as an
        assignment component -- students build it themselves.
"""
from django.urls import path

from . import views

# NAMESPACE for every route below -- lets templates/reverse() use
# "djtraders:customer_list" instead of a bare "customer_list", avoiding
# name collisions as more apps are added.
app_name = "djtraders"

# GET /djtraders/ -> views.home. An empty path means "the root of
# whatever prefix this urls.py was include()'d under" (djtraders/).
home_url = path("", views.home, name="home")

# GET /djtraders/customers/ -> views.customer_list
customer_list_url = path("customers/", views.customer_list, name="customer_list")

# GET /djtraders/products/ -> views.product_list
product_list_url = path("products/", views.product_list, name="product_list")

# "<str:customer_id>" is a path converter: matches a non-slash segment
# and passes it to the view as customer_id (str, matching Customer's
# CharField primary key -- an int converter would reject "ALFKI").
customer_detail_url = path(
    "customers/<str:customer_id>/", views.customer_detail, name="customer_detail"
)

# <int:order_id> -- Order.order_id is an integer PK.
order_detail_url = path(
    "orders/<int:order_id>/", views.order_detail, name="order_detail"
)

# GET /djtraders/products/<product_id>/ -> views.product_detail
product_detail_url = path(
    "products/<int:product_id>/", views.product_detail, name="product_detail"
)      

urlpatterns = [
    home_url,
    customer_list_url,
    product_list_url,
    customer_detail_url,
    order_detail_url,
    product_detail_url,
]
