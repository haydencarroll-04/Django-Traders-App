"""
Django Forms for the djtraders app.

A Form (or ModelForm, below) is Django's own way of describing an HTML
form's fields, validation, and rendering as a Python class, instead of
hand-written <input> tags. customer_edit_form.html (the "plain" edit
page) skips this entirely -- it reads request.POST fields directly and
writes them onto the Customer instance itself. CustomerEditForm below
is the same edit, built the ModelForm way instead, rendered by
customer_edit.html through django-crispy-forms' {% crispy %} tag (see
settings.py's INSTALLED_APPS/CRISPY_* settings). Both pages render the
identical field grid on purpose, so the real difference stands out:
CustomerEditForm declares its fields and layout once as a class, and
gets validation Django builds in for free (a required field, a max
length) without any hand-written checks in the view.

CustomerEditForm's fields also carry a running example of Django's
three validation layers, each one enforcing the same rule a different
way:
  - Browser layer (courtesy only): an HTML5 pattern=/required/min=
    attribute on the widget, set in __init__ below. Blocks an obviously
    bad value before a request is even sent -- but proves nothing,
    since disabling JS or editing the request in DevTools skips it
    entirely.
  - Server layer (the real check): a clean_<field>() method (or the
    cross-field clean() on OrderCommitForm below) re-checks the same
    rule and raises ValidationError if it fails. This is the one layer
    that can't be bypassed from the browser.
  - Database layer (final backstop, when there is one): a column
    constraint like max_length that Postgres enforces regardless of
    the two layers above. Some rules (no digits in a company name, a
    required contact name) have no database layer behind them at all --
    the schema simply doesn't express that rule, so the form is the
    only thing enforcing it.
phone (clean_phone), company_name/city (clean_company_name/clean_city,
no-digits), and contact_name (required=True override in __init__) are
four small, independent examples of this pattern -- useful as a
template for writing a new business rule elsewhere in the app.
"""
import re

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Column, Layout, Row
from django import forms
from django.core.exceptions import ValidationError

from datetime import date, timedelta

from .models import Category, Customer, Order, OrderDetail, Product, Supplier

# Digits, spaces, parentheses, and dashes only, 7-20 characters -- loose
# enough to accept "(206) 555-9857" or "030-0074321", tight enough to
# reject obvious garbage. Shared by the widget's HTML5 pattern attribute
# (browser layer) and clean_phone() below (server layer), so the two
# can never quietly drift apart.
PHONE_PATTERN = r"[0-9()\-\s]{7,20}"

# No digit characters anywhere -- "[^0-9]*" reads as "zero or more
# non-digit characters," which as a FULL match (see clean_company_name/
# clean_city below, and the pattern= attribute __init__ sets) means "the
# whole string, and there's not a single digit in it." Shared the same
# way PHONE_PATTERN is, between the browser-layer widget attribute and
# the server-layer clean_<field>() checks.
NO_DIGITS_PATTERN = r"[^0-9]*"


class CustomerEditForm(forms.ModelForm):
    """
    Edits every Customer field except customer_id (the primary key --
    ModelForm never includes it unless told to) and inactive_date
    (deliberately left out of Meta.fields below, since it's not part of
    this edit page).

    self.helper (a crispy-forms FormHelper) is what {% crispy form %}
    (customer_edit.html) actually reads to render this form --
    without one, crispy still renders every field, but adds no submit
    button at all, and stacks every field one per row instead of the
    grid self.helper.layout describes below. The HTML(...) at the end
    of that layout is a real, hand-written <button> tag: crispy's own
    Submit/StrictButton layout objects both render a plain <input>,
    which can't hold the icon this project's buttons all carry.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Browser layer of the phone validation example: a real HTML5
        # pattern= on the rendered <input>, using the exact same
        # PHONE_PATTERN clean_phone() checks server-side below, so the
        # two can't silently drift apart. title= is what most browsers
        # show in their own "please match this format" tooltip.
        self.fields["phone"].widget.attrs.update({
            "pattern": PHONE_PATTERN,
            "title": "Digits, spaces, parentheses, and dashes only (7-20 characters).",
        })
        # Browser layer of the no-digits examples. Unlike phone, there's
        # no database constraint backing either of these rules up.
        self.fields["company_name"].widget.attrs.update({
            "pattern": NO_DIGITS_PATTERN,
            "title": "No numbers in a company name.",
        })
        self.fields["city"].widget.attrs.update({
            "pattern": NO_DIGITS_PATTERN,
            "title": "No numbers in a city name.",
        })
        # Contact Name can't be blank. The model itself allows it
        # (contact_name has blank=True, null=True, models.py), so this
        # override is the entire fix, on both layers at once: setting
        # required=True makes Django render a real HTML5 required
        # attribute (browser layer) AND raises "This field is
        # required." during the form's own field-level validation
        # (server layer) -- which runs before any clean_<field>()
        # method, so no separate clean_contact_name() is needed. As
        # with the no-digits fields above, there's no database layer
        # behind this rule -- blank=True/null=True mean Postgres has no
        # opinion either way; only the form enforces it.
        self.fields["contact_name"].required = True
        self.helper = FormHelper()
        # A real id= on the rendered <form>, so customer_edit.html's own
        # {% block scripts %} can target it by id (ValidateCustomerEditForm,
        # DjangoTraders.js) -- crispy renders no id at all by default.
        self.helper.form_id = "customer-edit-form"
        # Same grid as customer_edit_form.html's hand-written <div class="row g-3">
        # -- Row/Column are crispy's own layout objects, each Column's
        # css_class the same Bootstrap col-md-* used there. The trailing
        # HTML(...) is the Save button itself (see this class's docstring).
        self.helper.layout = Layout(
            Row(
                Column("company_name", css_class="col-md-6"),
                Column("contact_name", css_class="col-md-6"),
            ),
            Row(
                Column("contact_title", css_class="col-md-6"),
                Column("phone", css_class="col-md-6"),
            ),
            Row(
                Column("fax", css_class="col-md-6"),
                Column("password", css_class="col-md-6"),
            ),
            Row(
                Column("address", css_class="col-md-8"),
                Column("city", css_class="col-md-4"),
            ),
            Row(
                Column("region", css_class="col-md-4"),
                Column("postal_code", css_class="col-md-4"),
                Column("country", css_class="col-md-4"),
            ),
            HTML(
                """
                <div class="d-flex gap-2 mt-3 justify-content-end">
                    <button type="submit" class="btn dt-btn-primary-customer w3-hover-shadow" title="Save changes">
                        <i class="fa-solid fa-floppy-disk me-1 dt-icon-success"></i>Save
                    </button>
                    <div class="dt-link-wrap btn dt-btn-secondary-customer w3-hover-shadow">
                        {% if new_customer %}
                            <a href="{% url 'djtraders:customer_list' %}" title="Cancel -- nothing has been saved yet">
                                <i class="fa-solid fa-xmark me-1 dt-icon-danger"></i>Cancel
                            </a>
                        {% else %}
                            <a href="{% url 'djtraders:customer_detail' customer.customer_id %}" title="Cancel and discard changes">
                                <i class="fa-solid fa-xmark me-1 dt-icon-danger"></i>Cancel
                            </a>
                        {% endif %}
                    </div>
                </div>
                """
            ),
        )

    class Meta:
        model = Customer
        fields = [
            "company_name",
            "contact_name",
            "contact_title",
            "address",
            "city",
            "region",
            "postal_code",
            "country",
            "phone",
            "fax",
            "password",
        ]
        widgets = {
            "password": forms.PasswordInput(render_value=True),
        }

    def clean_phone(self):
        """
        Server layer of the phone validation example. Django calls
        clean_<field_name>() automatically for any field named this
        way, after that field's own basic type/max_length checks
        already passed and before clean() (there isn't one on this
        class) runs -- this is a hand-written business rule, raising
        ValidationError directly, rather than something Django enforces
        for free.

        phone is optional (blank=True, null=True on the model), so an
        empty value is valid and skips the pattern check entirely --
        only a non-blank value gets held to PHONE_PATTERN. Runs whether
        or not the browser's own pattern= attribute (__init__ above) was
        honored, bypassed, or never sent at all -- a POST straight to
        this view (curl, DevTools, an edited request) hits this exact
        same check.
        """
        phone = self.cleaned_data.get("phone", "")
        if phone and not re.fullmatch(PHONE_PATTERN, phone):
            raise ValidationError(
                "Enter a valid phone number (digits, spaces, parentheses, "
                "and dashes only, 7-20 characters)."
            )
        return phone

    def clean_company_name(self):
        """
        Server layer of the first no-digits example. company_name is
        required (the model's own NOT NULL already guarantees non-blank
        by the time this runs -- Django calls a field's required check
        before clean_<field_name>(), so an actually-blank submission
        never reaches this method), so no blank check is needed here,
        only the digits rule.
        """
        name = self.cleaned_data.get("company_name", "")
        if not re.fullmatch(NO_DIGITS_PATTERN, name):
            raise ValidationError("Company name can't contain numbers.")
        return name

    def clean_city(self):
        """
        Server layer of the second no-digits example. city is optional
        (blank=True, null=True on the model, unlike company_name
        above), so an empty value is valid and skips the digits check
        entirely, the same pattern clean_phone() above already uses.
        """
        city = self.cleaned_data.get("city", "")
        if city and not re.fullmatch(NO_DIGITS_PATTERN, city):
            raise ValidationError("City can't contain numbers.")
        return city


class OrderDetailForm(forms.ModelForm):
    """
    Adds one line item (product + quantity) to a draft Order.

    Only product/quantity are ever collected from the user; unit_price
    and discount (both required, non-null columns on OrderDetail --
    djtraders/models.py) are set by the view from the chosen product's
    own unit_price and a flat 0.0 discount, not asked for here.

    Deliberately does NOT check quantity against the selected product's
    own units_in_stock -- units_in_stock is just an ordinary column,
    with nothing in the schema constraining OrderDetail.quantity
    against it. Adding that check would follow the same pattern as
    CustomerEditForm's clean_phone()/clean_company_name()/clean_city()
    above, except as a cross-field clean() rather than a single-field
    clean_<field>(), since it depends on both product and quantity
    together.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only non-discontinued products are offered -- same reasoning
        # as Product.search's own show_all=False default (models.py).
        self.fields["product"].queryset = self.fields["product"].queryset.filter(
            discontinued=0
        )
        self.fields["product"].empty_label = "Select a product..."
        self.fields["product"].widget.attrs.update({"class": "form-select"})
        # Product (models.py) has no __str__ of its own, so a plain
        # ModelChoiceField would render each <option> as the default
        # "Product object (5)" -- label_from_instance overrides that
        # per-choice display text (not the value actually submitted,
        # which is still just the product's pk) with something a
        # student picking from this dropdown can actually read.
        self.fields["product"].label_from_instance = (
            lambda product: f"{product.product_name} (${product.unit_price or 0:.2f})"
        )
        # Browser layer (courtesy): a real HTML5 min= on the rendered
        # <input>, blocking an obviously-bad quantity (zero or negative)
        # before a request is even sent. Not a guarantee -- same caveat
        # as every other pattern= attribute in this file.
        self.fields["quantity"].widget.attrs.update({"min": 1, "class": "form-control"})

    class Meta:
        model = OrderDetail
        fields = ["product", "quantity"]

    def clean_quantity(self):
        """
        Server layer: quantity has to be a positive number.
        """
        quantity = self.cleaned_data.get("quantity")
        if quantity is not None and quantity < 1:
            raise ValidationError("Quantity must be at least 1.")
        return quantity


class OrderCommitForm(forms.ModelForm):
    """
    Sets an order's employee/required_date/shipped_date at commit time
    -- the one point where a cart becomes a real, placed Order.
    order_date itself is set by the view (order_commit, djtraders/
    views.py), not by this form -- it's always today, on commit, not a
    value anyone picks.

    employee is a real, required field on this form even though the
    model column itself is nullable (Order.employee, models.py,
    SET_NULL) -- required here is a business rule ("every placed order
    needs an employee of record"), not a database constraint, the same
    "form is stricter than the column" shape as everywhere else in this
    file. __init__ below overrides the ModelForm default (a nullable
    model field would otherwise make this field optional on its own)
    and gives it a label_from_instance, the same reason OrderDetailForm's
    product field needs one -- Employee (models.py) has no __str__ of
    its own, so without this override each option would render as
    Django's default "Employee object (5)".

    required_date/shipped_date both come with a sensible default (two
    weeks out / one week out from today) computed in the view and
    passed in as this form's initial= values, but both stay real,
    editable fields -- a business-convention starting guess, not a
    fixed rule.

    Used unbound (no instance=) -- order_commit (djtraders/views.py)
    calls form.save(commit=False) to build a brand-new Order. A
    ModelForm behaves as a create form or an update form purely based
    on whether instance= was passed at construction, not on anything
    declared here.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].required = True
        self.fields["employee"].empty_label = "Select an employee..."
        self.fields["employee"].queryset = self.fields["employee"].queryset.order_by(
            "last_name", "first_name"
        )
        self.fields["employee"].label_from_instance = (
            lambda employee: f"{employee.first_name} {employee.last_name}"
        )
        self.fields["employee"].widget.attrs.update({"class": "form-select"})

    class Meta:
        model = Order
        fields = ["employee", "required_date", "shipped_date"]
        widgets = {
            "required_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "shipped_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def clean(self):
        """
        Same "no database backstop" shape as every other business rule
        in this file: nothing stops Postgres from storing a required/
        shipped date before the order was even placed -- these two
        checks are the only thing that would catch it.
        """
        cleaned_data = super().clean()
        today = date.today()
        for field_name, label in (("required_date", "Required date"), ("shipped_date", "Ship-by date")):
            value = cleaned_data.get(field_name)
            if value is not None and value < today:
                self.add_error(field_name, f"{label} can't be before today's order date.")
        return cleaned_data


def default_required_date():
    """order_date (today, at commit) + 2 weeks -- see OrderCommitForm."""
    return date.today() + timedelta(weeks=2)


def default_shipped_date():
    """order_date (today, at commit) + 1 week -- see OrderCommitForm."""
    return date.today() + timedelta(weeks=1)
class ProductEditForm(forms.ModelForm):
    """
    Create/edit form for a Product, built the same way as CustomerEditForm.
    discontinued/date_discontinued are deliberately NOT fields here --
    they're set by the view (product_create / product_delete).

    Validation layers for the two business rules below:
      - Browser: min= / required attributes set in __init__ (courtesy).
      - Server: clean_unit_price() and clean() (the real check).
      - Database: none. The products table only enforces NOT NULL, the
        primary key, and the supplier/category foreign keys, so these
        rules live only in this form.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Browser layer: price must be at least one cent.
        self.fields["unit_price"].required = True
        self.fields["unit_price"].widget.attrs.update({
            "min": "0.01",
            "step": "0.01",
            "title": "Price must be greater than $0.",
        })
        for name in ("units_in_stock", "units_on_order", "reorder_level"):
            self.fields[name].widget.attrs.update({"min": 0})
        # Models have no __str__, so give the dropdowns readable labels.
        self.fields["supplier"].required = True
        self.fields["supplier"].queryset = Supplier.objects.order_by("company_name")
        self.fields["supplier"].label_from_instance = lambda s: s.company_name
        self.fields["category"].queryset = Category.objects.order_by("category_name")
        self.fields["category"].label_from_instance = lambda c: c.category_name

        self.helper = FormHelper()
        self.helper.form_id = "product-edit-form"
        self.helper.layout = Layout(
            Row(
                Column("product_name", css_class="col-md-8"),
                Column("unit_price", css_class="col-md-4"),
            ),
            Row(
                Column("supplier", css_class="col-md-6"),
                Column("category", css_class="col-md-6"),
            ),
            Row(
                Column("quantity_per_unit", css_class="col-md-6"),
                Column("units_in_stock", css_class="col-md-2"),
                Column("units_on_order", css_class="col-md-2"),
                Column("reorder_level", css_class="col-md-2"),
            ),
            HTML(
                """
                <div class="d-flex gap-2 mt-3 justify-content-end">
                    <button type="submit" class="btn dt-btn-primary-supplier w3-hover-shadow" title="Save changes">
                        <i class="fa-solid fa-floppy-disk me-1 dt-icon-success"></i>Save
                    </button>
                    <div class="dt-link-wrap btn dt-btn-secondary-supplier w3-hover-shadow">
                        {% if new_product %}
                            <a href="{% url 'djtraders:product_list' %}" title="Cancel -- nothing has been saved yet">
                                <i class="fa-solid fa-xmark me-1 dt-icon-danger"></i>Cancel
                            </a>
                        {% else %}
                            <a href="{% url 'djtraders:product_detail' product.product_id %}" title="Cancel and discard changes">
                                <i class="fa-solid fa-xmark me-1 dt-icon-danger"></i>Cancel
                            </a>
                        {% endif %}
                    </div>
                </div>
                """
            ),
        )

    class Meta:
        model = Product
        fields = [
            "product_name",
            "supplier",
            "category",
            "quantity_per_unit",
            "unit_price",
            "units_in_stock",
            "units_on_order",
            "reorder_level",
        ]

    def clean_unit_price(self):
        """
        Server layer of Rule 1: a price must be greater than zero. The
        column allows NULL, zero and negatives, so nothing else would
        stop a $0 or negative product from being saved.
        """
        price = self.cleaned_data.get("unit_price")
        if price is None or price <= 0:
            raise ValidationError("Unit price must be greater than $0.")
        return price

    def clean(self):
        """
        Server layer of Rule 2: the same supplier can't have two products
        with the same name. Needs product_name and supplier together, so
        it's a cross-field clean() rather than a clean_<field>().
        exclude(pk=...) lets an existing product keep its own name when
        it's being edited. (A brand-new product has product_id None, so
        nothing is excluded.)
        """
        cleaned_data = super().clean()
        name = cleaned_data.get("product_name")
        supplier = cleaned_data.get("supplier")
        if name and supplier:
            duplicate = (
                Product.objects.filter(product_name__iexact=name.strip(), supplier=supplier)
                .exclude(pk=self.instance.pk)
                .exists()
            )
            if duplicate:
                self.add_error(
                    "product_name",
                    f"{supplier.company_name} already supplies a product with this name.",
                )
        return cleaned_data

    def clean_units_in_stock(self):
        """Server layer for stock: can't be negative (browser min=0 is only a courtesy)."""
        value = self.cleaned_data.get("units_in_stock")
        if value is not None and value < 0:
            raise ValidationError("Units in stock can't be negative.")
        return value

    def clean_units_on_order(self):
        """Server layer for units on order: can't be negative (browser min=0 is only a courtesy)."""
        value = self.cleaned_data.get("units_on_order")
        if value is not None and value < 0:
            raise ValidationError("Units on order can't be negative.")
        return value

    def clean_reorder_level(self):
        """Server layer for reorder level: can't be negative (browser min=0 is only a courtesy)."""
        value = self.cleaned_data.get("reorder_level")
        if value is not None and value < 0:
            raise ValidationError("Reorder level can't be negative.")
        return value