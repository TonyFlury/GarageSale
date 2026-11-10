/** Connect each generated channel form to its own enable control. */
function initializeNotifierSettings() {
    document.querySelectorAll('.notifier-channel').forEach(function bindChannel(channel) {
        /** Connect one channel's option controls without depending on provider or field names. */
        const enabled = channel.querySelector('.notifier-channel-enabled');
        const options = channel.querySelector('.notifier-channel-options');

        // Ignore unrelated channel markup that has no generated options interface.
        if (!enabled || !options) {
            return;
        }

        /** Update option availability without changing the user's displayed values. */
        function updateOptions() {
            options.disabled = !enabled.checked;
            options.querySelectorAll('input, select, textarea').forEach(function updateControl(control) {
                /** Match a generated field's availability to the channel enable control. */
                control.disabled = !enabled.checked;
            });
        }

        enabled.addEventListener('change', updateOptions);
        updateOptions();
    });
}

// Initialize immediately after deferred loading, or after parsing for other script loading modes.
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeNotifierSettings);
} else {
    initializeNotifierSettings();
}
