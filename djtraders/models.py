"""
The app's models, cleaned up from `manage.py inspectdb` (rev_engineer_models.py
has the raw output). Every model is managed=False, because this app reads a
database Django didn't create and must never migrate those tables. Names are
singular, models are ordered so each is defined before anything that references
it by bare class name, and every foreign key has a real on_delete (inspectdb
defaults to DO_NOTHING).

On top of that the models add computed @property values (e.g.
Order.order_total), search() classmethods that back the list pages,
authenticate() classmethods for the hand-rolled logins (no django.contrib.auth),
and, for the dashboards, methods that return Plotly charts built with the
helpers in charts.py.
"""

import calendar

import pandas as pd
import plotly.graph_objects as go
from django.db import models
from django.db.models import Count, ExpressionWrapper, F, FloatField, Sum

from .charts import (
    CHART_COLORS,
    bar_figure,
    figure_html,
    line_figure,
    lines_frame,
    pie_figure,
    top_with_other,
)


class Category(models.Model):
    """A product category. Defined before Product so Product.category can use the bare class name."""
    category_id = models.SmallIntegerField(primary_key=True)
    category_name = models.CharField(max_length=15)
    description = models.TextField(blank=True, null=True)
    picture = models.BinaryField(blank=True, null=True)

    class Meta:
        """Meta configures the table, not a column. managed=False: the table exists, so Django must not migrate it. db_table: its real name."""
        managed = False
        db_table = 'categories'


# region [CONCEPT] charts the customer and supplier dashboards share
# Both dashboards ask the same questions of a different slice of the order lines (a
# customer's own orders, or a supplier's own products): summary cards, revenue by year
# and month, revenue by category, unit share by category and top products. Those live
# here once. A model that mixes this class in provides _order_lines_frame(extra) (its
# slice of the lines, see lines_frame in charts.py) and order_years(), and everything
# below works on that frame, so a chart can never include lines outside the slice.
# endregion
class DashboardChartsMixin:
    """Dashboard cards and charts built from self._order_lines_frame(); mixed into Customer and Supplier."""

    def parse_year(self, raw):
        """A ?year= value as an int that is one of this model's order years, None for "all" (or blank), or False when it is invalid."""
        if raw in ("", "all", None):
            return None
        try:
            year = int(raw)
        except ValueError:
            return False
        return year if year in self.order_years() else False

    def _year_frame(self, year=None, extra=None):
        """This model's lines, narrowed to one year (None keeps every year)."""
        frame = self._order_lines_frame(extra)
        if year is not None and not frame.empty:
            frame = frame[frame["year"] == year]
        return frame

    def annual_revenue_plot(self):
        """Bar chart of this model's revenue for each year, with a trend line (a straight line fitted through the yearly totals: it slopes up when revenue is growing from year to year); None when there are no sales."""
        frame = self._order_lines_frame()
        if frame.empty:
            return None
        annual = frame.groupby("year", as_index=False)["revenue"].sum()
        annual["year"] = annual["year"].astype(str)
        return bar_figure(
            annual, "year", "revenue", "Revenue by year",
            {"year": "Year", "revenue": "Revenue ($)"},
        )

    def monthly_revenue_plot(self, year):
        """
        Bar chart of this model's revenue for each month of one year (what the
        dashboards' year dropdown loads), or None when that year has no sales.
        reindex(range(1, 13), fill_value=0) puts all twelve months on the chart:
        without it a month with no sales would be missing instead of $0.
        """
        frame = self._year_frame(year)
        if frame.empty:
            return None
        monthly = (
            frame.groupby("month")["revenue"].sum()
            .reindex(range(1, 13), fill_value=0)
            .reset_index()
        )
        monthly["month"] = [calendar.month_abbr[m] for m in monthly["month"]]
        return bar_figure(
            monthly, "month", "revenue", f"Revenue by month, {year}",
            {"month": "Month", "revenue": "Revenue ($)"},
        )

    def dashboard_stats(self):
        """
        The summary cards, or None when nothing has been sold: total revenue, orders
        (distinct), units, average order (revenue per order), and the last order (its
        id, date and revenue on it, within this model's own slice of the lines).

        "Year to date" needs a today, but the order history ends long ago, so the
        latest order date in the slice stands in for today: ytd_revenue is revenue
        from Jan 1 of that year to that date, prior_ytd_revenue the same span one
        year earlier, and change_pct the difference as a percent (None when the
        year before had no sales, which has no percentage change).
        """
        frame = self._order_lines_frame()
        if frame.empty:
            return None
        last_date = frame["order_date"].max()
        last_order_id = int(frame.loc[frame["order_date"] == last_date, "order_id"].max())
        last_revenue = float(frame.loc[frame["order_id"] == last_order_id, "revenue"].sum())

        this_year = last_date.year
        ytd = frame.loc[frame["year"] == this_year, "revenue"].sum()
        prior_cutoff = last_date - pd.DateOffset(years=1)
        prior_ytd = frame.loc[(frame["year"] == this_year - 1) & (frame["order_date"] <= prior_cutoff), "revenue"].sum()
        revenue = float(frame["revenue"].sum())
        orders = int(frame["order_id"].nunique())
        return {
            "revenue": revenue,
            "orders": orders,
            "units": int(frame["quantity"].sum()),
            "average_order": revenue / orders,
            "last_order_id": last_order_id,
            "last_order_date": last_date.date(),
            "last_order_revenue": last_revenue,
            "ytd_year": this_year,
            "ytd_revenue": float(ytd),
            "prior_ytd_revenue": float(prior_ytd),
            "change_pct": float((ytd - prior_ytd) / prior_ytd * 100) if prior_ytd > 0 else None,
        }

    def category_revenue_plot(self, year=None):
        """Horizontal bar chart of revenue by category, largest first, for one year or all of them; None when there are no sales."""
        frame = self._year_frame(year)
        if frame.empty:
            return None
        by_category = frame.groupby("category_name", as_index=False)["revenue"].sum().sort_values("revenue")
        scope = f", {year}" if year else ""
        return bar_figure(
            by_category, "category_name", "revenue", f"Revenue by category{scope}",
            {"category_name": "Category", "revenue": "Revenue ($)"},
            horizontal=True, trend=False, height=max(260, 60 * len(by_category) + 120),
        )

    def category_units_plot(self, year=None, kind="bar"):
        """
        Each category's share of the units sold, for one year or all of them: a
        bar chart of percents (kind="bar") or a pie (kind="pie"). None when there
        are no sales.
        """
        frame = self._year_frame(year)
        if frame.empty:
            return None
        units = frame.groupby("category_name", as_index=False)["quantity"].sum()
        scope = f", {year}" if year else ""
        title = f"Unit share by category{scope}"
        if kind == "pie":
            return pie_figure(top_with_other(units, "category_name", "quantity", 8),
                              "category_name", "quantity", title, money=False)
        units["percent"] = units["quantity"] / units["quantity"].sum() * 100
        units = units.sort_values("percent")
        return bar_figure(
            units, "category_name", "percent", title,
            {"category_name": "Category", "percent": "Share of units (%)"},
            horizontal=True, trend=False, height=max(260, 60 * len(units) + 120),
            text=[f"{p:.1f}%" for p in units["percent"]],
            hover=[f"<b>{c}</b><br>{q:,.0f} units ({p:.1f}%)" for c, q, p in zip(units["category_name"], units["quantity"], units["percent"])],
        )

    # What the top-products chart can rank by: the column of the frame and its label.
    TOP_MEASURES = {"revenue": "Revenue", "quantity": "Units sold"}

    @staticmethod
    def _top_products_figure(frame, top, measure):
        """
        Horizontal bar chart of the top products in frame by revenue or by units
        (measure = "revenue" or "quantity"), largest at the top, or None for an empty
        frame. The title names the top you asked for, and says how many products
        have sales when that is fewer, so a short chart doesn't look like a stuck control.
        """
        if frame.empty:
            return None
        by_product = (
            frame.groupby("product_name", as_index=False)[measure].sum()
            .sort_values(measure, ascending=False).head(top)
            .sort_values(measure)
        )
        what = "revenue" if measure == "revenue" else "units"
        shown = len(by_product)
        note = f" (only {shown} with sales)" if shown < top else ""
        return bar_figure(
            by_product, "product_name", measure, f"Top {top} products by {what}{note}",
            {"product_name": "Product", measure: "Revenue ($)" if measure == "revenue" else "Units sold"},
            horizontal=True, trend=False, height=max(260, 42 * len(by_product) + 120),
        )


class Customer(DashboardChartsMixin, models.Model):
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
        """This customer's address fields joined into one line, blanks skipped."""
        parts = [self.address, self.city, self.region, self.postal_code, self.country]
        return ", ".join(part for part in parts if part)

    # region [WHY] charts built from a DataFrame
    # Each *_plot method (most are in DashboardChartsMixin) pulls this customer's placed
    # order lines into a DataFrame (_order_lines_frame), groups and sums them with pandas,
    # and hands the result to bar_figure, which returns chart HTML a template prints with |safe.
    # endregion
    def _order_lines_frame(self, extra=None):
        """
        Every line on this customer's placed orders as a DataFrame (see
        lines_frame in charts.py). An order with no order_date is an unplaced
        cart and is left out.
        """
        return lines_frame(OrderDetail.objects.filter(
            order__customer=self, order__order_date__isnull=False
        ), extra=extra)

    def top_products_plot(self, top=10, measure="revenue", year=None):
        """Horizontal bar chart of this customer's top products by revenue or units (measure = "revenue" or "quantity"), for one year or all of them; None when they bought nothing."""
        return self._top_products_figure(self._year_frame(year), top, measure)

    def order_years(self):
        """Distinct years this customer has placed orders in, newest first."""
        years = self.order_set.filter(order_date__isnull=False).dates("order_date", "year")
        return sorted((d.year for d in years), reverse=True)

    @classmethod
    def search(cls, company_name="", contact_name="", contact_title="", city="", country=""):
        """
        Filters customers by any combination of company name, contact name,
        contact title, city and country (every customer when none are given), for
        customer_list's search form. A @classmethod because it builds a new
        queryset from the class (cls) rather than acting on one Customer. The two
        free-text fields use "icontains" (case-insensitive substring); the others
        come from dropdowns, so they match exactly.
        """
        queryset = cls.objects.order_by("company_name")
        if company_name:
            queryset = queryset.filter(company_name__icontains=company_name)
        if contact_name:
            queryset = queryset.filter(contact_name__icontains=contact_name)
        if contact_title:
            queryset = queryset.filter(contact_title=contact_title)
        if city:
            queryset = queryset.filter(city=city)
        if country:
            queryset = queryset.filter(country=country)
        return queryset

    @classmethod
    def authenticate(cls, customer_id, password):
        """
        Checks a login: the customer with this ID, and a direct compare of the
        password column (unlike Employee, which has no password column). Returns
        the Customer on success, None otherwise.
        """
        customer = cls.objects.filter(pk=customer_id).first()
        if customer is None:
            return None
        if customer.password != password:
            return None
        return customer

    @classmethod
    def generate_customer_id(cls, company_name):
        """
        Builds a new, unique 5-letter customer_id from a company name, in the
        existing style ("Alfreds Futterkiste" -> ALFKI). Called by
        customer_create after the form validates; a customer never types an ID.
        It takes the name's first five letters (padded with "X"), and if that ID is
        taken, swaps in a trailing counter (ALFK1, ALFK2, ...). The primary key's own
        uniqueness is the final guarantee; the loop just avoids a rejected insert.
        """
        letters = "".join(char for char in company_name.upper() if char.isalpha())
        base = (letters + "XXXXX")[:5]

        if not cls.objects.filter(pk=base).exists():
            return base

        # base alone is taken: replace its trailing characters with a counter.
        suffix = 1
        while suffix < 100_000:
            digits = str(suffix)
            candidate = base[: 5 - len(digits)] + digits
            if not cls.objects.filter(pk=candidate).exists():
                return candidate
            suffix += 1

        # Practically unreachable for a dataset this size.
        raise ValueError(f"Could not generate a unique customer_id from {company_name!r}")

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

    @property
    def formatted_address(self):
        """This employee's address fields joined into one line, blanks skipped."""
        parts = [self.address, self.city, self.region, self.postal_code, self.country]
        return ", ".join(part for part in parts if part)

    @property
    def is_manager(self):
        """
        True when at least one employee reports to this one. A manager may open
        any employee's page; employee_set is the reverse side of reports_to
        (every employee whose manager is this one).
        """
        return self.employee_set.exists()

    def _order_lines_frame(self):
        """Every line on the placed orders this employee handled, as a DataFrame (see lines_frame in charts.py)."""
        return lines_frame(OrderDetail.objects.filter(
            order__employee=self, order__order_date__isnull=False
        ))

    def revenue_years(self):
        """The years in which this employee handled placed orders, oldest first (for the year dropdown)."""
        frame = self._order_lines_frame()
        if frame.empty:
            return []
        return sorted(int(year) for year in frame["year"].unique())

    def revenue_over_time(self, level="year", year=None, height=360):
        """
        The dashboard's revenue-over-time chart, as chart HTML (None when this
        employee has no orders). Each bar's hover shows the period, its revenue
        and its number of orders.

        level "year": one bar per year (year is ignored).
        level "month" with a year: the twelve months of that year, as a line chart.
        level "month" with year=None: every month from the first order to the last,
        across all years, as a line chart, so it reads as revenue over time.

        Orders are distinct orders. Months with no orders are filled in with zero
        (reindex over a full period range), so a quiet month shows as an empty
        slot instead of vanishing.
        """
        frame = self._order_lines_frame()
        if frame.empty:
            return None
        if level == "year":
            grouped = frame.groupby("year").agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
            table = grouped.reset_index()
            table["label"] = table["year"].astype(str)
            table["full_label"] = table["label"]
            title, axis = "Revenue by year", "Year"
        else:
            if year is not None:
                frame = frame[frame["year"] == year]
            frame = frame.assign(period=frame["order_date"].dt.to_period("M"))
            grouped = frame.groupby("period").agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
            if year is None:
                full_range = pd.period_range(grouped.index.min(), grouped.index.max(), freq="M")
                title = "Revenue by month, all years"
            else:
                full_range = pd.period_range(f"{year}-01", f"{year}-12", freq="M")
                title = f"Revenue by month, {year}"
            grouped = grouped.reindex(full_range, fill_value=0)
            table = grouped.reset_index(names="period")
            table["label"] = table["period"].dt.strftime("%b" if year is not None else "%b %Y")
            table["full_label"] = table["period"].dt.strftime("%B %Y")
            axis = "Month"
        hover = [
            f"<b>{row.full_label}</b><br>Revenue: ${row.revenue:,.0f}<br>Orders: {row.orders:,}"
            for row in table.itertuples()
        ]
        labels = {"label": axis, "revenue": "Revenue ($)"}
        if level == "year":
            return bar_figure(table, "label", "revenue", title, labels, height=height, hover=hover)
        # Months run in time order, so a line reads better than bars.
        return line_figure(table, "label", "revenue", title, labels, height=height, hover=hover)

    def period_detail(self, key):
        """
        What the Details modal shows for one period of this employee's orders: key
        is "1997" (a year) or "1997-03" (a month). Returns a dict with label,
        revenue, orders and products (the five products with the most revenue in
        that period, each with units and revenue). For a whole year it also returns
        months_plot, that year's revenue by month; for a single month it is None.
        The view has already checked that key is a real period.
        """
        year, _, month = key.partition("-")
        frame = self._order_lines_frame()
        in_period = frame["year"] == int(year)
        label = year
        if month:
            in_period &= frame["month"] == int(month)
            label = pd.Timestamp(year=int(year), month=int(month), day=1).strftime("%B %Y")
        part = frame[in_period]
        products = (
            part.groupby("product_name", as_index=False)
            .agg(units=("quantity", "sum"), revenue=("revenue", "sum"))
            .sort_values("revenue", ascending=False).head(5)
        )
        months_plot = None
        if not month:
            months_plot = self.revenue_over_time("month", int(year), height=300)
        return {
            "label": label,
            "revenue": part["revenue"].sum(),
            "orders": part["order_id"].nunique(),
            "products": products.to_dict("records"),
            "months_plot": months_plot,
        }

    @classmethod
    def _performance_frame(cls):
        """
        One row per employee who handled at least one placed order:
        revenue, orders (distinct orders), customers (distinct customers),
        average_order, revenue_per_customer, share (percent of all company
        revenue), and a rank for each measure (revenue_rank, orders_rank,
        average_order_rank, customers_rank, revenue_per_customer_rank;
        1 = best, ties share a rank). The database does the grouping with
        values()/annotate(); pandas adds the derived columns. Sorted by
        revenue_rank. The base for performance(), team_comparison() and
        leaderboard().
        """
        rows = (
            OrderDetail.objects.filter(order__order_date__isnull=False)
            .values(employee_key=F("order__employee_id"))
            .annotate(
                revenue=Sum(Supplier._line_revenue()),
                orders=Count("order", distinct=True),
                customers=Count("order__customer", distinct=True),
            )
        )
        frame = pd.DataFrame(list(rows)).dropna(subset=["employee_key"]) if rows else pd.DataFrame()
        if frame.empty:
            return frame
        frame["employee_key"] = frame["employee_key"].astype(int)
        frame["average_order"] = frame["revenue"] / frame["orders"]
        frame["revenue_per_customer"] = frame["revenue"] / frame["customers"].where(frame["customers"] > 0)
        frame["share"] = frame["revenue"] / frame["revenue"].sum() * 100
        for measure in ("revenue", "orders", "average_order", "customers", "revenue_per_customer"):
            frame[f"{measure}_rank"] = frame[measure].rank(ascending=False, method="min")
        return frame.sort_values("revenue_rank")

    def performance(self):
        """
        This employee compared with the other employees, for the
        dashboard's summary tiles: a dict with their revenue, orders,
        average_order, share of company revenue, revenue_rank and
        orders_rank, employee_count (how many employees have orders),
        colleagues_behind, team_share (an even split, 100 / employee_count),
        team_average_order (the mean of the employees' average orders, the same
        figure the "vs. the team" table shows) and
        average_order_diff (percent above or below that team figure).
        Returns None when this employee has no placed orders.
        """
        frame = self._performance_frame()
        if frame.empty:
            return None
        mine = frame[frame["employee_key"] == self.employee_id]
        if mine.empty:
            return None
        row = mine.iloc[0]
        count = len(frame)
        team_average_order = frame["average_order"].mean()
        return {
            "revenue": row["revenue"],
            "orders": int(row["orders"]),
            "average_order": row["average_order"],
            "share": row["share"],
            "revenue_rank": int(row["revenue_rank"]),
            "orders_rank": int(row["orders_rank"]),
            "employee_count": count,
            "colleagues_behind": count - int(row["revenue_rank"]),
            "team_share": 100 / count,
            "team_average_order": team_average_order,
            "average_order_diff": (row["average_order"] / team_average_order - 1) * 100,
        }

    # What the team comparison chart's dropdown can compare: the key and its label.
    TEAM_MEASURES = {
        "revenue": "Revenue",
        "orders": "Orders",
        "customers": "Customers served",
    }

    def team_comparison(self):
        """
        This employee against the team on the three TEAM_MEASURES, as a list of
        dicts for the dashboard's comparison table and chart: measure, label, kind
        ("money" or "count", for formatting), you, team_average (the mean across
        employees), vs_average (you as a percent above or below that average), best
        (the highest employee, nameless), rank and employee_count.
        Returns [] when this employee has no placed orders.
        """
        frame = self._performance_frame()
        mine = frame[frame["employee_key"] == self.employee_id] if not frame.empty else frame
        if mine.empty:
            return []
        row = mine.iloc[0]
        comparison = []
        for measure, label in self.TEAM_MEASURES.items():
            team_average = frame[measure].mean()
            comparison.append({
                "measure": measure,
                "label": label,
                "kind": "money" if measure == "revenue" else "count",
                "you": row[measure],
                "team_average": team_average,
                "vs_average": (row[measure] / team_average - 1) * 100,
                "best": frame[measure].max(),
                "rank": int(row[f"{measure}_rank"]),
                "employee_count": len(frame),
            })
        return comparison

    def team_comparison_plot(self, measure="revenue", you_label="You"):
        """
        Bar chart for one measure (a TEAM_MEASURES key): this employee, the team
        average and the best employee, in real units. The best bar is nameless.
        This one is built with Plotly's graph_objects (go) rather than Express, so
        each bar is added by hand. Returns None when there is nothing to compare.
        """
        row = next((r for r in self.team_comparison() if r["measure"] == measure), None)
        if row is None:
            return None

        names = [you_label, "Team average", "Best"]
        values = [row["you"], row["team_average"], row["best"]]
        is_money = row["kind"] == "money"
        text = [f"${v:,.0f}" if is_money else f"{v:,.0f}" for v in values]

        figure = go.Figure(go.Bar(
            x=names, y=values, text=text, textposition="outside", cliponaxis=False,
            marker_color=[CHART_COLORS[0], "#5f6b76", CHART_COLORS[2]],
            hovertemplate="<b>%{x}</b><br>%{text}<extra></extra>",
        ))
        figure.update_layout(
            title=f"{row['label']}: {you_label} compared with the team", height=340,
            yaxis_title="Revenue ($)" if is_money else row["label"],
        )
        figure.update_yaxes(range=[0, max(values) * 1.25])
        return figure_html(figure)

    # An employee with fewer placed orders than this gets a "based on only N orders" note
    # on the category mix chart, because a handful of orders can make one category look huge.
    MIX_MIN_ORDERS = 20

    def category_mix_plot(self, you_label="You"):
        """
        Grouped bar chart of category mix: for each category, this employee's share of
        their own revenue next to the whole team's share of the team's revenue. Each
        set of shares adds up to 100%, so the chart shows what each side sells rather
        than who sells more. A category one side never sold is a 0% bar, so the two
        series always line up. None when this employee has no placed orders.

        The team's figures are grouped in the database and only the combined share per
        category is kept here, never a colleague's row, so nothing about another
        employee reaches the page. With fewer than MIX_MIN_ORDERS orders the title says
        how few the chart rests on.
        """
        mine = self._order_lines_frame()
        if mine.empty:
            return None
        mine_by_category = mine.groupby("category_name")["revenue"].sum()
        team_rows = (
            OrderDetail.objects.filter(order__order_date__isnull=False, order__employee__isnull=False)
            .values(category=F("product__category__category_name"))
            .annotate(revenue=Sum(Supplier._line_revenue()))
        )
        team_by_category = pd.Series(
            {(row["category"] or "Uncategorized"): row["revenue"] for row in team_rows}, dtype=float
        )

        mix = pd.DataFrame({"you": mine_by_category, "team": team_by_category}).fillna(0)
        mix["you"] = mix["you"] / mix["you"].sum() * 100
        mix["team"] = mix["team"] / mix["team"].sum() * 100
        mix = mix.sort_values("team", ascending=False)

        orders = int(mine["order_id"].nunique())
        note = f" (based on only {orders} orders)" if orders < self.MIX_MIN_ORDERS else ""
        figure = go.Figure()
        for column, name, color in (("you", you_label, CHART_COLORS[0]), ("team", "Team", "#5f6b76")):
            figure.add_bar(
                x=list(mix.index), y=list(mix[column]), name=name, marker_color=color,
                text=[f"{v:.1f}%" for v in mix[column]], textposition="outside", cliponaxis=False,
                hovertemplate="<b>%{x}</b><br>" + name + ": %{y:.1f}% of revenue<extra></extra>",
            )
        figure.update_layout(
            title=f"Category mix: {you_label} compared with the team{note}", barmode="group", height=420,
            yaxis_title="Share of revenue (%)", legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "xanchor": "right", "x": 1.0},
        )
        figure.update_yaxes(range=[0, mix.to_numpy().max() * 1.25])
        return figure_html(figure)

    def leaderboard(self):
        """
        Every employee ranked by revenue, as a list of dicts for the
        manager-only leaderboard table: rank, name, orders, revenue,
        average_order, share, is_self (True on this page's employee).
        Names and dollars for every employee, so the view only calls
        this for a manager; everyone else gets team_comparison(), which
        shows averages and a nameless best instead of other people.
        """
        frame = self._performance_frame()
        if frame.empty:
            return []
        names = {e.employee_id: f"{e.first_name} {e.last_name}" for e in Employee.objects.all()}
        return [
            {
                "rank": int(row.revenue_rank),
                "name": names.get(row.employee_key, "Unknown"),
                "orders": row.orders,
                "revenue": row.revenue,
                "average_order": row.average_order,
                "share": row.share,
                "is_self": row.employee_key == self.employee_id,
            }
            for row in frame.itertuples()
        ]

    def customer_revenue_plot(self, top=10, kind="bar"):
        """
        Revenue on this employee's orders by customer, as kind="bar" (horizontal bars,
        largest at the top; the default), "column" (vertical bars, largest first) or
        "pie". top=10 keeps the ten biggest customers and top=None charts every
        customer; each bar is labeled with its dollars and the percentage of this
        employee's total revenue (all customers, not just the ones charted). A pie
        shows each customer's share, the largest ten at most plus the rest as "Other".
        """
        frame = self._order_lines_frame()
        if frame.empty:
            return None
        by_customer = (
            frame.groupby("customer_name", as_index=False)["revenue"].sum()
            .sort_values("revenue")
        )
        total = by_customer["revenue"].sum()
        if kind == "pie":
            slices = top_with_other(by_customer, "customer_name", "revenue", min(top or 10, 10))
            return pie_figure(slices, "customer_name", "revenue", "Share of revenue by customer",
                              color_names=frame["customer_name"])
        if top:
            by_customer = by_customer.tail(top)
        # Horizontal bars list the largest at the top; columns run largest first, left to right.
        horizontal = kind != "column"
        if not horizontal:
            by_customer = by_customer.iloc[::-1]
        text = [f"${row.revenue:,.0f} ({row.revenue / total * 100:.1f}%)" for row in by_customer.itertuples()]
        # Same sizing rule as revenue_breakdown_plot, so the two charts sharing a dashboard row match.
        per_bar = 32 if len(by_customer) <= 12 else 24
        return bar_figure(
            by_customer, "customer_name", "revenue",
            f"Top {top} customers by revenue" if top else "Revenue by customer",
            {"customer_name": "Customer", "revenue": "Revenue ($)"},
            color_names=frame["customer_name"], horizontal=horizontal,
            height=max(420, per_bar * len(by_customer) + 100) if horizontal else 420, trend=False, text=text,
        )

    # What the dashboard's "Revenue by" dropdown can group by: the key, the
    # singular word used in chart titles, and the OrderDetail field to group on.
    BREAKDOWNS = {
        "supplier": ("supplier", "product__supplier__company_name"),
        "product": ("product", "product__product_name"),
        "category": ("category", "product__category__category_name"),
    }

    def revenue_breakdown_plot(self, by="supplier", all_orders=False, top=None, kind="bar"):
        """
        Horizontal bar chart of revenue by supplier, product or category
        (by = "supplier", "product" or "category"), largest at the top. What it
        shows depends on who is looking (the view passes
        all_orders=viewer.is_manager):

        all_orders=True (a manager): each group's revenue across every placed
        order, labeled with its dollars and its percentage of all revenue.

        all_orders=False (anyone else): the share of each group's revenue that came
        from this employee's own orders, as a percentage. Only the percentage is
        charted, never the group's total, so an employee sees what they brought in
        without seeing what the group earns overall.

        top limits the chart to the largest N bars; None shows every group. Colors
        come from the full list of groups, so a group keeps its color whichever top
        is chosen. The rows are grouped in the database with values()/annotate().

        kind is "bar" (horizontal, the default), "column" (vertical) or "pie". A pie is
        for a manager only, because an employee's bars are shares of different totals
        that don't add up to a whole; it shows each group's share of all revenue, the
        largest ten at most plus the rest as "Other".
        """
        word, field = self.BREAKDOWNS[by]
        placed = OrderDetail.objects.filter(order__order_date__isnull=False)
        revenue = Sum(Supplier._line_revenue())

        def revenue_by_group(lines):
            rows = lines.values(group_name=F(field)).annotate(revenue=revenue)
            frame = pd.DataFrame(list(rows))
            if frame.empty:
                return frame
            frame["group_name"] = frame["group_name"].fillna(f"Unknown {word}")
            return frame.groupby("group_name", as_index=False)["revenue"].sum()

        totals = revenue_by_group(placed)
        if totals.empty:
            return None

        if all_orders:
            chart_data = totals.copy()
            chart_data["percent"] = chart_data["revenue"] / chart_data["revenue"].sum() * 100
            chart_data = chart_data.sort_values("revenue", ascending=False)
            value, title = "revenue", f"Revenue by {word} (all orders)"
            labels = {"group_name": word.capitalize(), "revenue": "Revenue ($)"}
        else:
            mine = revenue_by_group(placed.filter(order__employee=self))
            chart_data = totals.merge(mine, on="group_name", how="left", suffixes=("_all", "_mine"))
            chart_data["revenue_mine"] = chart_data["revenue_mine"].fillna(0)
            chart_data = chart_data[chart_data["revenue_all"] > 0]
            chart_data["share"] = chart_data["revenue_mine"] / chart_data["revenue_all"] * 100
            chart_data["percent"] = chart_data["share"]
            chart_data = chart_data.sort_values("share", ascending=False)
            value, title = "share", f"Your share of each {word}'s revenue (%)"
            labels = {"group_name": word.capitalize(), "share": f"Share of {word} revenue (%)"}

        if kind == "pie" and all_orders:
            slices = top_with_other(chart_data, "group_name", "revenue", min(top or 10, 10))
            return pie_figure(slices, "group_name", "revenue", f"Share of revenue by {word}",
                              color_names=totals["group_name"])

        if top:
            chart_data = chart_data.head(top)
            title = f"{title} -- top {top}"
        # Plotly draws the first horizontal bar at the bottom, so bars flip to put the largest
        # on top; columns already run largest first, left to right.
        horizontal = kind != "column"
        if horizontal:
            chart_data = chart_data.iloc[::-1]

        if all_orders:
            text = [f"${row.revenue:,.0f} ({row.percent:.1f}%)" for row in chart_data.itertuples()]
        else:
            text = [f"{row.percent:.1f}%" for row in chart_data.itertuples()]

        per_bar = 32 if len(chart_data) <= 12 else 24
        return bar_figure(
            chart_data, "group_name", value, title, labels,
            color_names=totals["group_name"], horizontal=horizontal,
            height=max(420, per_bar * len(chart_data) + 100) if horizontal else 420, trend=False, text=text,
        )

    @classmethod
    def authenticate(cls, employee_id, password):
        """
        Looks up the employee picked in the login form and checks their
        password: the 4-digit year of their own birth_date, as a string
        (e.g. birth_date of 1985-03-12 -> password "1985"). Returns the
        matching Employee on success, or None if the employee_id doesn't
        exist, has no birth_date on record, or the password is wrong.
        """
        employee = cls.objects.filter(pk=employee_id).first()
        if employee is None or employee.birth_date is None:
            return None
        if str(employee.birth_date.year) != password:
            return None
        return employee

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
        """This order's total: every line item's line_total (OrderDetail.line_total) added together."""
        return sum(line.line_total for line in self.orderdetail_set.all())

    @property
    def formatted_ship_address(self):
        """This order's ship_* address fields joined into one line, blanks skipped."""
        parts = [self.ship_address, self.ship_city, self.ship_region, self.ship_postal_code, self.ship_country]
        return ", ".join(part for part in parts if part)

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
        """discontinued is a plain 1/0 column; this maps it to a real bool. A @property is computed on each access, so it needs no migration."""
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
    def generate_product_id(cls):
        """
        products.product_id has no auto-increment in the database, so a
        new product's ID is the current highest ID plus one -- the same
        "never typed by the user" idea as Customer.generate_customer_id.
        """
        highest = cls.objects.order_by("-product_id").first()
        return (highest.product_id + 1) if highest else 1

    @classmethod
    def search(cls, product_name="", category_id="", supplier_id="", show_all=False):
        """
        Filters products by an optional name (case-insensitive substring) and
        supplier (exact) and category (exact, since it comes from a dropdown), for product_list's search
        form. Discontinued products are left out unless show_all is True; the
        filter uses the raw 1/0 column, because the database can't filter on the
        is_discontinued property.
        """
        queryset = cls.objects.order_by("product_name")
        if product_name:
            queryset = queryset.filter(product_name__icontains=product_name)

        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)

        if category_id:
            queryset = queryset.filter(category_id=category_id)

        if not show_all:
            queryset = queryset.filter(discontinued=0)

        return queryset

    @property
    def total_revenue(self):
        """Total revenue from this product: every line it appears on, each line_total added together (orderdetail_set is the reverse side of OrderDetail.product)."""
        return sum(line.line_total for line in self.orderdetail_set.all())

    @property
    def units_sold(self):
        """Total quantity of this product sold, across every order line it appears on."""
        return sum(line.quantity for line in self.orderdetail_set.all())

    class Meta:
        managed = False
        db_table = 'products'


class Shipper(models.Model):
    """A shipping carrier. No foreign keys."""
    shipper_id = models.SmallIntegerField(primary_key=True)
    company_name = models.CharField(max_length=40)
    phone = models.CharField(max_length=24, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'shippers'


class Supplier(DashboardChartsMixin, models.Model):
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

    # region [WHY] a fixed shared password for suppliers
    # The suppliers table has no password column, and this app's tables are unmanaged,
    # so there is nowhere to store one per supplier. Every supplier logs in with this
    # one demo password. A real app would store a hashed password per supplier.
    # endregion
    SHARED_PASSWORD = "pass"

    @classmethod
    def authenticate(cls, supplier_id, password):
        """Checks a login: the supplier picked in the dropdown and the shared password. An unknown or non-numeric supplier_id is a failed login, not a crash."""
        try:
            supplier = cls.objects.filter(pk=int(supplier_id)).first()
        except (TypeError, ValueError):
            return None
        if supplier is None or password != cls.SHARED_PASSWORD:
            return None
        return supplier

    @property
    def formatted_address(self):
        """Address, city, region, postal_code, and country joined into one line (blank ones skipped)."""
        parts = [self.address, self.city, self.region, self.postal_code, self.country]
        return ", ".join(part for part in parts if part)

    def _placed_lines(self):
        """Every line on a placed order for one of this supplier's products (product__supplier=self follows OrderDetail -> Product -> Supplier in one query)."""
        return OrderDetail.objects.filter(
            product__supplier=self, order__order_date__isnull=False
        )

    @staticmethod
    def _line_revenue():
        """The database-side version of OrderDetail.line_total, for Sum(): unit_price * quantity * (1 - discount)."""
        return ExpressionWrapper(
            F("unit_price") * F("quantity") * (1 - F("discount")),
            output_field=FloatField(),
        )

    def summary(self):
        """Headline numbers for the Info tab: products, units sold, revenue, orders (revenue and units from placed orders only)."""
        totals = self._placed_lines().aggregate(
            units=Sum("quantity"),
            revenue=Sum(self._line_revenue()),
            orders=Count("order_id", distinct=True),
        )
        return {
            "product_count": self.product_set.count(),
            "units": totals["units"] or 0,
            "revenue": totals["revenue"] or 0,
            "orders": totals["orders"],
        }

    def order_history(self):
        """
        One row per placed order that includes at least one of this
        supplier's products, newest first: order_id, order_date, the
        customer's company name, how many of this supplier's products
        were on the order, and the units and revenue for those lines
        only -- never the rest of the order, which belongs to other
        suppliers too. values() picks the columns to group by and
        annotate() adds the per-group totals.
        """
        return (
            self._placed_lines()
            .values("order_id", "order__order_date", "order__customer__company_name")
            .annotate(
                products=Count("product_id", distinct=True),
                units=Sum("quantity"),
                revenue=Sum(self._line_revenue()),
            )
            .order_by("-order__order_date", "-order_id")
        )

    def product_revenue(self):
        """
        One row per product this supplier provides (including products
        with no sales yet, shown as zeros), largest revenue first:
        product_id, product_name, category_name, units, revenue, orders.
        """
        sales = {
            row["product_id"]: row
            for row in self._placed_lines()
            .values("product_id")
            .annotate(
                units=Sum("quantity"),
                revenue=Sum(self._line_revenue()),
                orders=Count("order_id", distinct=True),
            )
        }
        rows = []
        for product in self.product_set.select_related("category"):
            sold = sales.get(product.product_id, {})
            rows.append({
                "product_id": product.product_id,
                "product_name": product.product_name,
                "category_name": product.category.category_name if product.category else "—",
                "units": sold.get("units", 0),
                "revenue": sold.get("revenue", 0),
                "orders": sold.get("orders", 0),
            })
        return sorted(rows, key=lambda row: row["revenue"], reverse=True)

    # region [CONCEPT] the supplier dashboard
    # Every method below starts from _placed_lines(), which is already limited to this
    # supplier's products, so no chart can include another supplier's sales. Each pulls
    # the lines into a DataFrame (_order_lines_frame), groups them with pandas and hands the
    # result to a helper in charts.py, like the customer and employee dashboards.
    # The one place other suppliers' numbers are touched is comparison(): see its note.
    # endregion
    def _order_lines_frame(self, extra=None):
        """This supplier's placed order lines as a DataFrame (lines_frame in charts.py); extra adds columns, e.g. {"discontinued": "product__discontinued"}."""
        return lines_frame(self._placed_lines(), extra=extra)

    def order_years(self):
        """Distinct years this supplier's products were sold in, newest first."""
        years = self._placed_lines().values_list("order__order_date__year", flat=True).distinct()
        return sorted(years, reverse=True)

    def top_products_plot(self, top=10, measure="revenue", include_discontinued=False, year=None):
        """
        Horizontal bar chart of this supplier's top products by revenue or by units
        (measure = "revenue" or "quantity"), for one year or all of them. Discontinued
        products are left out unless include_discontinued. None when none qualify.
        """
        frame = self._year_frame(year, extra={"discontinued": "product__discontinued"})
        if not frame.empty and not include_discontinued:
            frame = frame[frame["discontinued"] != 1]
        return self._top_products_figure(frame, top, measure)

    def top_customers(self, limit=10):
        """
        This supplier's best customers by what they spent on this supplier's
        products, as a list of dicts: company_name, orders and share (percent of
        this supplier's revenue). Nothing else about a customer, and nothing about
        what else they buy, is ever read.
        """
        frame = self._order_lines_frame()
        if frame.empty:
            return []
        total = frame["revenue"].sum()
        grouped = (
            frame.groupby("customer_name")
            .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
            .sort_values("revenue", ascending=False).head(limit)
        )
        return [
            {"company_name": name, "orders": int(row["orders"]), "revenue": float(row["revenue"]),
             "share": float(row["revenue"] / total * 100)}
            for name, row in grouped.iterrows()
        ]

    # What the comparison chart's dropdown can compare: the key and its label.
    SUPPLIER_MEASURES = {"revenue": "Revenue", "orders": "Orders", "units": "Units sold"}

    # region [CONCEPT] comparing without revealing
    # comparison() has to look at every supplier to find an average and a best, but
    # only three numbers leave it. The best is a number (frame[measure].max()), not a
    # row (sort_values(...).iloc[-1]), because a row carries its supplier with it. The
    # per-supplier frame stays inside this method, so nothing about any other supplier
    # reaches the view, the template or the page source.
    # endregion
    def comparison(self, measure="revenue"):
        """
        This supplier against all suppliers on one measure (a SUPPLIER_MEASURES key):
        {"label", "kind", "you", "average", "best"}, where average is over the
        suppliers that sold anything and best is the highest of them, unnamed.
        None when nothing has been sold at all.
        """
        if measure not in self.SUPPLIER_MEASURES:
            return None
        rows = (
            OrderDetail.objects.filter(order__order_date__isnull=False, product__supplier__isnull=False)
            .values(supplier_key=F("product__supplier_id"))
            .annotate(
                revenue=Sum(self._line_revenue()),
                orders=Count("order", distinct=True),
                units=Sum("quantity"),
            )
        )
        frame = pd.DataFrame(list(rows))
        if frame.empty:
            return None
        mine = frame.loc[frame["supplier_key"] == self.pk, measure]
        return {
            "label": self.SUPPLIER_MEASURES[measure],
            "kind": "money" if measure == "revenue" else "count",
            "you": float(mine.iloc[0]) if len(mine) else 0.0,
            "average": float(frame[measure].mean()),
            "best": float(frame[measure].max()),
        }

    def comparison_plot(self, measure="revenue"):
        """Bar chart for one measure: this supplier, the average of all suppliers and the best supplier (unnamed), in real units. None when there is nothing to compare."""
        row = self.comparison(measure)
        if row is None:
            return None
        names = ["You", "All-supplier average", "Best supplier"]
        values = [row["you"], row["average"], row["best"]]
        is_money = row["kind"] == "money"
        text = [f"${v:,.0f}" if is_money else f"{v:,.0f}" for v in values]
        figure = go.Figure(go.Bar(
            x=names, y=values, text=text, textposition="outside", cliponaxis=False,
            marker_color=[CHART_COLORS[0], "#5f6b76", CHART_COLORS[2]],
            hovertemplate="<b>%{x}</b><br>%{text}<extra></extra>",
        ))
        figure.update_layout(
            title=f"{row['label']}: you compared with all suppliers", height=340,
            yaxis_title="Revenue ($)" if is_money else row["label"],
        )
        figure.update_yaxes(range=[0, (max(values) or 1) * 1.25])
        return figure_html(figure)

    # region [CONCEPT] Requirement 4: where do my sales come from?
    # The chart answers "which countries do my customers buy from, and how much of my
    # sales does each one account for?". The country is added to the frame with lines_frame's
    # extra argument (the customer's country, order -> customer -> country); the customer's
    # name is never used, and only totals per country leave the method, so the chart reads as
    # countries and never as customers. A horizontal bar suits it better than a pie (a supplier
    # can sell to a couple of dozen countries, too many slices to tell apart) or a map (it would
    # need every country name matched to a map region, and shows dollars less exactly): a bar
    # ranks the countries and can show the value and its percent share on the same label.
    # endregion
    # What the country chart can count: the key and its label.
    COUNTRY_MEASURES = {"revenue": "Revenue", "units": "Units sold", "orders": "Orders"}

    # The customers table spells a country two ways in places ("USA" for most customers,
    # "United States" for one). The chart counts the second spelling as the first, so one
    # country is one bar; nothing in the database is changed.
    COUNTRY_ALIASES = {"United States": "USA"}

    def country_sales_plot(self, year=None, measure="revenue"):
        """
        Horizontal bar chart of this supplier's sales by the customer's country
        (measure = a COUNTRY_MEASURES key), for one year or all of them, largest at
        the top. Each bar is labeled with its value and its share of the total, and
        its hover repeats both. A customer with no country on record is counted under
        "Unknown country", and COUNTRY_ALIASES merges two spellings of one country.
        Countries only: no customer is named or counted. Returns None when there are
        no sales.
        """
        every_year = self._order_lines_frame(extra={"country": "order__customer__country"})
        if every_year.empty:
            return None
        every_year["country"] = (
            every_year["country"].fillna("Unknown country").str.strip().replace(self.COUNTRY_ALIASES)
        )
        frame = every_year if year is None else every_year[every_year["year"] == year]
        if frame.empty:
            return None

        by_country = frame.groupby("country").agg(
            revenue=("revenue", "sum"), units=("quantity", "sum"), orders=("order_id", "nunique")
        )
        data = by_country[[measure]].reset_index().sort_values(measure)
        data["percent"] = data[measure] / data[measure].sum() * 100
        label = self.COUNTRY_MEASURES[measure]
        money = "$" if measure == "revenue" else ""
        shown = [f"{money}{v:,.0f} ({p:.1f}%)" for v, p in zip(data[measure], data["percent"])]
        scope = f", {year}" if year else ""
        return bar_figure(
            data, "country", measure, f"{label} by customer country{scope}",
            {"country": "Customer country", measure: "Revenue ($)" if measure == "revenue" else label},
            color_names=every_year["country"], horizontal=True, trend=False,
            height=max(260, 42 * len(data) + 120), text=shown,
            hover=[f"<b>{c}</b><br>{label}: {t}" for c, t in zip(data["country"], shown)],
        )

    class Meta:
        managed = False
        db_table = 'suppliers'