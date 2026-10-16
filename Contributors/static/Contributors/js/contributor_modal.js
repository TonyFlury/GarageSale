'use strict';
{
    let dialog;

    /** Close the server-rendered action dialog without modifying spreadsheet state. */
    function closeModal() {
        dialog.close();
    }

    /** Open an action result only when the server supplied a modal fragment. */
    function initialiseModal() {
        dialog = document.querySelector('#spreadsheet-modal-dialog');
        // Ordinary spreadsheet requests have no action chooser or result to display.
        if (!dialog) return;
        dialog.querySelector('.spreadsheet-modal-close').addEventListener('click', closeModal);
        dialog.showModal();
    }

    // The fragment must exist before the dialog is opened.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiseModal);
    } else {
        initialiseModal();
    }
}
