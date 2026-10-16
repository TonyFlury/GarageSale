'use strict';
{
    let sheet, dataLabel, dialog, form, fields, error, edit, save, cancel, close, history, contact;
    let row = null;
    let initialHTML = '';
    let editing = false;
    let busy = false;

    /** Resolve controls only after the DOM has supplied the shared details dialog. */
    function findControls() {
        sheet = document.querySelector('#contributor-sheet');
        dataLabel = (sheet?.dataset.label || 'Contributor').toLowerCase();
        dialog = document.querySelector('#contributor-details-dialog');
        form = document.querySelector('#contributor-details-form');
        fields = document.querySelector('#contributor-details-fields');
        error = document.querySelector('#contributor-details-error');
        edit = document.querySelector('#contributor-details-edit');
        save = document.querySelector('#contributor-details-save');
        cancel = document.querySelector('#contributor-details-cancel');
        close = document.querySelector('#contributor-details-close');
        history = document.querySelector('#contributor-details-history');
        contact = document.querySelector('#details-add-contact-history');
    }

    /** Make loaded details read-only until the user explicitly requests editing. */
    function setMode(value) {
        editing = value;
        form.dataset.editing = String(editing);
        // Dynamically rendered fields must obey the same editing state as the toolbar.
        for (const input of fields.querySelectorAll('input:not([type="hidden"]):not([type="button"]), textarea, select')) {
            input.disabled = !editing || busy;
        }
        edit.hidden = editing || !initialHTML;
        save.hidden = !editing;
        cancel.hidden = !editing;
        // Edit-only guidance and social controls would clutter the read-only view.
        for (const help of fields.querySelectorAll('.details-help')) help.hidden = !editing;
        for (const button of fields.querySelectorAll('.social-edit-action')) button.hidden = !editing;
    }

    /** Prevent competing actions while loading or saving this contributor. */
    function setBusy(value) {
        busy = value;
        // Closing or switching mode mid-request could hide an uncertain save outcome.
        for (const button of [edit, save, cancel, close]) button.disabled = busy;
        contact.disabled = busy;
        // Contribution buttons arrive in server-rendered fragments after initial binding.
        for (const button of fields.querySelectorAll('.add-contribution')) button.disabled = busy;
    }

    /** Remove previous validation messages without discarding edited values. */
    function clearErrors() {
        error.textContent = '';
        // Every field can retain an earlier server-side validation message.
        for (const node of fields.querySelectorAll('[data-details-error]')) node.textContent = '';
    }

    /** Delegate social edits so replacement form fragments need no rebinding. */
    function editSocials(event) {
        // Read-only mode and active requests must not mutate the pending social data.
        if (!editing || busy) return;
        const remove = event.target.closest('.social-remove');
        // Removal is local until the complete details form is saved.
        if (remove) {
            remove.closest('.social-pair').remove();
            return;
        }
        const add = event.target.closest('.social-add');
        // Other controls within the details form have their own handlers.
        if (!add) return;
        const pair = document.createElement('div');
        pair.className = 'social-pair';
        pair.innerHTML = '<input class="social-key" type="text" aria-label="Social site">' +
            '<input class="social-value" type="text" aria-label="Social link">' +
            '<button type="button" class="social-remove social-edit-action" aria-label="Remove social entry">×</button>';
        add.closest('.socials-editor').querySelector('.socials-rows').appendChild(pair);
        pair.querySelector('.social-key').focus();
    }

    /** Preserve original JSON types while validating the editable social keys. */
    function syncSocials() {
        const data = fields.querySelector('.socials-data');
        // Some contributor forms deliberately omit the socials editor.
        if (!data) return true;
        const socials = Object.create(null);
        // Null-prototype storage allows names such as __proto__ without changing object behaviour.
        for (const pair of fields.querySelectorAll('.social-pair')) {
            const key = pair.querySelector('.social-key').value.trim();
            const value = pair.querySelector('.social-value').value;
            // A newly added blank pair is an unfilled control, not a social entry.
            if (!key && !value) continue;
            if (!key || Object.hasOwn(socials, key)) {
                error.textContent = 'Each social entry needs a unique site.';
                return false;
            }
            socials[key] = pair.dataset.originalText === value && pair.dataset.originalValue !== undefined
                ? JSON.parse(pair.dataset.originalValue) : value;
        }
        // Preserve null when no socials have ever been entered.
        data.value = Object.keys(socials).length || data.value !== 'null' ? JSON.stringify(socials) : 'null';
        return true;
    }

    /** Clear stale contributor data before a new details request becomes visible. */
    function prepareDetails(button) {
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
    }

    /** Fetch the specialised view's details and contribution-display preference. */
    async function loadDetails() {
        const showContributions = sheet.dataset.showContributions === 'false' ? '0' : '1';
        const label = encodeURIComponent(sheet.dataset.label || 'Contributor');
        const response = await fetch(`${form.action}?show_contributions=${showContributions}&data_label=${label}`, {
            headers: {'Accept': 'application/json'},
        });
        const data = await response.json();
        // An unsuccessful reply cannot replace the dialog with incomplete contributor data.
        if (!response.ok || !data.ok) throw new Error(`Unable to load ${dataLabel} details.`);
        initialHTML = data.html;
        fields.innerHTML = initialHTML;
        history.innerHTML = data.history_html;
        contact.dataset.contactHistoryUrl = data.contact_history_url;
        contact.dataset.contributorId = data.contributor_id;
        contact.hidden = false;
        clearErrors();
    }

    /** Open saved contributors only and leave failed loads in a recoverable dialog. */
    async function openDetails(event) {
        const button = event.target.closest('.contributor-details-button');
        // Unsaved rows have no details endpoint and busy requests must not change identity.
        if (!button || busy || button.closest('tr').dataset.isNew === 'true') return;
        prepareDetails(button);
        // Reset to read-only even when loading fails halfway through rendering.
        try {
            await loadDetails();
        } catch (failure) {
            error.textContent = `Unable to load ${dataLabel} details. Close and try again.`;
        } finally {
            setBusy(false);
            setMode(false);
        }
    }

    /** Focus the first field when editing is explicitly enabled. */
    function startEditing() {
        setMode(true);
        fields.querySelector('input:not([type="hidden"]), textarea, select')?.focus();
    }

    /** Discard pending details edits while retaining independently saved contributions. */
    function cancelEditing() {
        const contributionsHTML = fields.querySelector('#details-contributions')?.innerHTML;
        fields.innerHTML = initialHTML;
        // Contributions save independently and must survive cancelling unsaved details.
        if (contributionsHTML !== undefined) {
            fields.querySelector('#details-contributions').innerHTML = contributionsHTML;
        }
        clearErrors();
        setMode(false);
    }

    /** Guard asynchronous history refreshes against a changed or closed dialog. */
    function isCurrentHistory(historyRow, detailsURL) {
        return dialog.open && row === historyRow && form.action === detailsURL;
    }

    /** Refresh audit history without replacing pending details edits. */
    async function refreshHistory() {
        // A closed dialog will receive fresh history the next time it opens.
        if (!dialog.open) return;
        const historyRow = row;
        const detailsURL = form.action;
        // Late responses must never overwrite the history of a different contributor.
        try {
            const response = await fetch(`${detailsURL}?history=1`, {headers: {'Accept': 'application/json'}});
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error('Unable to refresh history.');
            if (isCurrentHistory(historyRow, detailsURL)) history.innerHTML = data.history_html;
        } catch (failure) {
            if (isCurrentHistory(historyRow, detailsURL)) {
                error.textContent = 'The change was saved, but history could not refresh. Reopen details to see it.';
            }
        }
    }

    /** Refresh only when the saved contact belongs to the displayed contributor. */
    function contactSaved(event) {
        // Another row's contact history must not affect this dialog's pending edits.
        if (event.detail.row !== row) return;
        return refreshHistory();
    }

    /** Place validation messages beside matching fields, with a general fallback. */
    function showValidationErrors(data) {
        // Unknown form fields still need a visible error rather than a silent failure.
        for (const [name, messages] of Object.entries(data.errors || {})) {
            const target = Array.from(fields.querySelectorAll('[data-details-error]'))
                .find(/** Match the server field name to its rendered error slot. */ node => node.dataset.detailsError === name) || error;
            target.textContent = messages.map(/** Extract each validation message. */ item => item.message).join(' ');
        }
        error.textContent = error.textContent || 'Please correct the highlighted fields.';
    }

    /** Save the form and notify the spreadsheet only after confirmed persistence. */
    async function saveDetails(body) {
        const response = await fetch(form.action, {
            method: 'POST', body,
            headers: {'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value},
        });
        const data = await response.json();
        // Keep edits available while the user corrects server-side field errors.
        if (!response.ok || !data.ok) {
            showValidationErrors(data);
            return;
        }
        sheet.dispatchEvent(new CustomEvent('contributor-details-saved', {
            detail: {row, contributor: data.contributor},
        }));
        dialog.close();
    }

    /** Serialize editing actions and restore controls after any delivery outcome. */
    async function submitDetails(event) {
        event.preventDefault();
        // Read-only and busy dialogs cannot issue competing save requests.
        if (!editing || busy) return;
        clearErrors();
        // Duplicate social keys would silently discard values when encoded as JSON.
        if (!syncSocials()) return;
        const body = new FormData(form);
        setBusy(true);
        // Network failures should preserve the form so edits remain available.
        try {
            await saveDetails(body);
        } catch (failure) {
            error.textContent = `Unable to save ${dataLabel} details. Please try again.`;
        } finally {
            setBusy(false);
        }
    }

    /** Close the details viewer from its Close button. */
    function closeDetails() {
        dialog.close();
    }

    /** Prevent Escape from hiding an unresolved request. */
    function cancelWhileBusy(event) {
        // A response must finish before the user can safely dismiss the dialog.
        if (busy) event.preventDefault();
    }

    /** Attach handlers once; delegated form controls survive fragment replacements. */
    function initialiseDetails() {
        findControls();
        fields.addEventListener('click', editSocials);
        sheet.addEventListener('click', openDetails);
        edit.addEventListener('click', startEditing);
        cancel.addEventListener('click', cancelEditing);
        close.addEventListener('click', closeDetails);
        dialog.addEventListener('cancel', cancelWhileBusy);
        sheet.addEventListener('contact-history-saved', contactSaved);
        dialog.addEventListener('contributions-changed', refreshHistory);
        form.addEventListener('submit', submitDetails);
    }

    // Support both deferred script loading and pages whose DOM is already ready.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiseDetails);
    } else {
        initialiseDetails();
    }
}
