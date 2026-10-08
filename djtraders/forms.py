"""
Django Forms for the djtraders app.

A Form (or ModelForm, below) is Django's own way of describing an HTML
form's fields, validation, and rendering as a Python class, instead of
hand-written <input> tags and hand-written checks in the view.
CustomerEditForm below edits a Customer the ModelForm way, rendered by
customer_edit.html through django-crispy-forms' {% crispy %} tag (see
settings.py's INSTALLED_APPS/CRISPY_* settings): it declares its fields
and layout once as a class, and gets validation Django builds in for
free (a required field, a max length) without any hand-written checks
in the view.

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

# Letters, digits, spaces, and hyphens only, 3-10 characters -- loose enough
# for "27402", "02389-673", "H1J 1C3", or "WA1 1DP", tight enough to reject
# obvious garbage. Shared the same way PHONE_PATTERN is: by the widget's
# pattern= attribute (browser layer) and OrderCommitForm.clean_ship_postal_code()
# (server layer), so the two can never quietly drift apart.
POSTAL_CODE_PATTERN = r"[A-Za-z0-9 \-]{3,10}"


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
        # The field grid -- Row/Column are crispy's own layout objects, each
        # Column's css_class a Bootstrap col-md-*. The trailing HTML(...) is
        # the Save button itself (see this class's docstring).
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


class CustomerSignupForm(CustomerEditForm):
    """
    The public "Create a FREE Account" form (customer_signup, djtraders/
    views.py) -- a brand-new customer registering themselves, instead of an
    employee adding one on their behalf (customer_create).

    Built on CustomerEditForm, so every field and every validation rule a
    customer already has (phone format, no digits in the company name or
    city, contact name required, the browser-layer pattern= attributes)
    applies here unchanged. It asks for every column the customers table
    tracks, except the two the system fills in itself: customer_id
    (generated from the company name, Customer.generate_customer_id) and
    inactive_date (left blank, so a new account starts out active).

    What this form adds on top of CustomerEditForm:
      - password is required (the model allows it blank, so that is a form
        rule, the same "form is stricter than the column" shape as
        contact_name), asked for twice, and never echoed back into the page
        after an error (render_value=False). strip=False keeps the
        characters exactly as typed, because customer_login_view compares
        the raw, unstripped password.
      - company_name can't already have an account. The login page picks a
        customer from a dropdown of company names, so two accounts sharing
        a name would be indistinguishable there. Nothing in the database
        enforces this (only customer_id is unique), so this check is the
        only thing that does.
    """
    confirm_password = forms.CharField(
        label="Confirm password",
        max_length=64,
        strip=False,
        widget=forms.PasswordInput(render_value=False),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].required = True
        self.fields["password"].strip = False
        self.fields["password"].widget.render_value = False
        self.fields["password"].widget.attrs["autocomplete"] = "new-password"
        self.fields["confirm_password"].widget.attrs["autocomplete"] = "new-password"

        # Replaces the layout CustomerEditForm.__init__ just built: the same
        # field grid, with the password pair added and Create/Cancel buttons
        # that point at the login page instead of a customer page.
        self.helper.form_id = "customer-signup-form"
        self.helper.layout = Layout(
            Row(
                Column("company_name", css_class="col-md-6"),
                Column("contact_name", css_class="col-md-6"),
            ),
            Row(
                Column("contact_title", css_class="col-md-4"),
                Column("phone", css_class="col-md-4"),
                Column("fax", css_class="col-md-4"),
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
            Row(
                Column("password", css_class="col-md-6"),
                Column("confirm_password", css_class="col-md-6"),
            ),
            HTML(
                """
                <div class="d-flex gap-2 mt-3 justify-content-end">
                    <button type="submit" class="btn dt-btn-primary-customer w3-hover-shadow" title="Create your account">
                        <i class="fa-solid fa-user-plus me-1 dt-icon-success"></i>Create My Account
                    </button>
                    <div class="dt-link-wrap btn dt-btn-secondary-customer w3-hover-shadow">
                        <a href="{% url 'djtraders:customer_login' %}" title="Cancel -- no account will be created">
                            <i class="fa-solid fa-xmark me-1 dt-icon-danger"></i>Cancel
                        </a>
                    </div>
                </div>
                """
            ),
        )

    def clean_company_name(self):
        """
        Server layer of the "one account per company" rule. Runs the
        no-digits check from CustomerEditForm first (super()), then refuses
        a company name that already has an account -- compared
        case-insensitively, so "acme foods" can't sneak past "Acme Foods".
        """
        name = super().clean_company_name()
        if Customer.objects.filter(company_name__iexact=name).exists():
            raise ValidationError(
                "An account for this company already exists -- please log in instead."
            )
        return name

    def clean(self):
        """
        Server layer of the password confirmation. Needs both password
        fields together, so it's a cross-field clean() rather than a
        clean_<field>() -- the same shape as OrderCommitForm.clean().
        """
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm = cleaned_data.get("confirm_password")
        if password and confirm and password != confirm:
            self.add_error("confirm_password", "The two passwords don't match.")
        return cleaned_data


MAX_FREE_DISCOUNT_PERCENT = 10
class OrderDetailForm(forms.ModelForm):
    """
    Adds one line item (product + quantity) to a draft Order.

    Only product/quantity are ever collected from the user; unit_price
    and discount (both required, non-null columns on OrderDetail --
    djtraders/models.py) are set by the view from the chosen product's
    own unit_price and a flat 0.0 discount, not asked for here.
    """
    # Not model fields. OrderDetail.discount is stored as a fraction (0.10 =
    # 10%), so the user types a percent and the view divides by 100. Blank
    # means "leave this product's existing discount alone". Both fields are
    # only shown to employees (order_build.html).
    discount_percent = forms.FloatField(
        required=False, min_value=0, max_value=100, label="Discount (%)"
    )
    manager_approved = forms.BooleanField(required=False, label="Manager approved")

    def __init__(self, *args, in_cart=None, is_employee=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_employee = is_employee
        self.fields["discount_percent"].widget.attrs.update({
            "class": "form-control", "step": "0.01", "min": 0, "max": 100, "placeholder": "0",
        })
        self.fields["manager_approved"].widget.attrs.update({"class": "form-check-input"})
        # {str(product_id): quantity} already in the session cart, so the
        # stock check in clean() counts what's already there.
        self.in_cart = in_cart or {}
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


    def clean_discount_percent(self):
        """
        Server layer, rule 1: only employees can apply a discount at all.
        The template hides the field from customers, but a POST that adds it
        by hand lands here and is refused.
        """
        percent = self.cleaned_data.get("discount_percent")
        if percent and not self.is_employee:
            raise ValidationError("Only an employee can apply a discount.")
        return percent

    def clean(self):
        """
        Server layer of the stock rule (the real check). Needs product and
        quantity together, so it's a cross-field clean() rather than a
        clean_<field>() -- the same shape OrderCommitForm.clean() uses.
        Counts what's already in the cart, since adding the same product
        again bumps the existing line. units_in_stock can be NULL; that's
        treated as 0, since stock that isn't recorded can't be sold.
        There's no database backstop: nothing stops order_details.quantity
        from exceeding products.units_in_stock.
        """
        cleaned_data = super().clean()
        product = cleaned_data.get("product")
        quantity = cleaned_data.get("quantity")
        if product is not None and quantity is not None:
            available = product.units_in_stock or 0
            already = self.in_cart.get(str(product.product_id), 0)
            if already + quantity > available:
                message = f"Only {available} of {product.product_name} in stock"
                if already:
                    message += f" ({already} already in your cart)"
                self.add_error("quantity", message + ".")
        # Server layer, rule 2: staff discounts above the free ceiling also
        # need manager approval. Cross-field (discount + approval together),
        # so it lives in clean() rather than a clean_<field>().
        percent = cleaned_data.get("discount_percent")
        if (
            percent
            and percent > MAX_FREE_DISCOUNT_PERCENT
            and not cleaned_data.get("manager_approved")
        ):
            self.add_error(
                "discount_percent",
                f"Discounts above {MAX_FREE_DISCOUNT_PERCENT}% need manager approval -- "
                'tick "Manager approved".',
            )
        return cleaned_data


class OrderLineQuantityForm(forms.Form):
    """
    Sets the quantity of a line that is already in the cart
    (order_update_line, djtraders/views.py). A plain Form, not a
    ModelForm like OrderDetailForm: the cart is only session state until
    commit, so there is no OrderDetail row to bind to, and the product is
    fixed by the URL -- quantity is the only thing asked for.

    The new quantity REPLACES the old one (OrderDetailForm, by contrast,
    adds to what is already there), so it is checked against the stock on
    its own, not added to what's in the cart.

    Validation layers, same pattern as OrderDetailForm:
      - Browser: min=/max= on the Quantity <input> in _order_line_row.html
        (courtesy).
      - Server: the quantity field's min_value and clean_quantity() (the
        real check) -- at least 1, and no more than units_in_stock.
      - Database: none. order_details.quantity has no CHECK constraint, so
        only this form (and the stock re-check at commit) stops a cart
        line from asking for more than is on hand.
    """
    quantity = forms.IntegerField(
        min_value=1,
        label="Quantity",
        error_messages={
            "required": "Enter a quantity.",
            "invalid": "Quantity must be a whole number.",
            "min_value": "Quantity must be at least 1.",
        },
    )

    def __init__(self, *args, product, **kwargs):
        super().__init__(*args, **kwargs)
        self.product = product

    def clean_quantity(self):
        """
        Server layer of the stock rule. units_in_stock can be NULL; that's
        treated as 0, since stock that isn't recorded can't be sold (same
        as OrderDetailForm.clean()).
        """
        quantity = self.cleaned_data["quantity"]
        available = self.product.units_in_stock or 0
        if quantity > available:
            raise ValidationError(f"Only {available} of {self.product.product_name} in stock.")
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

    The six ship_* fields are the order's ship-to address, which the
    customer can change at commit time. order_build (djtraders/views.py)
    pre-fills them from the customer's own on-file address, so leaving them
    alone ships to the same place as before; order_commit then saves
    whatever was submitted onto the Order, not the customer's address.
    Validation has the usual three layers: browser (the required/pattern
    attributes set in __init__), server (the clean_ship_*() methods below),
    and the database (only the column lengths, which max_length mirrors).
    Name, address, city, and country are required; region and postal code
    stay optional, since many customers on file have no region and not
    every country uses either one.
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

        # Ship-to address. Required: an order has to go somewhere. The model
        # columns are all nullable (blank=True), so "required" is a form rule --
        # the same "form is stricter than the column" shape as employee above.
        # Region and postal code stay optional.
        for name in ("ship_name", "ship_address", "ship_city", "ship_region",
                     "ship_postal_code", "ship_country"):
            self.fields[name].widget.attrs.update({"class": "form-control"})
        for name in ("ship_name", "ship_address", "ship_city", "ship_country"):
            self.fields[name].required = True
        # Browser layer (courtesy only): the same patterns the clean_ship_*()
        # methods below re-check on the server.
        for name, label in (("ship_city", "city"), ("ship_region", "region"),
                            ("ship_country", "country")):
            self.fields[name].widget.attrs.update({
                "pattern": NO_DIGITS_PATTERN,
                "title": f"No numbers in a {label} name.",
            })
        self.fields["ship_postal_code"].widget.attrs.update({
            "pattern": POSTAL_CODE_PATTERN,
            "title": "Letters, numbers, spaces, and hyphens only (3-10 characters).",
        })

    class Meta:
        model = Order
        fields = [
            "employee", "required_date", "shipped_date",
            "ship_name", "ship_address", "ship_city", "ship_region",
            "ship_postal_code", "ship_country",
        ]
        labels = {
            "ship_name": "Name",
            "ship_address": "Address",
            "ship_city": "City",
            "ship_region": "Region",
            "ship_postal_code": "Postal Code",
            "ship_country": "Country",
        }
        widgets = {
            "required_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "shipped_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def _check_no_digits(self, field_name, label):
        """
        Shared by the three place-name checks below -- the same rule
        CustomerEditForm.clean_city() enforces. Blank is fine (region is
        optional, and the required ones are already refused before this runs).
        """
        value = self.cleaned_data.get(field_name, "")
        if value and not re.fullmatch(NO_DIGITS_PATTERN, value):
            raise ValidationError(f"{label} can't contain numbers.")
        return value

    def clean_ship_city(self):
        """Server layer of the no-digits rule for the ship-to city."""
        return self._check_no_digits("ship_city", "City")

    def clean_ship_region(self):
        """Server layer of the no-digits rule for the ship-to region."""
        return self._check_no_digits("ship_region", "Region")

    def clean_ship_country(self):
        """Server layer of the no-digits rule for the ship-to country."""
        return self._check_no_digits("ship_country", "Country")

    def clean_ship_postal_code(self):
        """
        Server layer of the postal-code format rule. Optional: a blank code
        skips the check entirely, the same way CustomerEditForm.clean_phone()
        treats a blank phone. A non-blank code has to match POSTAL_CODE_PATTERN,
        whether or not the browser's own pattern= check ran.
        """
        code = self.cleaned_data.get("ship_postal_code", "")
        if code and not re.fullmatch(POSTAL_CODE_PATTERN, code):
            raise ValidationError(
                "Enter a valid postal code (letters, numbers, spaces, and hyphens only, "
                "3-10 characters)."
            )
        return code

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