(function () {
    function initialiseFilters() {
        const button = document.querySelector('#spreadsheet-filter-button');
        const dialog = document.querySelector('#spreadsheet-filter-dialog');
        const form = document.querySelector('#spreadsheet-filter-form');
        const cancel = document.querySelector('#spreadsheet-filter-cancel');
        const clear = document.querySelector('#spreadsheet-filter-clear');
        if (!button || !dialog || !form || !cancel) return;

        form.addEventListener('change', event => {
            const selected = event.target;
            const group = selected.dataset.filterGroup;
            if (!selected.checked || !group) return;
            form.querySelectorAll('input[name="selected_filters"][data-filter-group]').forEach(option => {
                if (option !== selected && option.dataset.filterGroup === group) option.checked = false;
            });
        });

        button.addEventListener('click', () => {
            form.reset();
            dialog.showModal();
        });
        cancel.addEventListener('click', () => {
            form.reset();
            dialog.close();
        });
        // Clear the pending selections; the Filter button applies the change.
        clear?.addEventListener('click', () => {
            form.querySelectorAll('input[name="selected_filters"]').forEach(option => {
                option.checked = false;
            });
        });
        dialog.addEventListener('cancel', () => form.reset());
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiseFilters);
    } else {
        initialiseFilters();
    }
})();
