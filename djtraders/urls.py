"""
URL configuration for the djtraders app.

Each Django *app* (as opposed to the overall *project*) gets its own
urls.py so that its routes stay self-contained. The project-level
urls.py (DjangoTraders/urls.py) then "includes" this file under a
prefix, keeping app routes decoupled from the project's top-level path
structure.
"""
from django.urls import path

from . import views

app_name = "djtraders"  # <-- NAMESPACE for every route in this file
"""
app_name lets templates/reverse() refer to these routes as
"djtraders:customer_list" instead of a bare "customer_list". This
avoids name collisions as more apps are added to the project.
"""

home_url = path("", views.home, name="home")  # <-- NAME: "home"
"""
GET /djtraders/ -> views.home

An empty string here means "the root of whatever prefix this urls.py
was include()'d under" -- since DjangoTraders/urls.py includes this
file at "djtraders/", this route ends up being /djtraders/ exactly,
i.e. the app's home page.

Referenced in templates as "djtraders:home" -- NAMESPACE (app_name,
above) + NAME ("home", set right here) joined with a colon.
"""

customer_list_url = path(
    "customers/",
    views.customer_list,
    name="customer_list"  # <-- NAME: "customer_list"
  )
"""
GET /djtraders/customers/ -> views.customer_list

name="customer_list" is the identifier used with the url tag in
templates and reverse() in Python, so the URL string itself can change
later without breaking references to it.

Referenced in templates as "djtraders:customer_list" -- NAMESPACE
(app_name, above) + NAME ("customer_list", set right here).
"""

urlpatterns = [
    home_url,
    customer_list_url,
]
