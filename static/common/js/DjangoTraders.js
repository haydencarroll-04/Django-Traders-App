/*
    Project-wide custom JavaScript.

    Lives in static/common/js/ (project-root static/ folder, registered
    via STATICFILES_DIRS in settings.py), parallel to templates/common/
    holding the project-wide base.html. Loaded from base.html after
    jQuery and DataTables, so anything here can rely on both already
    being present.

    Each Make*DataTable(tableId) function below applies DataTables to
    one named table by id -- pageLength/lengthMenu raise DataTables'
    own default of 10 rows per page and the choices in its "Show N
    entries" dropdown. Kept as one function per table, repeating the
    same settings, rather than a shared helper -- simple beats DRY
    here: a table with its own quirk (an unsortable icon column, a
    custom sort order) just sets that option in its own function
    instead of a generic helper needing extra parameters to handle
    every table's special case.

    MakeCustomersDataTable (customer_list.html) also disables sorting
    on its Actions column (an icon, not sortable data), and swaps the
    entries-per-page dropdown and "Showing X of Y" positions.
    MakeProductsDataTable (product_list.html) also disables sorting on
    its Actions column. MakeOrdersDataTable (customer_detail.html) and
    MakeProductOrdersDataTable (product_detail.html) both default to
    sorting by Order Date, descending, instead of DataTables' own
    default (first column, ascending). MakeOrderDetailsDataTable
    (order_detail.html) uses the plain defaults -- no special options
    needed.

    ValidateCustomerEditForm (customer_edit.html) is a hand-written
    jQuery illustration of client-side validation, alongside (not
    instead of) the HTML5 pattern= attributes and Django's own
    clean_<field>() methods (djtraders/forms.py) already doing the
    real work -- see its own comment below.

    AddOrderLineItem and UpdateCartQuantities (order_build.html) make up
    this project's one AJAX-driven workflow, the shopping cart -- see
    their own comments below.
*/

// #region DataTables activation functions
function MakeCustomersDataTable(tableId) {
    $(tableId).DataTable({
        pageLength: 20,
        lengthMenu: [ [10, 20, 25, 50, -1], [10, 20, 25, 50, "All"] ],
        columnDefs: [
            { targets: -1, orderable: false }
        ],
        layout: {
            topStart: 'info',
            topEnd: 'search',
            bottomStart: 'pageLength',
            bottomEnd: 'paging'
        },
    });
}

function MakeProductsDataTable(tableId) {
    $(tableId).DataTable({
        pageLength: 20,
        lengthMenu: [ [10, 20, 25, 50, -1], [10, 20, 25, 50, "All"] ],
        columnDefs: [
            { targets: -1, orderable: false }
        ],
        layout: {
            topStart: 'info',
            topEnd: 'search',
            bottomStart: 'pageLength',
            bottomEnd: 'paging'
        }
    });
}

function MakeOrdersDataTable(tableId) {
    $(tableId).DataTable({
        pageLength: 20,
        lengthMenu: [ [10, 20, 25, 50, -1], [10, 20, 25, 50, "All"] ],
        // Column 1 is Order Date; 'desc' shows the most recent order first
        // by default, instead of DataTables' own default (column 0, asc).
        order: [[1, 'desc']]
    });
}

function MakeOrderDetailsDataTable(tableId) {
    $(tableId).DataTable({
        pageLength: 20,
        lengthMenu: [ [10, 20, 25, 50, -1], [10, 20, 25, 50, "All"] ]
    });
}

function MakeProductOrdersDataTable(tableId) {
    $(tableId).DataTable({
        pageLength: 20,
        lengthMenu: [ [10, 20, 25, 50, -1], [10, 20, 25, 50, "All"] ],
        // Column 1 is Order Date; 'desc' shows the most recent order first
        // by default, instead of DataTables' own default (column 0, asc).
        order: [[1, 'desc']]
    });
}
// #endregion

/*
    ValidateCustomerEditForm -- client-side validation for customer_edit.html,
    layered alongside (not instead of) the HTML5 pattern= attributes
    CustomerEditForm's __init__ sets AND Django's own server-side check
    (clean_phone()/clean_company_name()/clean_city(), djtraders/forms.py).
    The server-side check is the one that actually enforces the rule --
    this only improves the browser experience.

    Its three regexes are hand-copied from forms.py's PHONE_PATTERN/
    NO_DIGITS_PATTERN. A static .js file can't import from a Python
    module, so the two copies have to be kept in sync by hand; if they
    ever drift apart, the server-side check still wins because it runs
    last and is the actual gate.

    Uses a plain 'submit' event listener with preventDefault() on
    failure, not AJAX -- the page still does a full POST/redirect on
    success. Note: a script that calls a form's native .submit()
    method (rather than a real click or Enter key) does not fire the
    'submit' event at all, so this validation -- like the HTML5
    pattern= attributes -- can be bypassed that way. That's inherent
    to client-side validation generally, not a gap specific to this
    function.
*/
function ValidateCustomerEditForm(formId) {
    // Same three patterns as forms.py's PHONE_PATTERN/NO_DIGITS_PATTERN,
    // hand-copied into JS since a .js file can't import from forms.py.
    const PHONE_PATTERN = /^[0-9()\-\s]{7,20}$/;
    const NO_DIGITS_PATTERN = /^[^0-9]*$/;

    // Shows (or clears) one field's error the same way crispy/Bootstrap
    // already render a server-side error (is-invalid + a sibling
    // .invalid-feedback), so a client-caught error and a server-caught
    // one look identical to someone just looking at the page.
    function setFieldError(fieldId, message) {
        const field = document.getElementById(fieldId);
        let feedback = field.parentElement.querySelector(".js-invalid-feedback");
        if (!feedback) {
            feedback = document.createElement("div");
            feedback.className = "invalid-feedback js-invalid-feedback";
            field.insertAdjacentElement("afterend", feedback);
        }
        if (message) {
            field.classList.add("is-invalid");
            feedback.textContent = message;
            feedback.style.display = "block";
        } else {
            field.classList.remove("is-invalid");
            feedback.style.display = "none";
        }
    }

    $(formId).on("submit", function (event) {
        let valid = true;

        // company_name is required (HTML5 required= already blocks an
        // empty submission before this handler ever runs on a real
        // click) -- an empty value here is skipped, not flagged, so
        // this check never fights with that native "required" message.
        const companyName = $("#id_company_name").val().trim();
        if (companyName && !NO_DIGITS_PATTERN.test(companyName)) {
            setFieldError("id_company_name", "Company name can't contain numbers.");
            valid = false;
        } else {
            setFieldError("id_company_name", null);
        }

        // phone and city are both optional (blank=True, null=True on
        // the model) -- an empty value is valid and skips its pattern
        // check entirely, the same way clean_phone()/clean_city() do
        // server-side (forms.py).
        const phone = $("#id_phone").val().trim();
        if (phone && !PHONE_PATTERN.test(phone)) {
            setFieldError("id_phone", "Enter a valid phone number (digits, spaces, parentheses, and dashes only, 7-20 characters).");
            valid = false;
        } else {
            setFieldError("id_phone", null);
        }

        const city = $("#id_city").val().trim();
        if (city && !NO_DIGITS_PATTERN.test(city)) {
            setFieldError("id_city", "City can't contain numbers.");
            valid = false;
        } else {
            setFieldError("id_city", null);
        }

        if (!valid) {
            event.preventDefault();
        }
    });
}

/*
    AddOrderLineItem -- intercepts order_build.html's Add Line Item
    form and POSTs to order_add_line (djtraders/views.py) via AJAX,
    patching the page in place instead of reloading it. This is the
    project's one AJAX-driven view: a customer can add several products
    in a row without the page reloading each time, then commit the
    whole order at once.

    Only checks the bare minimum client-side before submitting -- a
    product is selected, and quantity is a positive number. It does
    not check the selected product's stock; that check is server-side
    only, in OrderDetailForm/order_add_line, and is the authoritative one.

    formId: the Add Line Item <form>'s own id ("#order-detail-form"),
    passed in from order_build.html's {% block scripts %} rather than
    hard-coded, the same way ValidateCustomerEditForm takes its form id
    as an argument.
*/
function AddOrderLineItem(formId) {
    const $form = $(formId);
    const $errorBox = $form.find("#order-detail-form-error");
    // Browser layer (courtesy only) of the stock rule. order_add_line's
    // OrderDetailForm.clean() is the real check; this just stops an
    // obviously-too-large quantity before a request is sent.
    const stockElement = document.getElementById("stock-map");
    const stockMap = stockElement ? JSON.parse(stockElement.textContent) : {};

    $("#id_product").on("change", function () {
        const stock = stockMap[$(this).val()];
        if (stock === undefined) {
            $("#id_quantity").removeAttr("max");
        } else {
            $("#id_quantity").attr("max", stock);
        }
    });

    function showError(message) {
        $errorBox.text(message).removeClass("d-none");
    }

    function clearError() {
        $errorBox.text("").addClass("d-none");
    }

    $form.on("submit", function (event) {
        event.preventDefault();
        clearError();

        const $productSelect = $("#id_product");
        const productId = $productSelect.val();
        const quantity = parseInt($("#id_quantity").val(), 10);

        if (!productId) {
            showError("Select a product.");
            return;
        }
        if (!quantity || quantity < 1) {
            showError("Quantity must be at least 1.");
            return;
        }
        const inStock = stockMap[productId];
        if (inStock !== undefined && quantity > inStock) {
            showError("Only " + inStock + " in stock.");
            return;
        }

        // Errors come back either as plain strings (order_add_line's own
        // access/state checks, views.py) or as {message, code} objects
        // (Django's form.errors.get_json_data(), for OrderDetailForm's
        // field validation) -- normalized to plain text either way.
        function messagesFrom(errors) {
            return Object.values(errors || {})
                .flat()
                .map((error) => (typeof error === "string" ? error : error.message));
        }

        $.ajax({
            url: $form.attr("action"),
            method: "POST",
            data: $form.serialize(),
            dataType: "json",
        }).done(function (response) {
            if (!response.success) {
                showError(messagesFrom(response.errors).join(" ") || "Couldn't add that to your cart.");
                return;
            }

            $("#order-lines-empty-row").remove();
            const $existingRow = $(`#order-lines-body tr[data-product-id="${response.product_id}"]`);
            if ($existingRow.length) {
                $existingRow.replaceWith(response.row_html);
            } else {
                $("#order-lines-body").append(response.row_html);
            }
            $("#order-total").text("$" + response.order_total);
            $("#id_quantity").val(1);
            $("#id_discount_percent").val("");
            $("#id_manager_approved").prop("checked", false);
            $productSelect.val("");
        }).fail(function (xhr) {
            // A validation failure (order_add_line's own 400/403 JsonResponse,
            // views.py) lands here, not in .done() above -- jQuery treats
            // any non-2xx HTTP status as a failure regardless of the
            // response body, so the real error message has to be read
            // from xhr.responseJSON. Fall back to a generic message only
            // when there's no JSON to read (a network failure or 500).
            const messages = xhr.responseJSON ? messagesFrom(xhr.responseJSON.errors) : [];
            showError(messages.join(" ") || "Something went wrong adding that to your cart -- try again.");
        });
    });
}


/*
    UpdateCartQuantities -- lets the shopper change a cart line's quantity
    right in its row of order_build.html. Every row has a small <form>
    (_order_line_row.html) holding a Quantity box and an Update button;
    this intercepts that form's submit and POSTs it to order_update_line
    (djtraders/views.py) via AJAX, then swaps in the refreshed row and the
    new Order Total -- no page reload, so anything already typed into the
    Add to Cart or Place Order cards (Ship To, dates) is left alone.

    The listener is attached once, to the table body, and picks up a
    submit from any row inside it ("event delegation"). A listener on each
    row would be lost every time a row is replaced -- which happens on
    every update here and on every add in AddOrderLineItem -- so rows
    added or refreshed after the page loaded still work with no re-wiring.

    As with AddOrderLineItem, the real check (a whole number, at least 1,
    no more than the stock on hand) is server-side, in
    OrderLineQuantityForm; the min=/max= on the box are courtesy only.

    tableBodyId: the <tbody> holding the rows ("#order-lines-body").
    errorBoxId: the red alert above the table ("#order-lines-error").
    Both are passed in from order_build.html's {% block scripts %}.
*/
function UpdateCartQuantities(tableBodyId, errorBoxId) {
    const $body = $(tableBodyId);
    const $errorBox = $(errorBoxId);

    // Scoped to the table body so the Add to Cart form's own quantity box
    // (also named "quantity") is never touched.
    function showError(message, $input) {
        $body.find("input[name='quantity']").removeClass("is-invalid");
        $input.addClass("is-invalid");
        $errorBox.text(message).removeClass("d-none");
    }

    function clearError() {
        $body.find("input[name='quantity']").removeClass("is-invalid");
        $errorBox.text("").addClass("d-none");
    }

    // Same normalizing as AddOrderLineItem: errors arrive either as plain
    // strings (order_update_line's own access/state checks, views.py) or
    // as {message, code} objects (Django's form.errors.get_json_data()).
    function messagesFrom(errors) {
        return Object.values(errors || {})
            .flat()
            .map((error) => (typeof error === "string" ? error : error.message));
    }

    $body.on("submit", ".order-line-quantity-form", function (event) {
        event.preventDefault();
        const $form = $(this);
        const $input = $form.find("input[name='quantity']");
        const $button = $form.find("button[type='submit']");
        clearError();
        $button.prop("disabled", true);

        $.ajax({
            url: $form.attr("action"),
            method: "POST",
            data: $form.serialize(),
            dataType: "json",
        }).done(function (response) {
            if (!response.success) {
                showError(messagesFrom(response.errors).join(" ") || "Couldn't update that quantity.", $input);
                return;
            }
            // The whole row is replaced, not just the number, so the
            // discount, Volume badge, and line total all stay in step.
            $form.closest("tr").replaceWith(response.row_html);
            $("#order-total").text("$" + response.order_total);
        }).fail(function (xhr) {
            // A refused update (order_update_line's 400/403 JsonResponse)
            // lands here, not in .done() -- read the real message from
            // xhr.responseJSON, same as AddOrderLineItem does.
            const messages = xhr.responseJSON ? messagesFrom(xhr.responseJSON.errors) : [];
            showError(messages.join(" ") || "Something went wrong updating that quantity -- try again.", $input);
        }).always(function () {
            $button.prop("disabled", false);
        });
    });
}


/*
 * SetUpProductFilter -- narrows order_build.html's Product dropdown as the
 * user types in the search box or picks a category (enhancement #2). Purely
 * a usability aid: it only changes which <option>s are listed, never what
 * gets submitted -- order_add_line still validates the chosen product and
 * quantity on the server. The full option list is remembered once at load
 * and the <select> is rebuilt from it on every change, since hiding
 * <option> elements isn't reliable across browsers.
 */
function SetUpProductFilter() {
    const $select = $("#id_product");
    const $text = $("#product-filter-text");
    const $category = $("#product-filter-category");
    const $count = $("#product-filter-count");
    if (!$select.length || !$text.length) {
        return;
    }

    // {product_id: category_id} sent by order_build (_product_picker_context).
    const categoryElement = document.getElementById("product-category-map");
    const categoryMap = categoryElement ? JSON.parse(categoryElement.textContent) : {};

    const placeholderText = $select.find("option[value='']").text() || "Select a product...";
    const allOptions = Array.from($select[0].options)
        .filter((option) => option.value !== "")
        .map((option) => ({ value: option.value, text: option.text }));

    function applyFilter() {
        const needle = $text.val().trim().toLowerCase();
        const categoryId = $category.val();
        const previous = $select.val();

        const matches = allOptions.filter(
            (option) =>
                (!needle || option.text.toLowerCase().includes(needle)) &&
                (!categoryId || String(categoryMap[option.value]) === categoryId)
        );

        $select.empty().append(new Option(placeholderText, ""));
        matches.forEach((option) => $select.append(new Option(option.text, option.value)));
        // Keep the previous choice if it's still in the list.
        $select.val(matches.some((option) => option.value === previous) ? previous : "");
        // Tell the stock-limit code (AddOrderLineItem) the selection may have changed.
        $select.trigger("change");

        $count.text(
            matches.length === allOptions.length
                ? ""
                : matches.length + " of " + allOptions.length + " products shown"
        );
    }

    $text.on("input", applyFilter);
    $category.on("change", applyFilter);
    // Enter in the search box would otherwise submit the whole Add to Cart form.
    $text.on("keydown", function (event) {
        if (event.key === "Enter") {
            event.preventDefault();
        }
    });
    $("#product-filter-reset").on("click", function () {
        $text.val("");
        $category.val("");
        applyFilter();
    });
}
