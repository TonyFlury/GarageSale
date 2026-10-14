(function () {
    function initialiseToolbar() {
        const form = document.querySelector('#toolbar .extra-toolbar-actions');
        const sheet = document.querySelector('#contributor-sheet');
        if (!form || !sheet) return;

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
