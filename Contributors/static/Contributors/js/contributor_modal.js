(function () {
    function initialiseModal() {
        const dialog = document.querySelector('#spreadsheet-modal-dialog');
        if (!dialog) return;
        dialog.querySelector('.spreadsheet-modal-close').addEventListener('click', () => dialog.close());
        dialog.showModal();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiseModal);
    } else {
        initialiseModal();
    }
})();
