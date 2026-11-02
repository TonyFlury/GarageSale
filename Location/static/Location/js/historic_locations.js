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
    // The open attribute keeps the form available without JavaScript.
    dialog.removeAttribute('open');
    dialog.showModal();
    dialog.addEventListener('cancel', event => {
        event.preventDefault();
        window.location.assign(dialog.dataset.cancelUrl);
    });
});
