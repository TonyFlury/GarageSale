'use strict';
{
    let button, dialog, form, cancel, clear;

    /** Allow one pending choice per named group while retaining independent filters. */
    function chooseGroupedFilter(event) {
        const selected = event.target;
        const group = selected.dataset.filterGroup;

        // Unchecking a choice and ungrouped choices must not affect other checkboxes.
        if (!selected.checked || !group) return;

        // Exclusive choices remain checkboxes so every group can also have no restriction.
        for (const option of form.querySelectorAll('input[name="selected_filters"][data-filter-group]')) {
            if (option !== selected && option.dataset.filterGroup === group) option.checked = false;
        }
    }

    /** Discard unsubmitted changes each time the filter chooser opens. */
    function openFilters() {
        form.reset();
        dialog.showModal();
    }

    /** Restore applied filters when the user cancels pending choices. */
    function cancelFilters() {
        form.reset();
        dialog.close();
    }

    /** Clear pending choices without applying them until the Filter button is used. */
    function clearFilters() {

        // Clearing is an editable draft so Cancel can still recover the applied filters.
        for (const option of form.querySelectorAll('input[name="selected_filters"]')) option.checked = false;
    }

    /** Treat Escape like Cancel without interfering with native dialog closing. */
    function resetFilters() {
        form.reset();
    }

    /** Attach filter controls only when the spreadsheet declares filter options. */
    function initialiseFilters() {
        button = document.querySelector('#spreadsheet-filter-button');
        dialog = document.querySelector('#spreadsheet-filter-dialog');
        form = document.querySelector('#spreadsheet-filter-form');
        cancel = document.querySelector('#spreadsheet-filter-cancel');
        clear = document.querySelector('#spreadsheet-filter-clear');

        // Derived spreadsheets can deliberately omit the entire filter interface.
        if (!button || !dialog || !form || !cancel) return;
        form.addEventListener('change', chooseGroupedFilter);
        button.addEventListener('click', openFilters);
        cancel.addEventListener('click', cancelFilters);
        clear?.addEventListener('click', clearFilters);
        dialog.addEventListener('cancel', resetFilters);
    }

    // Support both normal page parsing and scripts loaded after DOM readiness.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiseFilters);
    } else {
        initialiseFilters();
    }
}
