(function () {
    function initialiseDetails() {
        const sheet = document.querySelector('#contributor-sheet');
        const dataLabel = (sheet?.dataset.label || 'Contributor').toLowerCase();
        const dialog = document.querySelector('#contributor-details-dialog');
        const form = document.querySelector('#contributor-details-form');
        const fields = document.querySelector('#contributor-details-fields');
        const error = document.querySelector('#contributor-details-error');
        const edit = document.querySelector('#contributor-details-edit');
        const save = document.querySelector('#contributor-details-save');
        const cancel = document.querySelector('#contributor-details-cancel');
        const close = document.querySelector('#contributor-details-close');
        const history = document.querySelector('#contributor-details-history');
        const contact = document.querySelector('#details-add-contact-history');
        let row = null;
        let initialHTML = '';
        let editing = false;
        let busy = false;

        function setMode(value) {
            editing = value;
            form.dataset.editing = String(editing);
            fields.querySelectorAll('input:not([type="hidden"]):not([type="button"]), textarea, select').forEach(input => {
                input.disabled = !editing || busy;
            });
            edit.hidden = editing || !initialHTML;
            save.hidden = !editing;
            cancel.hidden = !editing;
            fields.querySelectorAll('.details-help').forEach(help => { help.hidden = !editing; });
            fields.querySelectorAll('.social-edit-action').forEach(button => { button.hidden = !editing; });
        }

        function setBusy(value) {
            busy = value;
            for (const button of [edit, save, cancel, close]) button.disabled = busy;
            contact.disabled = busy;
            fields.querySelectorAll('.add-contribution').forEach(button => {button.disabled = busy;});
        }

        function clearErrors() {
            error.textContent = '';
            fields.querySelectorAll('[data-details-error]').forEach(node => { node.textContent = ''; });
        }

        fields.addEventListener('click', event => {
            if (!editing || busy) return;
            const remove = event.target.closest('.social-remove');
            if (remove) {
                remove.closest('.social-pair').remove();
                return;
            }
            const add = event.target.closest('.social-add');
            if (!add) return;
            const pair = document.createElement('div');
            pair.className = 'social-pair';
            pair.innerHTML = '<input class="social-key" type="text" aria-label="Social site">' +
                '<input class="social-value" type="text" aria-label="Social link">' +
                '<button type="button" class="social-remove social-edit-action" aria-label="Remove social entry">×</button>';
            add.closest('.socials-editor').querySelector('.socials-rows').appendChild(pair);
            pair.querySelector('.social-key').focus();
        });

        function syncSocials() {
            const data = fields.querySelector('.socials-data');
            if (!data) return true;
            const socials = Object.create(null);
            for (const pair of fields.querySelectorAll('.social-pair')) {
                const key = pair.querySelector('.social-key').value.trim();
                const value = pair.querySelector('.social-value').value;
                if (!key && !value) continue;
                if (!key || Object.hasOwn(socials, key)) {
                    error.textContent = 'Each social entry needs a unique site.';
                    return false;
                }
                socials[key] = pair.dataset.originalText === value && pair.dataset.originalValue !== undefined
                    ? JSON.parse(pair.dataset.originalValue) : value;
            }
            // Preserve null when no socials have been entered.
            data.value = Object.keys(socials).length || data.value !== 'null' ? JSON.stringify(socials) : 'null';
            return true;
        }

        sheet.addEventListener('click', async event => {
            const button = event.target.closest('.contributor-details-button');
            if (!button || busy || button.closest('tr').dataset.isNew === 'true') return;
            row = button.closest('tr');
            form.action = button.dataset.detailsUrl;
            initialHTML = '';
            fields.innerHTML = '';
            history.innerHTML = '';
            contact.hidden = true;
            clearErrors();
            setMode(false);
            setBusy(true);
            dialog.showModal();
            error.textContent = `Loading ${dataLabel} details…`;
            try {
                const showContributions = sheet.dataset.showContributions === 'false' ? '0' : '1';
                const label = encodeURIComponent(sheet.dataset.label || 'Contributor');
                const response = await fetch(`${form.action}?show_contributions=${showContributions}&data_label=${label}`, {
                    headers: {'Accept': 'application/json'},
                });
                const data = await response.json();
                if (!response.ok || !data.ok) throw new Error(`Unable to load ${dataLabel} details.`);
                initialHTML = data.html;
                fields.innerHTML = initialHTML;
                history.innerHTML = data.history_html;
                contact.dataset.contactHistoryUrl = data.contact_history_url;
                contact.dataset.contributorId = data.contributor_id;
                contact.hidden = false;
                clearErrors();
            } catch (failure) {
                error.textContent = `Unable to load ${dataLabel} details. Close and try again.`;
            } finally {
                setBusy(false);
                setMode(false);
            }
        });

        edit.addEventListener('click', () => {
            setMode(true);
            fields.querySelector('input:not([type="hidden"]), textarea, select')?.focus();
        });
        cancel.addEventListener('click', () => {
            const contributionsHTML = fields.querySelector('#details-contributions')?.innerHTML;
            fields.innerHTML = initialHTML;
            if (contributionsHTML !== undefined) {
                fields.querySelector('#details-contributions').innerHTML = contributionsHTML;
            }
            clearErrors();
            setMode(false);
        });
        close.addEventListener('click', () => dialog.close());
        dialog.addEventListener('cancel', event => {if (busy) event.preventDefault();});
        async function refreshHistory() {
            if (!dialog.open) return;
            const historyRow = row;
            const detailsURL = form.action;
            try {
                const response = await fetch(`${detailsURL}?history=1`, {headers: {'Accept': 'application/json'}});
                const data = await response.json();
                if (!response.ok || !data.ok) throw new Error('Unable to refresh history.');
                if (dialog.open && row === historyRow && form.action === detailsURL) {
                    history.innerHTML = data.history_html;
                }
            } catch (failure) {
                if (dialog.open && row === historyRow && form.action === detailsURL) {
                    error.textContent = 'The change was saved, but history could not refresh. Reopen details to see it.';
                }
            }
        }
        sheet.addEventListener('contact-history-saved', event => {
            if (event.detail.row !== row) return;
            return refreshHistory();
        });
        dialog.addEventListener('contributions-changed', refreshHistory);

        form.addEventListener('submit', async event => {
            event.preventDefault();
            if (!editing || busy) return;
            clearErrors();
            if (!syncSocials()) return;
            const body = new FormData(form);
            setBusy(true);
            try {
                const response = await fetch(form.action, {
                    method: 'POST', body,
                    headers: {'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value},
                });
                const data = await response.json();
                if (!response.ok || !data.ok) {
                    for (const [name, messages] of Object.entries(data.errors || {})) {
                        const target = Array.from(fields.querySelectorAll('[data-details-error]'))
                            .find(node => node.dataset.detailsError === name) || error;
                        target.textContent = messages.map(item => item.message).join(' ');
                    }
                    error.textContent = error.textContent || 'Please correct the highlighted fields.';
                    return;
                }
                sheet.dispatchEvent(new CustomEvent('contributor-details-saved', {
                    detail: {row, contributor: data.contributor},
                }));
                dialog.close();
            } catch (failure) {
                error.textContent = `Unable to save ${dataLabel} details. Please try again.`;
            } finally {
                setBusy(false);
            }
        });
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiseDetails);
    } else {
        initialiseDetails();
    }
})();
