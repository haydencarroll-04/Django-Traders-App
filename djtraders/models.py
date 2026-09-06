from django.db import models

"""
Cleaned-up models generated from `manage.py inspectdb` (see rev_engineer_models.py
for the raw, unedited output). Django's inspectdb leaves a standard checklist of
manual fixes at the top of the generated file -- what changed here, and why:

  1. Renamed models to singular (Category, Customer, ...), reordered so a
    model is defined before anything that references it by bare class
    name, and gave every FK a real on_delete (inspectdb defaults to
    DO_NOTHING) matching what should actually happen when the related
    row is deleted. managed=False everywhere, since this app reads an
    existing database Django didn't create.
  2. Product.is_discontinued maps the raw discontinued IntegerField (1
    or 0) to an actual bool, for product_list.html's display.
  3. Customer.search and Product.search back their list pages' search
    forms (djtraders/views.py) -- free-text fields use a case-
    insensitive "icontains", fields from a dropdown use an exact match.
  4. OrderDetail.line_total, Order.order_total, Product.total_revenue,
    and Product.units_sold are computed properties, not stored fields --
    order_total/total_revenue both sum line_total across a set of lines
    rather than repeating its formula.
  5. Customer.formatted_address joins address/city/region/postal_code/
    country into one line (blanks skipped), for customer_detail.html.
"""

class Category(models.Model):
    """
    A product category. Defined before Product (the model that references
    it) so Product.category can use the bare class name instead of a
    forward-reference string - see the module docs for why order
    matters here.
    """
    category_id = models.SmallIntegerField(primary_key=True)
    category_name = models.CharField(max_length=15)
    description = models.TextField(blank=True, null=True)
    picture = models.BinaryField(blank=True, null=True)

    class Meta:
        """
        Meta configures the model/table itself, not a database column.
        managed=False: table already exists, Django shouldn't migrate it.
        db_table: the real table name, since it doesn't match Django's
        default ("djtraders_category").
        """
        managed = False
        db_table = 'categories'


class Customer(models.Model):
    """A DjangoTraders customer. No foreign keys, so no on_delete concerns."""
    customer_id = models.CharField(primary_key=True, max_length=5)
    company_name = models.CharField(max_length=40)
    contact_name = models.CharField(max_length=30, blank=True, null=True)
    contact_title = models.CharField(max_length=30, blank=True, null=True)
    address = models.CharField(max_length=60, blank=True, null=True)
    city = models.CharField(max_length=15, blank=True, null=True)
    region = models.CharField(max_length=15, blank=True, null=True)
    postal_code = models.CharField(max_length=10, blank=True, null=True)
    country = models.CharField(max_length=15, blank=True, null=True)
    phone = models.CharField(max_length=24, blank=True, null=True)
    fax = models.CharField(max_length=24, blank=True, null=True)
    password = models.CharField(db_column='Password', max_length=64, blank=True, null=True)  # Field name made lowercase.
    inactive_date = models.DateField(blank=True, null=True)

    @property
    def formatted_address(self):
        """
        This customer's address, city, region, postal_code, and country
        joined into one line (blank ones skipped), instead of five
        separate fields -- used by customer_detail.html.
        """
        parts = [self.address, self.city, self.region, self.postal_code, self.country]
        return ", ".join(part for part in parts if part)

    @classmethod
    def search(cls, company_name="", city="", country="", contact_name="", contact_title=""):
        """
        Filters customers by an optional company name, city, country, contact name, and/or contact title
        returning every customer when none are given. Used by
        customer_list (djtraders/views.py) to back its search form.

        A @classmethod (not a regular instance method) because it builds
        a brand-new queryset from scratch (cls.objects...) rather than
        acting on one existing Customer -- there's no single customer
        instance to call it on yet, so it needs the class itself (cls),
        not self. This also lets it be called directly on the model
        (Customer.search(...)) instead of needing an instance first.

        cls: the Customer class itself, passed in automatically since
        this is a classmethod -- not a particular customer instance.

        company_name uses "icontains" (a case-insensitive substring
        match) since it's a free-text field -- someone typing part of a
        name expects a match anywhere in it, regardless of case. country
        uses an exact match instead, since its value always comes from a
        dropdown of countries already on record, not free text -- there's
        nothing partial (or case-varied) to match against.
        """
        queryset = cls.objects.order_by("company_name")
        if company_name:
            queryset = queryset.filter(company_name__icontains=company_name)
        if city:
            queryset = queryset.filter(city__icontains=city)
        if country:
            queryset = queryset.filter(country=country)
        if contact_name:
            queryset = queryset.filter(contact_name__icontains=contact_name)
        if contact_title:
            queryset = queryset.filter(contact_title=contact_title)
        return queryset

    class Meta:
        managed = False
        db_table = 'customers'


class Employee(models.Model):
    """A DjangoTraders employee. Has a self-referencing FK for its manager (reports_to)."""
    employee_id = models.SmallIntegerField(primary_key=True)
    last_name = models.CharField(max_length=20)
    first_name = models.CharField(max_length=10)
    title = models.CharField(max_length=30, blank=True, null=True)
    title_of_courtesy = models.CharField(max_length=25, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    hire_date = models.DateField(blank=True, null=True)
    address = models.CharField(max_length=60, blank=True, null=True)
    city = models.CharField(max_length=15, blank=True, null=True)
    region = models.CharField(max_length=15, blank=True, null=True)
    postal_code = models.CharField(max_length=10, blank=True, null=True)
    country = models.CharField(max_length=15, blank=True, null=True)
    home_phone = models.CharField(max_length=24, blank=True, null=True)
    extension = models.CharField(max_length=4, blank=True, null=True)
    photo = models.BinaryField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    photo_path = models.CharField(max_length=255, blank=True, null=True)
    # region [CONCEPT] self-referencing FK (reports_to)
    # FK to Employee itself, for the manager hierarchy: gives us
    # employee.reports_to.first_name (up to the manager) and
    # employee.employee_set.all() (down to their reports).
    # SET_NULL so deleting a manager just clears the link, not their reports.
    # endregion
    reports_to = models.ForeignKey('self', models.SET_NULL, db_column='reports_to', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'employees'


class OrderDetail(models.Model):
    """
    A single line item on an order (composite primary key: order_id + product_id).
    """
    # region [WARNING] order+product form the composite PK, not a separate id column
    # order and product below are ordinary FKs, but they're ALSO the two
    # columns making up this table's primary key (CompositePrimaryKey, not
    # a separate id column) - a product can only appear once per order.
    # endregion
    pk = models.CompositePrimaryKey('order_id', 'product_id')

    # FK to Order (order_detail.order.order_date, order.orderdetail_set.all()).
    # CASCADE: a line item is meaningless without its order.
    order = models.ForeignKey('Order', models.CASCADE)

    # FK to Product (order_detail.product.product_name, product.orderdetail_set.all()).
    # PROTECT: refuse to delete a product still on a historical order line.
    product = models.ForeignKey('Product', models.PROTECT)
    unit_price = models.FloatField()
    quantity = models.SmallIntegerField()
    discount = models.FloatField()

    @property
    def line_total(self):
        """
        This line's own revenue: unit_price times quantity, minus the
        discount fraction. A @property, not a field, since it's derived
        from the three fields above rather than stored -- Order.order_total
        sums this same property across every line instead of repeating
        the formula.
        """
        return self.unit_price * self.quantity * (1 - self.discount)

    class Meta:
        managed = False
        db_table = 'order_details'


class Order(models.Model):
    """
    A customer order. The customer/employee/shipper links are all nullable, so
    on_delete=SET_NULL keeps the order history intact even if one of those
    related records is later removed.
    """
    # region [WHY] AutoField only for order_id
    # SmallAutoField, unlike this app's other primary keys: order_id's
    # database column is backed by a real auto-incrementing sequence, so
    # the other models' IDs (category_id, etc.) aren't - they're fixed
    # reference IDs the database won't generate for you.
    # endregion
    order_id = models.SmallAutoField(primary_key=True)
    order_date = models.DateField(blank=True, null=True)
    required_date = models.DateField(blank=True, null=True)
    shipped_date = models.DateField(blank=True, null=True)
    freight = models.FloatField(blank=True, null=True)
    ship_name = models.CharField(max_length=40, blank=True, null=True)
    ship_address = models.CharField(max_length=60, blank=True, null=True)
    ship_city = models.CharField(max_length=15, blank=True, null=True)
    ship_region = models.CharField(max_length=15, blank=True, null=True)
    ship_postal_code = models.CharField(max_length=10, blank=True, null=True)
    ship_country = models.CharField(max_length=15, blank=True, null=True)

    # FK to Customer (order.customer.company_name, customer.order_set.all()).
    customer = models.ForeignKey(Customer, models.SET_NULL, blank=True, null=True)

    # FK to Employee (order.employee.last_name, employee.order_set.all()).
    employee = models.ForeignKey(Employee, models.SET_NULL, blank=True, null=True)

    # FK to Shipper, stored in a column named ship_via (db_column below) --
    # that's the existing table's column name, not shipper_id.
    ship_via = models.ForeignKey('Shipper', models.SET_NULL, db_column='ship_via', blank=True, null=True)

    @property
    def order_total(self):
        """
        This order's total revenue -- every line item's own line_total
        (OrderDetail.line_total) added together, not recomputed here.
        order.customer is already a real field (the FK above), not a
        property -- it needs no extra code to access.
        """
        return sum(line.line_total for line in self.orderdetail_set.all())

    class Meta:
        managed = False
        db_table = 'orders'


class Product(models.Model):
    """
    A DjangoTraders product. Supplier and category are both nullable, so removing
    either one just clears the link (SET_NULL) instead of touching the product.
    """
    product_id = models.SmallIntegerField(primary_key=True)
    product_name = models.CharField(max_length=40)
    quantity_per_unit = models.CharField(max_length=20, blank=True, null=True)
    unit_price = models.FloatField(blank=True, null=True)
    units_in_stock = models.SmallIntegerField(blank=True, null=True)
    units_on_order = models.SmallIntegerField(blank=True, null=True)
    reorder_level = models.SmallIntegerField(blank=True, null=True)
    discontinued = models.IntegerField()
    date_discontinued = models.DateField(blank=True, null=True)
    
    # FK to Supplier (product.supplier.company_name, supplier.product_set.all()).
    supplier = models.ForeignKey('Supplier', models.SET_NULL, blank=True, null=True)

    # FK to Category (product.category.category_name, category.product_set.all()).
    category = models.ForeignKey(Category, models.SET_NULL, blank=True, null=True)

    @property
    def is_discontinued(self):
        """
        discontinued is a plain 1/0 IntegerField, not a BooleanField -- this
        maps it to a real bool so callers can write product.is_discontinued
        instead of comparing product.discontinued to 1 by hand. A @property,
        not a field, so it's computed fresh each access, no migration needed.
        """
        return bool(self.discontinued)

    @property
    def is_low_stock(self):
        """
        Returns True if the product's units_in_stock is less than or equal 
        to its reorder_level, or False otherwise. If either value is None, 
        returns False.
        """
        if self.units_in_stock is None or self.reorder_level is None:
            return False
        return self.units_in_stock <= self.reorder_level

    @property
    def is_out_of_stock(self):
        """
        True when units_in_stock is exactly 0. Kept separate from
        is_low_stock so a template can show one badge or the other.
        """
        return self.units_in_stock == 0

    @classmethod
    def search(cls, product_name="", category_id="", supplier_id="", show_all=False):
        """
        Filters products by an optional product name and/or category,
        returning every non-discontinued product by default. Used by
        product_list (djtraders/views.py) to back its search form.

        product_name uses "icontains" (a case-insensitive substring
        match), same reasoning as Customer.search's company_name.
        category_id uses an exact match, since its value comes from a
        dropdown of categories already on record, not free text.
        show_all=False filters out discontinued products (discontinued
        is a plain 1/0 field, not is_discontinued -- that's a Python
        property, not something the database can filter on); show_all=
        True skips that filter, showing discontinued products too.
        """
        queryset = cls.objects.order_by("product_name")
        # if there is a product_name, filter by it;
        if product_name:
            queryset = queryset.filter(product_name__icontains=product_name)

        # if there is a supplier_id, filter by it;
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)

        # if there is a category_id, filter by it;
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # if show_all is False, filter out discontinued products (discontinued=1);
        if not show_all:
            queryset = queryset.filter(discontinued=0)

        return queryset

    @property
    def total_revenue(self):
        """
        Total revenue this product has generated -- every order line it
        appears on, each one's own line_total (OrderDetail.line_total)
        added together. product.orderdetail_set is the reverse side of
        OrderDetail.product's FK (every OrderDetail row for this product).
        """
        return sum(line.line_total for line in self.orderdetail_set.all())

    @property
    def units_sold(self):
        """
        Total quantity of this product sold -- every order line's
        quantity added together, across every order it's appeared on.
        """
        return sum(line.quantity for line in self.orderdetail_set.all())

    class Meta:
        managed = False
        db_table = 'products'


class Region(models.Model):
    """A geographic region. No foreign keys."""
    region_id = models.SmallIntegerField(primary_key=True)
    region_description = models.CharField(max_length=60)

    class Meta:
        managed = False
        db_table = 'region'


class Shipper(models.Model):
    """A shipping carrier. No foreign keys."""
    shipper_id = models.SmallIntegerField(primary_key=True)
    company_name = models.CharField(max_length=40)
    phone = models.CharField(max_length=24, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'shippers'


class Supplier(models.Model):
    """A product supplier. No foreign keys."""
    supplier_id = models.SmallIntegerField(primary_key=True)
    company_name = models.CharField(max_length=40)
    contact_name = models.CharField(max_length=30, blank=True, null=True)
    contact_title = models.CharField(max_length=30, blank=True, null=True)
    address = models.CharField(max_length=60, blank=True, null=True)
    city = models.CharField(max_length=15, blank=True, null=True)
    region = models.CharField(max_length=15, blank=True, null=True)
    postal_code = models.CharField(max_length=10, blank=True, null=True)
    country = models.CharField(max_length=15, blank=True, null=True)
    phone = models.CharField(max_length=24, blank=True, null=True)
    fax = models.CharField(max_length=24, blank=True, null=True)
    homepage = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'suppliers'

# region [CONCEPT] Territory and UsState omitted on purpose
# Territory and UsState  omitted on purpose: this app doesn't use them
#
# class Territory(models.Model):
#     territory_id = models.CharField(primary_key=True, max_length=20)
#     territory_description = models.CharField(max_length=60)
#     region = models.ForeignKey(Region, models.PROTECT)
#
#     class Meta:
#         managed = False
#         db_table = 'territories'
#
#
# class UsState(models.Model):
#     """US state lookup data. No foreign keys. We will use this later."""
#     state_id = models.SmallIntegerField(primary_key=True)
#     state_name = models.CharField(max_length=100, blank=True, null=True)
#     state_abbr = models.CharField(max_length=2, blank=True, null=True)
#     state_region = models.CharField(max_length=50, blank=True, null=True)

#     class Meta:
#         managed = False
#         db_table = 'us_states'
# endregion