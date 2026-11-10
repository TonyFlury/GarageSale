/** Connect the mobile settings launcher to the existing authorized settings forms. */
function initializeNotifierSettingsDialog() {
    const launcher = document.querySelector('.notifier-settings-launch');
    const dialog = document.querySelector('.notifier-settings-dialog');

    // Full settings pages and other host documents do not contain the review dialog.
    if (!launcher || !dialog) {
        return;
    }
    const body = dialog.querySelector('.notifier-dialog-body');
    let changed = false;
    let busy = false;

    /** Load or save the same server forms without replacing the notification review page. */
    async function requestSettings(url, options = {}) {
        busy = true;
        try {
            const response = await fetch(url, {...options, credentials: 'same-origin'});

            // Expired sessions and permission failures must not inject a login page into the settings editor.
            if (response.redirected || (!response.ok && response.status !== 400)) {
                throw new Error('Settings unavailable');
            }
            const documentFragment = new DOMParser().parseFromString(await response.text(), 'text/html');
            const content = documentFragment.querySelector('.notifier-settings-content');

            // Only the expected server fragment can become an interactive settings form.
            if (!content) {
                throw new Error('Settings unavailable');
            }
            body.replaceChildren(content);
            initializeNotifierSettings();

            // A successful save refreshes the review after closing, so current channel choices take effect.
            if (content.dataset.notifierSaved === 'true') {
                changed = true;
                const message = content.querySelector('.notifier-message');
                message.tabIndex = -1;
                message.focus();

                // A user can close the dialog while a save request finishes.
                if (!dialog.open) {
                    window.location.reload();
                }
            }
        } catch (error) {
            const message = document.createElement('p');
            message.className = 'notifier-dialog-error';
            message.setAttribute('role', 'alert');
            message.textContent = 'Settings could not be loaded. Use the full settings page below.';
            body.replaceChildren(message);
        } finally {
            busy = false;
        }
    }

    launcher.addEventListener('click', function openSettings(event) {
        /** Open the accessible native dialog while retaining a normal link as the fallback. */
        event.preventDefault();
        body.textContent = 'Loading settings…';
        dialog.showModal();
        const url = new URL(launcher.href);
        url.searchParams.set('display', 'dialog');
        requestSettings(url);
    });
    dialog.querySelector('.notifier-dialog-close').addEventListener('click', function closeSettings() {
        /** Close through the native dialog mechanism and return focus to the settings launcher. */
        dialog.close();
    });
    dialog.addEventListener('close', function refreshReview() {
        /** Retain the current review URL and filters when saved preferences require a refreshed list. */
        if (changed) {
            window.location.reload();
        }
    });
    body.addEventListener('submit', function saveSettings(event) {
        /** Submit one provider group with its existing CSRF token and server validation. */
        const form = event.target.closest('.notifier-provider-settings');

        // Unrelated content must not become a settings submission.
        if (!form) {
            return;
        }
        event.preventDefault();

        // An unfinished request must not receive a duplicate save.
        if (busy) {
            return;
        }
        requestSettings(form.action, {method: 'POST', body: new FormData(form)});
    });
}

// Deferred loading supplies the completed document before the dialog handlers are attached.
initializeNotifierSettingsDialog();
