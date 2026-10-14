(function () {
    function initialiseContributions() {
        const details = document.querySelector('#contributor-details-dialog');
        const dialog = document.querySelector('#contribution-dialog');
        const form = document.querySelector('#contribution-form');
        const gift = document.querySelector('#contribution-gift');
        const cash = document.querySelector('#contribution-cash');
        const eventInput = document.querySelector('#contribution-event');
        const error = document.querySelector('#contribution-error');
        const status = document.querySelector('#contribution-status');
        const cancel = document.querySelector('#contribution-cancel');
        let saving = false;
        let contributionList;
        let sponsorList = false;

        async function deleteContribution(event) {
            const button = event.target.closest('.delete-contribution');
            if (!button || saving) return;
            const sponsor = button.closest('[data-sponsor-contributions]');
            const list = sponsor || details.querySelector('#details-contributions');
            const message = list.querySelector('.contribution-delete-error');
            saving = true;
            button.disabled = true;
            message.textContent = '';
            let deleted = false;
            try {
                const response = await fetch(button.dataset.deleteUrl, {
                    method: 'POST',
                    headers: {'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value},
                    body: new URLSearchParams({event_id: button.dataset.eventId}),
                });
                const data = await response.json();
                if (!response.ok || !data.ok) {
                    message.textContent = data.message || `Unable to delete contribution (HTTP ${response.status}). Reopen the popup.`;
                    return;
                }
                deleted = true;
                list.innerHTML = sponsor ? data.sponsor_contributions_html : data.contributions_html;
                if (!sponsor) details.dispatchEvent(new CustomEvent('contributions-changed'));
            } catch (failure) {
                console.error('Contribution deletion failed', failure);
                message.textContent = deleted ? 'Contribution deleted. Reopen the popup to refresh the list.' :
                    'Deletion could not be verified. Reopen the popup before trying again.';
            } finally {
                saving = false;
                button.disabled = false;
            }
        }
        details.addEventListener('click', deleteContribution);
        document.querySelector('#spreadsheet-modal-dialog')?.addEventListener('click', deleteContribution);

        function updateAmountInput() {
            gift.inputMode = cash.checked ? 'decimal' : 'text';
            gift.placeholder = cash.checked ? '£0.00' : 'Describe the contribution';
            gift.rows = cash.checked ? 1 : 3;
        }
        cash.addEventListener('change', updateAmountInput);

        function openContribution(event) {
            const button = event.target.closest('.add-contribution');
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
        details.addEventListener('click', openContribution);
        document.querySelector('#spreadsheet-modal-dialog')?.addEventListener('click', openContribution);
        cancel.addEventListener('click', () => dialog.close());
        dialog.addEventListener('cancel', event => {if (saving) event.preventDefault();});
        form.addEventListener('submit', async event => {
            event.preventDefault();
            if (saving) return;
            const addAnother = event.submitter?.value === 'Save and Add another';
            const body = new FormData(form);
            saving = true;
            form.querySelectorAll('input[type="submit"], input[type="button"]').forEach(button => {button.disabled = true;});
            error.textContent = '';
            status.textContent = '';
            let saved = false;
            let stage = 'preparing request';
            try {
                const csrfToken = form.querySelector('[name="csrfmiddlewaretoken"]');
                if (!csrfToken) throw new Error('Contribution form has no CSRF token');
                stage = 'sending request';
                const response = await fetch(form.getAttribute('action'), {
                    method: 'POST', body,
                    headers: {'X-CSRFToken': csrfToken.value},
                });
                if (response.redirected || response.status === 401) {
                    error.textContent = 'Your session may have expired. Sign in again before saving this contribution.';
                    return;
                }
                let data;
                try {
                    data = await response.json();
                } catch (failure) {
                    console.error('Contribution response was not JSON', {status: response.status, failure});
                    const reasons = {
                        403: 'The server rejected this request (403). Reload the page before trying again.',
                        404: 'The contribution endpoint or sponsor could not be found (404). Reload the page.',
                    };
                    error.textContent = reasons[response.status] ||
                        `The server returned an unexpected response (HTTP ${response.status}). Check the sponsor’s contribution list before retrying; the save could not be verified.`;
                    return;
                }
                if (!response.ok || !data.ok) {
                    error.textContent = Object.values(data.errors || {}).flat()
                        .map(item => item.message).join(' ') || 'Unable to save contribution.';
                    return;
                }
                saved = true;
                stage = 'refreshing contribution list';
                const updatedHTML = sponsorList ? data.sponsor_contributions_html : data.contributions_html;
                if (!contributionList || typeof updatedHTML !== 'string') {
                    throw new Error('Contribution list or updated HTML is missing');
                }
                contributionList.innerHTML = updatedHTML;
                if (!sponsorList) details.dispatchEvent(new CustomEvent('contributions-changed'));
                if (addAnother) {
                    gift.value = '';
                    cash.checked = false;
                    updateAmountInput();
                    status.textContent = 'Contribution saved. Add another contribution.';
                    gift.focus();
                } else {
                    dialog.close();
                }
            } catch (failure) {
                console.error(`Contribution failed while ${stage}`, failure);
                error.textContent = saved ?
                    'The contribution was saved, but its list could not be refreshed. Reopen the list before adding it again.' :
                    stage === 'preparing request' ?
                    'The browser could not prepare the contribution request. Nothing was sent. Reload the page before trying again.' :
                    'Could not connect to the server. Check your connection and reopen the contribution list before retrying; the save could not be verified.';
            } finally {
                saving = false;
                form.querySelectorAll('input[type="submit"], input[type="button"]').forEach(button => {button.disabled = false;});
            }
        });
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiseContributions);
    } else {
        initialiseContributions();
    }
})();
