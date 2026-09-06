"""
URL configuration for DjangoTraders project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/

Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')

Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')

Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', inclu
"""
from django.contrib import admin
from django.urls import include, path

from . import views

"""
Import the views module from the djtraders app so we can reference its
view functions in our URL patterns.
"""

home_url = path('', views.home, name='home')
"""
GET / -> views.home

This project's own home.html, not an app's -- the entry point to the
whole site.
"""

admin_url = path('admin/', admin.site.urls)
"""
GET /admin/... -> Django's built-in admin site.
"""

djtraders_url = path('djtraders/', include('djtraders.urls'))
"""
Delegate every URL under /djtraders/ to the djtraders app's own
urls.py. This keeps the project-level file short and lets each app own
its own routes as more apps are added later.
"""

urlpatterns = [
    home_url,
    admin_url,
    djtraders_url,
]
