'use strict';
{
    let details, dialog, form, gift, cash, amount, amountHelp, eventInput, error, status, cancel;
    let saving = false;
    let contributionList;
    let sponsorList = false;

    /** Cache the shared popup controls after the DOM is available. */
    function findControls() {
        details = document.querySelector('#contributor-details-dialog');
        dialog = document.querySelector('#contribution-dialog');
        form = document.querySelector('#contribution-form');
        gift = document.querySelector('#contribution-gift');
        cash = document.querySelector('#contribution-cash');
        amount = document.querySelector('#contribution-amount');
        amountHelp = document.querySelector('#contribution-amount-help');
        eventInput = document.querySelector('#contribution-event');
        error = document.querySelector('#contribution-error');
        status = document.querySelector('#contribution-status');
        cancel = document.querySelector('#contribution-cancel');
    }

    /** Keep duplicate submissions and popup dismissal disabled during a save. */
    function setSaving(value) {
        saving = value;
        // Both save actions and Cancel must wait for a definitive server response.
        for (const button of form.querySelectorAll('input[type="submit"], input[type="button"]')) {
            button.disabled = value;
        }
    }

    /** Delete one record while preserving uncertainty about interrupted responses. */
    async function deleteContribution(event) {
        const button = event.target.closest('.delete-contribution');
        // Delegated clicks also include unrelated controls and repeated clicks.
        if (!button || saving) return;
        const sponsor = button.closest('[data-sponsor-contributions]');
        const list = sponsor || details.querySelector('#details-contributions');
        const message = list.querySelector('.contribution-delete-error');
        saving = true;
        button.disabled = true;
        message.textContent = '';
        // Always unlock after failure without assuming that the deletion was rolled back.
        try {
            await requestDeletion(button, list, sponsor, message);
        } catch (failure) {
            console.error('Contribution deletion failed', failure);
            message.textContent = 'Deletion could not be verified. Reopen the popup before trying again.';
        } finally {
            saving = false;
            button.disabled = false;
        }
    }

    /** Request deletion and refresh only the list containing that contribution. */
    async function requestDeletion(button, list, sponsor, message) {
        const response = await fetch(button.dataset.deleteUrl, {
            method: 'POST', headers: {'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value},
            body: new URLSearchParams({event_id: button.dataset.eventId}),
        });
        const data = await response.json();
        // Failed event checks must leave the displayed list intact for inspection.
        if (!response.ok || !data.ok) {
            message.textContent = data.message || `Unable to delete contribution (HTTP ${response.status}). Reopen the popup.`;
            return;
        }
        // A committed deletion must not be retried if only browser rendering fails.
        try {
            list.innerHTML = sponsor ? data.sponsor_contributions_html : data.contributions_html;
            if (!sponsor) details.dispatchEvent(new CustomEvent('contributions-changed'));
        } catch (failure) {
            console.error('Contribution deletion refresh failed', failure);
            message.textContent = 'Contribution deleted. Reopen the popup to refresh the list.';
        }
    }

    /** Match browser requirements to cash amounts and optional gift estimates. */
    function updateAmountInput() {
        amount.required = cash.checked;
        amount.min = cash.checked ? '0.01' : '0';
        amountHelp.textContent = cash.checked ? 'Cash amount is required.' : 'Optional estimated value for a non-cash gift.';
        gift.required = !cash.checked;
        gift.placeholder = cash.checked ? 'Optional description' : 'Describe the contribution';
    }

    /** Reuse the editor for either a details list or a sponsor confirmation list. */
    function openContribution(event) {
        const button = event.target.closest('.add-contribution');
        // Delegation must ignore unrelated clicks and protect an in-flight save.
        if (!button || saving) return;
        const sponsorContributions = button.closest('[data-sponsor-contributions]');
        sponsorList = Boolean(sponsorContributions);
        contributionList = sponsorContributions || details.querySelector('#details-contributions');
        form.reset();
        updateAmountInput();
        // Buttons named "action" shadow the form.action property.
        form.setAttribute('action', button.dataset.contributionUrl);
        eventInput.value = button.dataset.eventId;
        document.querySelector('#contribution-contributor').textContent = button.dataset.contributorName;
        error.textContent = '';
        status.textContent = '';
        dialog.showModal();
        gift.focus();
    }

    /** Explain non-JSON replies without implying that an uncertain save failed. */
    async function readSaveResponse(response) {
        // Expired sessions often return a login page rather than the JSON API response.
        if (response.redirected || response.status === 401) {
            error.textContent = 'Your session may have expired. Sign in again before saving this contribution.';
            return null;
        }
        // Proxy and permission errors may also return HTML instead of JSON.
        try {
            return await response.json();
        } catch (failure) {
            console.error('Contribution response was not JSON', {status: response.status, failure});
            const reasons = {
                403: 'The server rejected this request (403). Reload the page before trying again.',
                404: 'The contribution endpoint or sponsor could not be found (404). Reload the page.',
            };
            error.textContent = reasons[response.status] ||
                `The server returned an unexpected response (HTTP ${response.status}). Check the sponsor’s contribution list before retrying; the save could not be verified.`;
            return null;
        }
    }

    /** Refresh the originating list and notify history only when details is open. */
    function refreshContributionList(data) {
        const updatedHTML = sponsorList ? data.sponsor_contributions_html : data.contributions_html;
        // A missing fragment is a browser refresh failure after a successful save.
        if (!contributionList || typeof updatedHTML !== 'string') {
            throw new Error('Contribution list or updated HTML is missing');
        }
        contributionList.innerHTML = updatedHTML;
        // Sponsor confirmation lists do not own the details history panel.
        if (!sponsorList) details.dispatchEvent(new CustomEvent('contributions-changed'));
    }

    /** Preserve contributor and event identity while preparing another gift. */
    function finishSave(addAnother) {
        // Save-and-add-another deliberately keeps this contributor's popup open.
        if (addAnother) {
            gift.value = '';
            amount.value = '';
            cash.checked = false;
            updateAmountInput();
            status.textContent = 'Contribution saved. Add another contribution.';
            gift.focus();
        } else {
            dialog.close();
        }
    }

    /** Distinguish unsent requests from uncertain delivery and committed saves. */
    function reportSaveFailure(failure, progress) {
        console.error(`Contribution failed while ${progress.stage}`, failure);
        error.textContent = progress.saved ?
            'The contribution was saved, but its list could not be refreshed. Reopen the list before adding it again.' :
            progress.stage === 'preparing request' ?
            'The browser could not prepare the contribution request. Nothing was sent. Reload the page before trying again.' :
            'Could not connect to the server. Check your connection and reopen the contribution list before retrying; the save could not be verified.';
    }

    /** Submit once and retain enough progress information to prevent accidental duplicates. */
    async function submitContribution(event) {
        event.preventDefault();
        // Repeated clicks must not create duplicate gifts.
        if (saving) return;
        const body = new FormData(form);
        setSaving(true);
        error.textContent = '';
        status.textContent = '';
        const progress = {saved: false, stage: 'preparing request'};
        // Unlock controls for every outcome, including browser-side refresh failures.
        try {
            await saveContribution(body, event.submitter?.value === 'Save and Add another', progress);
        } catch (failure) {
            reportSaveFailure(failure, progress);
        } finally {
            setSaving(false);
        }
    }

    /** Validate the reply before replacing the originating list or closing the popup. */
    async function saveContribution(body, addAnother, progress) {
        const csrfToken = form.querySelector('[name="csrfmiddlewaretoken"]');
        // Missing CSRF protection means nothing should be sent to the server.
        if (!csrfToken) throw new Error('Contribution form has no CSRF token');
        progress.stage = 'sending request';
        const response = await fetch(form.getAttribute('action'), {
            method: 'POST', body, headers: {'X-CSRFToken': csrfToken.value},
        });
        const data = await readSaveResponse(response);
        // Session or non-JSON errors already have an actionable message.
        if (!data) return;
        // Field errors must preserve the user's entered values for correction.
        if (!response.ok || !data.ok) {
            error.textContent = Object.values(data.errors || {}).flat()
                .map(/** Extract server-provided field messages. */ item => item.message).join(' ') || 'Unable to save contribution.';
            return;
        }
        progress.saved = true;
        progress.stage = 'refreshing contribution list';
        refreshContributionList(data);
        finishSave(addAnother);
    }

    /** Keep Escape from closing the editor while the result is unknown. */
    function cancelWhileSaving(event) {
        // Closing mid-request would hide whether the contribution was committed.
        if (saving) event.preventDefault();
    }

    /** Close the idle contribution editor from its Cancel button. */
    function closeContribution() {
        dialog.close();
    }

    /** Bind delegated controls so refreshed list fragments remain interactive. */
    function initialiseContributions() {
        findControls();
        details.addEventListener('click', deleteContribution);
        document.querySelector('#spreadsheet-modal-dialog')?.addEventListener('click', deleteContribution);
        cash.addEventListener('change', updateAmountInput);
        details.addEventListener('click', openContribution);
        document.querySelector('#spreadsheet-modal-dialog')?.addEventListener('click', openContribution);
        cancel.addEventListener('click', closeContribution);
        dialog.addEventListener('cancel', cancelWhileSaving);
        form.addEventListener('submit', submitContribution);
    }

    // Scripts may be loaded before parsing finishes or after a dynamic page render.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiseContributions);
    } else {
        initialiseContributions();
    }
}
