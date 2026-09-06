"""
Project-level views for DjangoTraders.

Unlike djtraders/views.py, this file isn't inside a Django *app* --
it's a small views.py living alongside the project's settings.py and
urls.py. That's a deliberate choice for a single "site home page" that
isn't really part of any one app's feature set; it's the entry point
to the whole project. If more project-wide pages are needed later,
this is where they'd go too.
"""
from django.shortcuts import render


def home(request):
    """
    Project home page.

    Links into the djtraders app's own home page. As more apps join
    the project, this page becomes the index that lists all of them.
    """
    # render(request, template_name) -- see djtraders/views.py's home()
    # for the full breakdown of these arguments. The one difference
    # worth noting here: "home.html" (no "djtraders/" prefix) is found
    # via TEMPLATES['DIRS'] in settings.py, the project-level templates
    # folder, not via any app's own templates/ folder (APP_DIRS=True).
    return render(request, "home.html")
