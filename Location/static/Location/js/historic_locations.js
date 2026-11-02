document.addEventListener('DOMContentLoaded', () => {
    const dialog = document.getElementById('historic-locations');
    if (!dialog) return;
    const checkboxes = [...dialog.querySelectorAll('input[name="locations"]')];
    const updateSelection = () => {
        const count = checkboxes.filter(input => input.checked).length;
        document.getElementById('historic-count').textContent = `${count} location${count === 1 ? '' : 's'} selected`;
        dialog.querySelectorAll('[data-needs-selection]').forEach(button => { button.disabled = count === 0; });
    };
    checkboxes.forEach(input => input.addEventListener('change', updateSelection));
    updateSelection();
    const manual = dialog.dataset.manual === 'true';
    const trigger = document.querySelector('[data-historic-open]');
    if (trigger) trigger.addEventListener('click', event => {
        event.preventDefault();
        checkboxes.forEach(input => { input.checked = false; });
        updateSelection();
        dialog.showModal();
    });
    // The open attribute keeps the form available without JavaScript.
    dialog.removeAttribute('open');
    if (!manual) dialog.showModal();
    if (manual) dialog.querySelector('[value="cancel"]').addEventListener('click', event => {
        event.preventDefault();
        dialog.close();
    });
    dialog.addEventListener('cancel', event => {
        if (manual) return;
        event.preventDefault();
        window.location.assign(dialog.dataset.cancelUrl);
    });
});
