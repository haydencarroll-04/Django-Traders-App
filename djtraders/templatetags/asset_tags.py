"""
Template tags for the djtraders app -- loaded in a template by this
file's name (asset_tags), e.g. at the top of templates/common/base.html.

Django finds a tag library by file name inside an installed app's
templatetags/ folder (unlike a context processor, which is found by the
dotted path in settings.py), so the folder, its __init__.py, and the name
asset_tags.py all have to be spelled exactly this way. The development
server must be restarted once after a new templatetags module is added
before a template can load it.
"""
import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def versioned_static(path):
    """
    The same URL the built-in static tag gives for this file, plus
    "?v=<the file's last-modified time>".

    Why: the browser keeps its own saved copy of DjangoTraders.js and
    DjangoTraders.css, and Django's development server doesn't say how
    long that copy is good for -- so a browser is free to keep using it
    for hours after the file changes. A page can then pair new HTML with
    an old script that doesn't know about it (e.g. the cart's Update
    button next to a DjangoTraders.js from before UpdateCartQuantities
    existed). A changed file has a new modified time, so a new URL, which
    the browser has to fetch fresh; an unchanged file keeps the same URL
    and stays cached as usual.

    A path Django can't find on disk just gets the plain static URL.
    """
    url = static(path)
    found = finders.find(path)
    if found:
        url += f"?v={int(os.path.getmtime(found))}"
    return url
