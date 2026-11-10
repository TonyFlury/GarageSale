/** Connect each generated channel form to its own enable control. */
function initializeNotifierSettings() {
    document.querySelectorAll('.notifier-provider-settings').forEach(function bindSeverityControls(form) {
        /** Apply severity selections to channels in this provider and summarize individual exceptions. */
        form.querySelectorAll('.notifier-severity-bulk').forEach(function bindSeverity(control) {
            /** Connect one severity checkbox to its matching channel checkboxes. */
            const severity = control.dataset.notifierSeverity;
            const channels = Array.from(form.querySelectorAll('.notifier-channel[data-notifier-severity="' + severity + '"] .notifier-channel-enabled'));

            /** Show all, none, or some matching channels without imposing another enablement rule. */
            function updateSummary() {
                const selected = channels.filter(function isSelected(channel) {
                    /** Identify a selected channel for the aggregate checkbox state. */
                    return channel.checked;
                }).length;
                control.checked = selected === channels.length;
                control.indeterminate = selected > 0 && selected < channels.length;
            }

            control.addEventListener('change', function applySeverity() {
                /** Set matching channels before later individual edits and preserve their option values. */
                const checked = control.checked;
                channels.forEach(function updateChannel(channel) {
                    /** Notify channel option controls and aggregate indicators about the selection change. */
                    channel.checked = checked;
                    channel.dispatchEvent(new Event('change', {bubbles: true}));
                });
                updateSummary();
            });
            channels.forEach(function watchChannel(channel) {
                /** Refresh the mixed indicator after an individual channel exception. */
                channel.addEventListener('change', updateSummary);
            });
            updateSummary();
        });
    });
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
