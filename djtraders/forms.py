"""
The app's forms. A Form (or ModelForm) describes an HTML form's fields, validation
and rendering as a Python class instead of hand-written <input> tags.
CustomerEditForm is drawn by customer_edit.html with django-crispy-forms' crispy
tag (see INSTALLED_APPS and the CRISPY_* settings).

The customer form's fields show Django's three validation layers, each enforcing
the same rule a different way:
  - Browser (courtesy only): an HTML5 pattern=, required or min= attribute on the
    widget. It blocks an obviously bad value before a request is sent, but proves
    nothing, since DevTools or disabled JavaScript skips it.
  - Server (the real check): a clean_<field>() method, or the cross-field clean(),
    re-checks the rule and raises ValidationError. Nothing in the browser can
    bypass it.
  - Database (a backstop, when there is one): a column constraint such as
    max_length. Some rules, like no digits in a company name, have no database
    layer, so the form is the only thing enforcing them.
"""
import re
from datetime import timedelta

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Column, Layout, Row
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Category, Customer, Order, OrderDetail, Product, Supplier

# region [WHY] patterns shared by the browser and server layers
# Digits, spaces, parentheses and dashes, 7-20 characters: loose enough for
# "(206) 555-9857", tight enough to reject garbage. The widget's pattern= attribute
# and clean_phone() both use it, so the two can't drift apart.
# endregion
PHONE_PATTERN = r"[0-9()\-\s]{7,20}"

# region [CONCEPT] NO_DIGITS_PATTERN
# "[^0-9]*" means zero or more non-digit characters, so as a full match it says
# the whole string contains no digit. Shared the same way as PHONE_PATTERN.
# endregion
NO_DIGITS_PATTERN = r"[^0-9]*"


class CustomerEditForm(forms.ModelForm):
    """
    Edits every Customer field except customer_id (the primary key) and
    inactive_date (not part of this page).

    self.helper, a crispy FormHelper, is what the crispy tag reads to draw the
    grid and the Save button; without one crispy stacks the fields and adds no
    button. The Save and Cancel buttons are hand-written HTML because crispy's own
    Submit objects render a plain <input>, which can't hold an icon.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Browser layer: pattern= repeats PHONE_PATTERN, and title= is the tooltip
        # browsers show on a mismatch.
        self.fields["phone"].widget.attrs.update({
            "pattern": PHONE_PATTERN,
            "title": "Digits, spaces, parentheses, and dashes only (7-20 characters).",
        })
        # The no-digits fields have no database constraint behind them either.
        self.fields["company_name"].widget.attrs.update({
            "pattern": NO_DIGITS_PATTERN,
            "title": "No numbers in a company name.",
        })
        self.fields["city"].widget.attrs.update({
            "pattern": NO_DIGITS_PATTERN,
            "title": "No numbers in a city name.",
        })
        # The model allows a blank contact_name; required=True makes the form insist,
        # in the browser (required attribute) and on the server.
        self.fields["contact_name"].required = True
        self.helper = FormHelper()
        # A real id on the <form>, so ValidateCustomerEditForm (customers.js) can
        # find it; crispy renders none by default.
        self.helper.form_id = "customer-edit-form"
        # The field grid: Row and Column are crispy layout objects, each Column a
        # Bootstrap col-md-* width.
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
                    <button type="submit" class="btn dt-btn-primary-customer dt-hover-shadow" title="Save changes">
                        <i class="fa-solid fa-floppy-disk me-1 dt-icon-success"></i>Save
                    </button>
                    <div class="dt-link-wrap btn dt-btn-secondary-customer dt-hover-shadow">
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
        Server layer for phone. Django calls clean_<field>() after the field's own
        type and length checks pass; this hand-written business rule raises
        ValidationError. phone is optional, so a blank value skips the pattern check.
        It runs even when the browser's pattern= was bypassed (curl, DevTools).
        """
        phone = self.cleaned_data.get("phone", "")
        if phone and not re.fullmatch(PHONE_PATTERN, phone):
            raise ValidationError(
                "Enter a valid phone number (digits, spaces, parentheses, "
                "and dashes only, 7-20 characters)."
            )
        return phone

    def clean_company_name(self):
        """Server layer: no digits. company_name is required, and Django checks that before this runs."""
        name = self.cleaned_data.get("company_name", "")
        if not re.fullmatch(NO_DIGITS_PATTERN, name):
            raise ValidationError("Company name can't contain numbers.")
        return name

    def clean_city(self):
        """Server layer: no digits. city is optional, so a blank value skips the check, as in clean_phone."""
        city = self.cleaned_data.get("city", "")
        if city and not re.fullmatch(NO_DIGITS_PATTERN, city):
            raise ValidationError("City can't contain numbers.")
        return city


class OrderDetailForm(forms.ModelForm):
    """
    Adds one line item (product, quantity, discount) to the cart. Only those three
    are collected; unit_price comes from the product's current price, not the form.

    discount_percent is a plain form field, not a model field, because the units
    differ: a customer types a percentage ("10") while OrderDetail.discount stores
    a fraction (0.10). The view (order_add_line) divides by 100 once validation
    passes.

    Up to 10% is accepted from anyone; only a cart an employee is driving
    (employee_initiated=True, from the session) may go as high as 100%. clean()
    checks quantity against the product's units_in_stock, a cross-field rule that
    needs product and quantity together. It is a courtesy check at add-to-cart time;
    order_commit (views/orders.py) re-checks against current stock before writing the
    order. category_id narrows the product choices to one category; it is optional
    because order_commit's error re-render builds this form without one.
    """
    discount_percent = forms.FloatField(
        required=False, initial=0, label="Discount %"
    )

    def __init__(self, *args, category_id=None, employee_initiated=False, **kwargs):
        super().__init__(*args, **kwargs)
        # clean_discount_percent reads this flag to pick the 10% or 100% ceiling.
        self.employee_initiated = employee_initiated

        # Only non-discontinued products are offered, like Product.search's default.
        products = self.fields["product"].queryset.filter(discontinued=0)
        if category_id:
            products = products.filter(category_id=category_id)
        self.fields["product"].queryset = products
        # region [CONCEPT] hidden product field
        # The autocomplete box (product_search_json) writes the chosen product's pk
        # into this hidden field. The queryset above is still the server-side gate: a
        # missing or discontinued pk fails validation whatever the browser sent.
        # endregion
        self.fields["product"].widget = forms.HiddenInput()
        self.fields["product"].error_messages["invalid_choice"] = (
            "Pick a product from the suggestions -- that one isn't available."
        )
        # Browser layer: min=1 blocks a zero or negative quantity before the request.
        self.fields["quantity"].widget.attrs.update({"min": 1, "class": "form-control"})
        # Starts at 1, the value the fresh card shows after each add.
        self.fields["quantity"].initial = 1
        # max= matches the ceiling clean_discount_percent enforces, so an employee's
        # cart shows a wider allowed range.
        self.fields["discount_percent"].widget.attrs.update({
            "min": 0,
            "max": 100 if employee_initiated else 10,
            "step": "0.01",
            "class": "form-control",
        })

    class Meta:
        model = OrderDetail
        fields = ["product", "quantity"]

    def clean_quantity(self):
        """Server layer: quantity must be at least 1."""
        quantity = self.cleaned_data.get("quantity")
        if quantity is not None and quantity < 1:
            raise ValidationError("Quantity must be at least 1.")
        return quantity

    def clean_discount_percent(self):
        """Server layer for the discount ceiling (see the class docstring). A blank field counts as 0."""
        discount_percent = self.cleaned_data.get("discount_percent")
        if discount_percent is None:
            return 0.0
        if discount_percent < 0:
            raise ValidationError("Discount can't be negative.")
        ceiling = 100 if self.employee_initiated else 10
        if discount_percent > ceiling:
            raise ValidationError(
                f"Discount can't exceed {ceiling:g}% -- ask an employee to "
                f"place this order for a higher discount."
            )
        return discount_percent

    def clean(self):
        """
        Courtesy check: quantity can't exceed the product's units_in_stock. It needs
        two fields together, so it is clean() rather than clean_<field>(). A key
        missing from cleaned_data means that field already failed, and a NULL
        units_in_stock means there is no stock limit to check.
        """
        cleaned_data = super().clean()
        product = cleaned_data.get("product")
        quantity = cleaned_data.get("quantity")
        stock_known = product is not None and product.units_in_stock is not None
        if stock_known and quantity is not None and quantity > product.units_in_stock:
            self.add_error(
                "quantity",
                f"Only {product.units_in_stock} of {product.product_name} left in stock.",
            )
        return cleaned_data


class OrderCommitForm(forms.ModelForm):
    """
    Collects the employee, dates and shipping address when a cart becomes a placed
    Order. order_date is set by the view (order_commit, views/orders.py) to today,
    not picked.

    employee is required here even though the model column is nullable: "every
    placed order needs an employee" is a business rule, so the form is stricter than
    the column. Its dropdown shows full names because Employee has no __str__. The
    ship_* fields are editable and start from the customer's on-file address (the
    view passes it as initial=), so one order can ship elsewhere; name, address, city
    and country are required, region and postal code are not. required_date and
    shipped_date start two weeks and one week out (default_required_date,
    default_shipped_date) but stay editable.

    The form is used unbound (no instance=): order_commit calls
    form.save(commit=False) to build a new Order. A ModelForm creates or updates
    depending only on whether instance= was passed.
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

        # Required as a business rule, like employee: each of these columns is
        # nullable on Order itself.
        for field_name in ("ship_name", "ship_address", "ship_city", "ship_country"):
            self.fields[field_name].required = True
        for field_name in (
            "ship_name", "ship_address", "ship_city",
            "ship_region", "ship_postal_code", "ship_country",
        ):
            self.fields[field_name].widget.attrs.update({"class": "form-control"})

    class Meta:
        model = Order
        fields = [
            "employee",
            "required_date",
            "shipped_date",
            "ship_name",
            "ship_address",
            "ship_city",
            "ship_region",
            "ship_postal_code",
            "ship_country",
        ]
        widgets = {
            "required_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "shipped_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def clean(self):
        """
        Neither date may be before today: nothing in the database would stop a
        required or shipped date from being earlier than the order itself.
        """
        cleaned_data = super().clean()
        today = timezone.now().date()
        for field_name, label in (("required_date", "Required date"), ("shipped_date", "Ship-by date")):
            value = cleaned_data.get(field_name)
            if value is not None and value < today:
                self.add_error(field_name, f"{label} can't be before today's order date.")
        return cleaned_data


def default_required_date():
    """order_date (today, at commit) + 2 weeks -- see OrderCommitForm."""
    return timezone.now().date() + timedelta(weeks=2)


def default_shipped_date():
    """order_date (today, at commit) + 1 week -- see OrderCommitForm."""
    return timezone.now().date() + timedelta(weeks=1)


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
                    <button type="submit" class="btn dt-btn-primary-customer dt-hover-shadow" title="Create your account">
                        <i class="fa-solid fa-user-plus me-1 dt-icon-success"></i>Create My Account
                    </button>
                    <div class="dt-link-wrap btn dt-btn-secondary-customer dt-hover-shadow">
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


class OrderLineQuantityForm(forms.Form):
    """
    Sets the quantity of a line that is already in the cart
    (order_update_line, djtraders/views/ package). A plain Form, not a
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
                    <button type="submit" class="btn dt-btn-primary-supplier dt-hover-shadow" title="Save changes">
                        <i class="fa-solid fa-floppy-disk me-1 dt-icon-success"></i>Save
                    </button>
                    <div class="dt-link-wrap btn dt-btn-secondary-supplier dt-hover-shadow">
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
