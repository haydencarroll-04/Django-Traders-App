/**
 * Suppliers: the dashboard controls that reload one chart (the last one is Requirement 4's). Loaded by base.html after
 * DjangoTraders.js, whose LoadPageTab calls each Activate function below once the Dashboard
 * tab's HTML is in the page. The monthly chart's Year dropdown is wired by
 * ActivateYearDropdown (customers.js), which both dashboards share.
 */

/**
 * Supplier and customer dashboards: the Year dropdown and the "Unit share as" radio buttons
 * (Percent bars, Pie) both reload the two category charts in #dashboard-categories. The
 * first charts arrive already drawn. Each dashboard's #category-controls carries the URL of
 * its own view in data-url, so this one function serves both.
 * @param {jQuery} $pane - the tab pane that was just loaded
 */
function ActivateCategoryControls($pane) {
    const $controls = $pane.find("#category-controls");
    if ($controls.length === 0) {
        return;
    }
    const $year = $controls.find("#category-year");
    const $kind = $controls.find("input[name='category-kind']");
    function loadCategories() {
        $.get($controls.data("url"), { year: $year.val(), kind: $kind.filter(":checked").val() })
            .done(function (html) { $("#dashboard-categories").html(html); })
            .fail(function () { $("#dashboard-categories").text("Could not load the category charts."); });
    }
    $year.on("change", loadCategories);
    $kind.on("change", loadCategories);
}

/**
 * Supplier dashboard: the "Show Top" dropdown (5, 10, 20), the "Measure" radio buttons
 * (Revenue, Units sold) and the "Include discontinued products" checkbox all reload the
 * chart in #dashboard-top-products. An unchecked box sends 0, a checked one 1. The chart's
 * title names the chosen top; a supplier with fewer products than that sees the same bars
 * for 5, 10 and 20, and the title says how many have sales.
 * @param {jQuery} $pane - the tab pane that was just loaded
 */
function ActivateTopProductControls($pane) {
    const $controls = $pane.find("#top-products-controls");
    if ($controls.length === 0) {
        return;
    }
    const $top = $controls.find("#top-count");
    const $measure = $controls.find("input[name='top-measure']");
    const $discontinued = $controls.find("#top-discontinued");
    function loadTopProducts() {
        $.get($controls.data("url"), {
            top: $top.val(),
            measure: $measure.filter(":checked").val(),
            discontinued: $discontinued.is(":checked") ? 1 : 0
        })
            .done(function (html) { $("#dashboard-top-products").html(html); })
            .fail(function () { $("#dashboard-top-products").text("Could not load the chart."); });
    }
    $top.on("change", loadTopProducts);
    $measure.on("change", loadTopProducts);
    $discontinued.on("change", loadTopProducts);
}

/**
 * Supplier dashboard: the comparison chart's "Compare" dropdown (Revenue, Orders, Units
 * sold) reloads the chart in #dashboard-comparison.
 * @param {jQuery} $pane - the tab pane that was just loaded
 */
function ActivateSupplierComparison($pane) {
    const $controls = $pane.find("#comparison-controls");
    if ($controls.length === 0) {
        return;
    }
    const $measure = $controls.find("#comparison-measure");
    $measure.on("change", function () {
        $.get($controls.data("url"), { measure: $measure.val() })
            .done(function (html) { $("#dashboard-comparison").html(html); })
            .fail(function () { $("#dashboard-comparison").text("Could not load the chart."); });
    });
}

/**
 * Supplier dashboard: the "Where Do My Sales Come From?" chart's Year dropdown and "Measure"
 * radio buttons (Revenue, Units sold, Orders) reload the chart in #dashboard-country. The
 * first chart arrives already drawn.
 * @param {jQuery} $pane - the tab pane that was just loaded
 */
function ActivateCountryControls($pane) {
    const $controls = $pane.find("#country-controls");
    if ($controls.length === 0) {
        return;
    }
    const $year = $controls.find("#country-year");
    const $measure = $controls.find("input[name='country-measure']");
    function loadCountries() {
        $.get($controls.data("url"), { year: $year.val(), measure: $measure.filter(":checked").val() })
            .done(function (html) { $("#dashboard-country").html(html); })
            .fail(function () { $("#dashboard-country").text("Could not load the chart."); });
    }
    $year.on("change", loadCountries);
    $measure.on("change", loadCountries);
}
