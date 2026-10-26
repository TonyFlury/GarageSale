(function () {
    function initialiseAttachments() {
        const container = document.querySelector('#communication-template-attachments');
        const empty = document.querySelector('#communication-template-attachment-empty');
        const add = document.querySelector('#communication-template-attachment-add');
        const total = document.querySelector('#id_attachments-TOTAL_FORMS');
        if (!container || !empty || !add || !total) return;

        function updateMode(row) {
            const upload = row.querySelector('[data-attachment-upload]').checked;
            const removed = row.querySelector('input[name$="-DELETE"]').checked;
            row.hidden = removed;
            const nameField = row.querySelector('[data-name-field]');
            const fileField = row.querySelector('[data-file-field]');
            nameField.hidden = upload;
            fileField.hidden = !upload;
            nameField.querySelectorAll('input').forEach(input => {
                input.disabled = upload || removed;
                input.required = !upload && !removed;
            });
            fileField.querySelectorAll('input').forEach(input => {
                input.disabled = !upload || removed;
                input.required = input.type === 'file' && upload && !removed && row.dataset.hasFile !== 'true';
            });
        }

        container.querySelectorAll('[data-template-attachment]').forEach(updateMode);
        container.addEventListener('change', event => {
            const row = event.target.closest('[data-template-attachment]');
            if (row) updateMode(row);
        });
        container.addEventListener('click', event => {
            const remove = event.target.closest('[data-remove-attachment]');
            if (!remove) return;
            const row = remove.closest('[data-template-attachment]');
            row.querySelector('input[name$="-DELETE"]').checked = true;
            updateMode(row);
        });
        add.addEventListener('click', () => {
            const index = Number(total.value);
            container.insertAdjacentHTML('beforeend', empty.innerHTML.replace(/__prefix__/g, String(index)));
            total.value = String(index + 1);
            const row = container.lastElementChild;
            updateMode(row);
            row.querySelector('[data-name-field] input').focus();
        });
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiseAttachments);
    } else {
        initialiseAttachments();
    }
})();
