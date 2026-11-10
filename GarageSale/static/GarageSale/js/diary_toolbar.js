/** HOST-003: Decorate package controls while preserving their handlers and form actions. */
(() => {
    "use strict";

    /** Add an icon and accessible hover text to its matching toolbar button. */
    function decorateButton(toolbar, source) {
        const button = toolbar.querySelector(source.dataset.diaryTarget);

        // Missing controls and repeated initialization must preserve the package toolbar.
        if (!button || button.querySelector(".diary-host-toolbar-icon")) {
            return;
        }

        const icon = source.cloneNode(true);
        icon.removeAttribute("data-diary-target");
        button.prepend(icon);
        button.title = source.alt;
        button.setAttribute("aria-label", source.alt);
    }

    /** Apply host icon declarations to each available Diary navigator toolbar. */
    function decorateToolbars() {
        const definitions = document.querySelector(".diary-host-toolbar-icons");

        // Other Diary pages have no navigator and need no toolbar decoration.
        if (!definitions) {
            return;
        }

        const icons = definitions.content.querySelectorAll(".diary-host-toolbar-icon");
        for (const toolbar of document.querySelectorAll(".diary .diary-graph-toolbar")) {
            for (const icon of icons) {
                decorateButton(toolbar, icon);
            }
        }
    }

    decorateToolbars();
})();
