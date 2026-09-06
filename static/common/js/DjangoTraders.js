/*
    Project-wide custom JavaScript.

    Lives in static/common/js/ (project-root static/ folder, registered
    via STATICFILES_DIRS in settings.py), parallel to templates/common/
    holding the project-wide base.html. The js/ subfolder (and css/,
    next to it, for DjangoTraders.css) keeps scripts and stylesheets
    separated by kind rather than mixed together in static/common/
    directly. Loaded from base.html after jQuery and DataTables, so
    anything here can rely on both already being present.

  Each Make*DataTable(tableId) function below applies DataTables to one
  named table by id -- pageLength/lengthMenu raise DataTables' own
  default of 10 rows per page and the choices in its "Show N entries"
  dropdown. Kept as one function per table, repeating the same settings,
  rather than a shared helper -- simple beats DRY here: a table with its
  own quirk (an unsortable icon column, a custom sort order) just sets
  that option in its own function instead of a generic helper needing
  extra parameters to handle every table's special case.

  1. MakeCustomersDataTable (customer_list.html) also disables sorting
    on its Actions column (an icon, not sortable data), and swaps the
    entries-per-page dropdown and "Showing X of Y" positions.
  2. MakeProductsDataTable (product_list.html) also disables sorting on
    its Actions column.
  3. MakeOrdersDataTable (customer_detail.html) defaults to sorting by
    Order Date, descending, instead of DataTables' own default (first
    column, ascending).
  4. MakeOrderDetailsDataTable (order_detail.html) uses the plain
    defaults -- no special options needed.
*/

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
