/**
 * Orders: the order line-items table and the AJAX "Add to Cart" workflow.
 * Loaded by base.html after DjangoTraders.js.
 */

/**
 * An order's line items, with DataTables' default sorting.
 * @param {string} tableId - selector for the table
 */
function MakeOrderDetailsDataTable(tableId) {
    $(tableId).DataTable({
        pageLength: 20,
        lengthMenu: [[10, 20, 25, 50, -1], [10, 20, 25, 50, "All"]]
    });
}

/**
 * The "Add to Cart" card on order_build.html. Submitting its form POSTs to
 * order_add_line (views/orders.py) by AJAX. On success the server returns JSON with
 * the new row, the running total and a fresh, empty card, which replace what
 * is on the page; on failure only an error message appears. Changing the
 * category filter also swaps in a re-rendered card (order_add_card).
 *
 * The listeners are attached to document (jQuery's delegated form,
 * .on(event, selector, handler)) because swapping the card removes its old
 * elements; for the same reason elements are looked up inside each handler.
 * The checks before submitting are courtesy checks; the server repeats them.
 * @param {string} formId - selector for the form, e.g. "#order-detail-form"
 */
function AddOrderLineItem(formId) {
    ActivateProductSearch();

    // The server sends errors as plain strings or as {message, code}
    // objects, in lists or on their own; this returns just the messages.
    function messagesFrom(errors) {
        const messages = [];
        $.each(errors || {}, function (field, problems) {
            $.each([].concat(problems), function (index, problem) {
                messages.push(typeof problem === "string" ? problem : problem.message);
            });
        });
        return messages;
    }

    function showError(message) {
        $("#order-detail-form-error").text(message).removeClass("d-none");
    }

    $(document).on("change", "#id_category_filter", function () {
        $.get($(this).data("cardUrl"), { category: $(this).val() })
            .done(function (cardHtml) {
                $("#add-to-cart-card").replaceWith(cardHtml);
                ActivateProductSearch();
            })
            .fail(function () {
                showError("Couldn't load that category -- try again.");
            });
    });

    $(document).on("submit", formId, function (event) {
        event.preventDefault();
        const $form = $(this);
        $("#order-detail-form-error").text("").addClass("d-none");

        const productId = $("#id_product").val();
        const quantity = parseInt($("#id_quantity").val(), 10);

        if (!productId) {
            showError("Pick a product from the suggestions.");
            return;
        }
        if (!quantity || quantity < 1) {
            showError("Quantity must be at least 1.");
            return;
        }

        // The card embeds {product_id: units_in_stock} as JSON text in the page.
        const $stockData = $("#product-stock-data");
        const productStock = $stockData.length ? JSON.parse($stockData.text()) : {};
        const unitsInStock = productStock[productId];
        if (unitsInStock !== null && unitsInStock !== undefined && quantity > unitsInStock) {
            showError(`Only ${unitsInStock} left in stock.`);
            return;
        }

        $.ajax({
            url: $form.attr("action"),
            method: "POST",
            data: $form.serialize(),
            dataType: "json"
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

            $("#add-to-cart-card").replaceWith(response.card_html);
            ActivateProductSearch();
        }).fail(function (xhr) {
            // jQuery treats any non-2xx status as a failure, so the server's
            // validation errors (400/403) arrive here, in xhr.responseJSON.
            const messages = xhr.responseJSON ? messagesFrom(xhr.responseJSON.errors) : [];
            showError(messages.join(" ") || "Something went wrong adding that to your cart -- try again.");
        });
    });
}

/**
 * Turns the cart card's #product-search text box into a jQuery UI
 * Autocomplete. Typing asks product_search_json (views/products.py) for matching
 * products; picking one copies its id into the hidden #id_product field
 * the form submits. Low-stock products get a badge. Called on page load
 * and again whenever AddOrderLineItem swaps in a fresh card.
 */
function ActivateProductSearch() {
    const $productSearch = $("#product-search");
    const $productId = $("#id_product");
    const $lowStockNote = $("#product-low-stock-note");

    function showLowStock(item) {
        if (item && item.low_stock) {
            $("#product-low-stock-count").text(`Only ${item.units_in_stock} left`);
            $lowStockNote.removeClass("d-none");
        } else {
            $lowStockNote.addClass("d-none");
        }
    }

    $productSearch.autocomplete({
        minLength: 0,
        // A function (not a plain URL) so the category filter can be sent along.
        source: function (request, response) {
            $.getJSON($productSearch.data("searchUrl"), {
                term: request.term,
                category: $productSearch.data("category")
            }).done(response).fail(function () {
                response([]);
            });
        },
        select: function (event, ui) {
            $productId.val(ui.item.id);
            showLowStock(ui.item);
        }
    });

    // With minLength 0, entering the empty box must ask for suggestions itself.
    $productSearch.on("focus click", function () {
        $productSearch.autocomplete("search", $productSearch.val());
    });

    // Typing after a pick clears it, so the old product's id isn't left behind.
    $productSearch.on("input", function () {
        $productId.val("");
        showLowStock(null);
    });

    // Builds each suggestion by hand so a "Low stock" badge can sit beside it.
    // .text() escapes the product name, so markup in a name can't inject anything.
    $productSearch.autocomplete("instance")._renderItem = function (ul, item) {
        const $row = $("<div>").text(item.label);
        if (item.low_stock) {
            $row.append(
                $("<span>")
                    .addClass("badge text-bg-warning ms-2")
                    .text(`Low stock (${item.units_in_stock})`)
            );
        }
        return $("<li>").append($row).appendTo(ul);
    };
}


/*
    UpdateCartQuantities -- lets the shopper change a cart line's quantity
    right in its row of order_build.html. Every row has a small <form>
    (_order_line_row.html) holding a Quantity box and an Update button;
    this intercepts that form's submit and POSTs it to order_update_line
    (djtraders/views/orders.py) via AJAX, then swaps in the refreshed row and the
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
    // strings (order_update_line's own access/state checks, views/orders.py) or
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
