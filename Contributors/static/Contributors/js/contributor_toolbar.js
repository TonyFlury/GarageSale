'use strict';
{
    let form, sheet;

    /** Keep action recipients aligned with the rows currently visible to the user. */
    function selectedRows() {
        return sheet.querySelectorAll('tbody tr:not([hidden]) input[name="selected_contributor"]:checked');
    }

    /** Disable selection-dependent actions without affecting unrestricted actions. */
    function updateActions() {
        const disabled = selectedRows().length === 0;
        // Each action declares its own selection requirement in the rendered configuration.
        for (const button of form.querySelectorAll('[data-requires-selection]')) button.disabled = disabled;
    }

    /** Scroll within the grid and focus the first editable field of the entry row. */
    function focusNewRow() {
        const row = sheet.querySelector('tbody tr[data-is-new="true"]');
        const firstField = row?.querySelector(
            'input:not([type="hidden"]):not([type="checkbox"]):not([disabled]):not([readonly]), ' +
            'select:not([disabled]), textarea:not([disabled]):not([readonly])'
        );
        const scrollArea = sheet.closest('.spreadsheet-grid-scroll');
        // Custom spreadsheets may omit a new row or their own scroll container.
        if (!firstField || !scrollArea) return;
        scrollArea.scrollTop = scrollArea.scrollHeight;
        scrollArea.scrollLeft = 0;
        firstField.focus({preventScroll: true});
    }

    /** Snapshot visible selections into the standalone toolbar form at submission. */
    function submitAction(event) {
        const selected = selectedRows();
        // Recheck at submission because browser state restoration can stale button states.
        if (event.submitter?.hasAttribute('data-requires-selection') && selected.length === 0) {
            event.preventDefault();
            updateActions();
            return;
        }
        // A second submission must not retain hidden IDs from the previous selection.
        for (const input of form.querySelectorAll('input[name="selected_contributor"]')) input.remove();
        for (const checkbox of selected) {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'selected_contributor';
            input.value = checkbox.value;
            form.appendChild(input);
        }
    }

    /** Bind selection tracking after allowing spreadsheets with no custom actions. */
    function initialiseToolbar() {
        form = document.querySelector('#toolbar .extra-toolbar-actions');
        sheet = document.querySelector('#contributor-sheet');
        // The shared script can be included on pages without an editable grid.
        if (!sheet) return;
        document.querySelector('#spreadsheet-new-button')?.addEventListener('click', focusNewRow);
        // The New control also works when a subclass declares no toolbar actions.
        if (!form) return;
        sheet.addEventListener('change', updateActions);
        // Client-side search changes which selected rows are eligible for actions.
        for (const input of document.querySelectorAll('[data-filter-field]')) {
            input.addEventListener('input', updateActions);
        }
        window.addEventListener('pageshow', updateActions);
        form.addEventListener('submit', submitAction);
        updateActions();
    }

    // Support scripts included either before or after the grid has been parsed.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiseToolbar);
    } else {
        initialiseToolbar();
    }
}
