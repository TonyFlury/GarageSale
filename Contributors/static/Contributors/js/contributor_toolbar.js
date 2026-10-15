(function () {
    function initialiseToolbar() {
        const form = document.querySelector('#toolbar .extra-toolbar-actions');
        const sheet = document.querySelector('#contributor-sheet');
        if (!sheet) return;

        document.querySelector('#spreadsheet-new-button')?.addEventListener('click', () => {
            const row = sheet.querySelector('tbody tr[data-is-new="true"]');
            const firstField = row?.querySelector(
                'input:not([type="hidden"]):not([type="checkbox"]):not([disabled]):not([readonly]), ' +
                'select:not([disabled]), textarea:not([disabled]):not([readonly])'
            );
            const scrollArea = sheet.closest('.spreadsheet-grid-scroll');
            if (!firstField || !scrollArea) return;

            scrollArea.scrollTop = scrollArea.scrollHeight;
            scrollArea.scrollLeft = 0;
            firstField.focus({preventScroll: true});
        });

        if (!form) return;

        function selectedRows() {
            return sheet.querySelectorAll('tbody tr:not([hidden]) input[name="selected_contributor"]:checked');
        }

        function updateActions() {
            const disabled = selectedRows().length === 0;
            form.querySelectorAll('[data-requires-selection]').forEach(button => {
                button.disabled = disabled;
            });
        }

        sheet.addEventListener('change', updateActions);
        document.querySelectorAll('[data-filter-field]').forEach(input => {
            input.addEventListener('input', updateActions);
        });
        window.addEventListener('pageshow', updateActions);
        form.addEventListener('submit', event => {
            const selected = selectedRows();
            if (event.submitter?.hasAttribute('data-requires-selection') && selected.length === 0) {
                event.preventDefault();
                updateActions();
                return;
            }
            form.querySelectorAll('input[name="selected_contributor"]').forEach(input => input.remove());
            selected.forEach(checkbox => {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'selected_contributor';
                input.value = checkbox.value;
                form.appendChild(input);
            });
        });
        updateActions();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiseToolbar);
    } else {
        initialiseToolbar();
    }
})();
