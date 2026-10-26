(function () {
    'use strict';
    function initialise() {
        const page = document.querySelector('#prize-winners');
        if (!page) return;
        let pending = 0;
        for (const row of page.querySelectorAll('.prize-winner')) {
            if (row.dataset.canEdit !== 'true') continue;
            const ticketForm = row.querySelector('.winning-ticket-form');
            const detailsForm = row.querySelector('.winner-details-form');
            const ticketInput = ticketForm.querySelector('input');
            const detailsFields = detailsForm.querySelector('fieldset');
            const ticketFields = ticketForm.querySelector('fieldset');
            const hint = row.querySelector('.winner-unlock-hint');
            const error = row.querySelector('.winner-error');
            const status = row.querySelector('.winner-status');
            let busy = false;
            let blocked = false;
            function refresh() {
                const recorded = Boolean(row.dataset.ticket) && ticketInput.value.trim() === row.dataset.ticket;
                const canEdit = row.dataset.canEdit === 'true';
                ticketFields.disabled = busy || blocked || !canEdit;
                detailsFields.disabled = busy || blocked || !recorded || !canEdit;
                hint.hidden = recorded;
            }
            ticketInput.addEventListener('input', refresh);
            async function save(action, values) {
                if (busy || blocked) return;
                busy = true;
                pending++;
                refresh();
                row.setAttribute('aria-busy', 'true');
                status.textContent = action === 'ticket' ? 'Recording ticket…' : 'Saving winner details…';
                error.textContent = '';
                document.querySelectorAll('.winner-event-form select, .winner-event-form button').forEach(item => { item.disabled = true; });
                try {
                    const response = await fetch(page.dataset.saveUrl, {
                        method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json',
                            'X-CSRFToken': document.querySelector('#winner-csrf [name="csrfmiddlewaretoken"]').value},
                        body: JSON.stringify({action, contribution_id: Number(row.dataset.contributionId), revision: row.dataset.revision, ...values}),
                    });
                    if (response.redirected) throw new Error('Your session may have expired. Sign in again and reload this page.');
                    let data;
                    try { data = await response.json(); }
                    catch (_) { blocked = true; throw new Error('The save could not be confirmed. Reload the page before trying again.'); }
                    if (!response.ok || !data.ok) {
                        if (response.status !== 400) blocked = true;
                        throw new Error(data.message || Object.values(data.errors || {}).flat().map(item => item.message).join(' ') || 'Unable to save the winner.');
                    }
                    const winner = data.winner;
                    row.dataset.revision = winner.revision;
                    row.dataset.ticket = winner.ticket_number;
                    row.dataset.hasDetails = String(winner.has_details);
                    row.dataset.canEdit = String(data.can_edit);
                    ticketInput.value = winner.ticket_number;
                    for (const field of ['name', 'phone', 'address']) detailsForm.querySelector(`[name$="-${field}"]`).value = winner[field];
                    row.querySelector('.record-ticket').textContent = 'Update ticket';
                    status.textContent = action === 'ticket' ? 'Ticket recorded. You can now enter the winner details.' : 'Winner details saved.';
                    busy = false;
                    refresh();
                    if (action === 'ticket' && data.can_edit) detailsForm.querySelector('[name$="-name"]').focus();
                    if (!data.can_edit) status.textContent = 'Ticket recorded. Permission to change winners is required to enter further details.';
                } catch (failure) {
                    if (failure instanceof TypeError) blocked = true;
                    status.textContent = 'Changes have not been confirmed.';
                    error.textContent = failure.message || 'Connection failed. Reload the page to check the saved ticket and winner.';
                    if (blocked) error.textContent += ' Reload this page before making further changes to this prize.';
                } finally {
                    busy = false;
                    pending--;
                    row.setAttribute('aria-busy', 'false');
                    refresh();
                    if (!pending) document.querySelectorAll('.winner-event-form select, .winner-event-form button').forEach(item => { item.disabled = false; });
                }
            }
            ticketForm.addEventListener('submit', event => {
                event.preventDefault();
                if (!ticketForm.reportValidity()) return;
                const changed = ticketInput.value.trim() !== row.dataset.ticket;
                const reset = changed && row.dataset.hasDetails === 'true';
                if (reset && !window.confirm('Changing the winning ticket will clear the saved winner name, phone and address. Continue?')) return;
                save('ticket', {ticket_number: ticketInput.value, reset_details: reset});
            });
            detailsForm.addEventListener('submit', event => {
                event.preventDefault();
                if (detailsFields.disabled || !detailsForm.reportValidity()) return;
                const values = Object.fromEntries(['name', 'phone', 'address'].map(field => [field, detailsForm.querySelector(`[name$="-${field}"]`).value]));
                save('details', values);
            });
            refresh();
        }
        window.addEventListener('beforeunload', event => { if (pending) { event.preventDefault(); event.returnValue = ''; } });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialise);
    else initialise();
})();
