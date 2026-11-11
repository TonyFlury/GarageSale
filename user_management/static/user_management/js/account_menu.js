/** Attach account menu disclosure controls without assuming an indicator provider exists. */
function initializeAccountMenus() {
    document.querySelectorAll('.account-indicator').forEach(function bindAccountMenu(container) {
        /** Connect one account button to its existing pull-down menu. */
        const button = container.querySelector('.account-menu-toggle');

        // Repeated host initialization must not attach duplicate click handlers.
        if (!button || button.dataset.menuReady === 'true') {
            return;
        }
        button.dataset.menuReady = 'true';

        /** Keep the visible disclosure state and accessible expanded state consistent. */
        function setOpen(open) {
            container.classList.toggle('account-menu-open', open);
            button.setAttribute('aria-expanded', String(open));
        }
        button.addEventListener('click', function toggleMenu() {
            /** Toggle the menu for clicks on the icon or its noninteractive overlay. */
            setOpen(button.getAttribute('aria-expanded') !== 'true');
        });
        document.addEventListener('click', function closeOutside(event) {
            /** Dismiss the pull-down when the user selects another part of the page. */
            if (!container.contains(event.target)) {
                setOpen(false);
            }
        });
        container.addEventListener('keydown', function closeOnEscape(event) {
            /** Dismiss the menu through the keyboard and retain focus on its button. */
            if (event.key === 'Escape') {
                setOpen(false);
                button.focus();
            }
        });
    });
}

// Deferred loading supplies the completed account controls before handlers attach.
initializeAccountMenus();
