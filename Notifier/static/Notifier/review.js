/** Keep optional filters compact on mobile without concealing active selections or validation errors. */
function initializeNotifierReview() {
    const panel = document.querySelector('.notifier-filter-panel');

    // Other review documents do not contain the optional filter panel.
    if (!panel) {
        return;
    }
    const mobile = window.matchMedia('(max-width: 600px)');

    /** Apply the viewport default while preserving visibility for active filters and errors. */
    function updateFilterPanel() {
        panel.open = !mobile.matches || panel.dataset.notifierFilterRequired === 'true';
    }
    mobile.addEventListener('change', updateFilterPanel);
    updateFilterPanel();
}

// Deferred scripts initialize after parsing. Other loading modes wait until the document is ready.
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeNotifierReview);
} else {
    initializeNotifierReview();
}
