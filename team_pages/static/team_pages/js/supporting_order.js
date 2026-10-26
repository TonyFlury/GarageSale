"use strict";
document.querySelectorAll(".supporting-picker").forEach((picker) => {
    const selected = picker.querySelector("[data-selected]");
    const results = picker.querySelector("[data-results]");
    const search = picker.querySelector("[data-search]");
    const status = picker.querySelector("[data-search-status]");
    const previous = picker.querySelector('[data-page="previous"]');
    const next = picker.querySelector('[data-page="next"]');
    const zones = [...picker.querySelectorAll("[data-drop-zone]")];
    let page = 1;
    let controller;
    let timer;
    let dragged = null;
    const marker = document.createElement("li");
    marker.className = "supporting-drop-marker";
    marker.setAttribute("aria-hidden", "true");

    function selectedRows() {
        return [...selected.children].filter((row) => row.hasAttribute("data-charity-id"));
    }

    function updateSelection() {
        const rows = selectedRows();
        picker.querySelector("[data-selected-count]").textContent = `(${rows.length})`;
        picker.querySelector("[data-empty-selected]").hidden = rows.length > 0;
        rows.forEach((row, index) => {
            row.draggable = true;
            const position = row.querySelector("[data-position]");
            position.value = index + 1;
            position.max = rows.length;
            row.querySelector('[data-move="up"]').disabled = index === 0;
            row.querySelector('[data-move="down"]').disabled = index === rows.length - 1;
        });
    }

    function announce(message) {
        picker.querySelector("[data-selection-status]").textContent = message;
    }

    function charityName(row) {
        return row.dataset.charityLabel;
    }

    function addCharity(charity, before = null) {
        if (selectedRows().some((row) => row.dataset.charityId === String(charity.id))) return;
        const row = document.createElement("li");
        row.dataset.charityId = charity.id;
        row.dataset.charityLabel = charity.name;
        const identity = document.createElement("input");
        identity.type = "hidden";
        identity.name = picker.dataset.fieldName;
        identity.value = charity.id;
        const name = document.createElement("span");
        name.dataset.charityName = "";
        name.textContent = charity.name;
        const handle = document.createElement("span");
        handle.className = "supporting-drag-handle";
        handle.draggable = true;
        handle.textContent = "⠿ ";
        handle.setAttribute("aria-hidden", "true");
        name.prepend(handle);
        const label = document.createElement("label");
        label.textContent = "Position ";
        const position = document.createElement("input");
        position.type = "number";
        position.min = 1;
        position.dataset.position = "";
        position.setAttribute("aria-label", `Position of ${charity.name}`);
        label.append(position);
        row.append(identity, name, label);
        for (const [action, text] of [["up", "Move up"], ["down", "Move down"], ["remove", "Remove"]]) {
            const button = document.createElement("button");
            button.type = "button";
            if (action === "remove") button.dataset.remove = "";
            else button.dataset.move = action;
            button.textContent = text;
            button.setAttribute("aria-label", `${text} ${charity.name}`);
            row.append(button);
        }
        selected.insertBefore(row, before);
        updateSelection();
        announce(`${charity.name} added.`);
        position.focus();
        loadResults(1);
    }

    function removeCharity(row) {
        const name = charityName(row);
        const focusTarget = row.nextElementSibling || row.previousElementSibling;
        row.remove();
        updateSelection();
        announce(`${name} removed. Save the event to keep this selection.`);
        (focusTarget?.querySelector("[data-position]") || search).focus();
        loadResults(1);
    }

    async function loadResults(requestedPage = 1) {
        clearTimeout(timer);
        controller?.abort();
        const request = new AbortController();
        controller = request;
        const url = new URL(picker.dataset.searchUrl, window.location.href);
        url.searchParams.set("q", search.value.trim());
        url.searchParams.set("page", requestedPage);
        for (const row of selectedRows()) url.searchParams.append("selected", row.dataset.charityId);
        previous.disabled = true;
        next.disabled = true;
        status.textContent = "Searching…";
        results.replaceChildren();
        try {
            const response = await fetch(url, {signal: request.signal, headers: {"Accept": "application/json"}});
            if (!response.ok) throw new Error("Search failed");
            const data = await response.json();
            if (request.signal.aborted) return;
            page = data.page;
            for (const charity of data.results) {
                const row = document.createElement("li");
                row.dataset.charityId = charity.id;
                row.dataset.charityLabel = charity.name;
                row.draggable = true;
                const name = document.createElement("span");
                name.textContent = charity.name;
                const handle = document.createElement("span");
                handle.className = "supporting-drag-handle";
                handle.draggable = true;
                handle.textContent = "⠿ ";
                handle.setAttribute("aria-hidden", "true");
                name.prepend(handle);
                const button = document.createElement("button");
                button.type = "button";
                button.textContent = "Add";
                button.setAttribute("aria-label", `Add ${charity.name}`);
                button.addEventListener("click", () => addCharity(charity));
                row.append(name, button);
                results.append(row);
            }
            status.textContent = data.count ? `${data.count} organisation${data.count === 1 ? "" : "s"} available.` : "No matching organisations available.";
            picker.querySelector("[data-page-label]").textContent = `Page ${data.page} of ${data.pages}`;
            previous.disabled = page <= 1;
            next.disabled = page >= data.pages;
        } catch (error) {
            if (request.signal.aborted) return;
            status.textContent = "Unable to load organisations. Change the search to try again.";
            picker.querySelector("[data-page-label]").textContent = "";
        }
    }

    selected.addEventListener("click", (event) => {
        const button = event.target.closest("button");
        if (!button) return;
        const row = button.closest("li");
        const name = charityName(row);
        if (button.hasAttribute("data-remove")) {
            removeCharity(row);
            return;
        }
        if (button.dataset.move === "up" && row.previousElementSibling) {
            selected.insertBefore(row, row.previousElementSibling);
        } else if (button.dataset.move === "down" && row.nextElementSibling) {
            selected.insertBefore(row.nextElementSibling, row);
        }
        updateSelection();
        announce(`${name} moved to position ${row.querySelector("[data-position]").value}.`);
        (button.disabled ? row.querySelector("[data-position]") : button).focus();
    });
    selected.addEventListener("change", (event) => {
        if (!event.target.matches("[data-position]")) return;
        const row = event.target.closest("li");
        const position = Math.max(1, Math.min(selectedRows().length, Math.trunc(Number(event.target.value)) || 1));
        const otherRows = selectedRows().filter((item) => item !== row);
        selected.insertBefore(row, otherRows[position - 1] || null);
        updateSelection();
        announce(`${charityName(row)} moved to position ${position}.`);
    });
    function clearDrag() {
        marker.remove();
        dragged?.classList.remove("is-dragging");
        dragged = null;
        zones.forEach((zone) => zone.classList.remove("is-drop-target"));
    }
    picker.addEventListener("dragstart", (event) => {
        if (event.target.closest("input, button, label")) { event.preventDefault(); return; }
        dragged = event.target.closest("li[data-charity-id]");
        if (!dragged) return;
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", dragged.dataset.charityId);
        dragged.classList.add("is-dragging");
    });
    picker.addEventListener("dragover", (event) => {
        if (!dragged) return;
        const zone = event.target.closest("[data-drop-zone]");
        if (!zone || !picker.contains(zone)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        zones.forEach((item) => item.classList.toggle("is-drop-target", item === zone));
        if (zone.dataset.dropZone !== "selected") { marker.remove(); return; }
        const before = selectedRows().filter((row) => row !== dragged).find((row) => {
            const bounds = row.getBoundingClientRect();
            return event.clientY < bounds.top + bounds.height / 2;
        });
        selected.insertBefore(marker, before || null);
        const bounds = selected.getBoundingClientRect();
        if (event.clientY < bounds.top + 24) selected.scrollTop -= 12;
        else if (event.clientY > bounds.bottom - 24) selected.scrollTop += 12;
    });
    picker.addEventListener("dragleave", (event) => {
        if (!picker.contains(event.relatedTarget)) {
            marker.remove();
            zones.forEach((zone) => zone.classList.remove("is-drop-target"));
        }
    });
    picker.addEventListener("drop", (event) => {
        if (!dragged) return;
        const zone = event.target.closest("[data-drop-zone]");
        if (!zone || !picker.contains(zone)) return;
        event.preventDefault();
        const row = dragged;
        const before = marker.parentElement === selected ? marker.nextElementSibling : null;
        clearDrag();
        if (zone.dataset.dropZone === "available") {
            if (row.parentElement === selected) removeCharity(row);
            return;
        }
        if (row.parentElement !== selected) {
            addCharity({id: row.dataset.charityId, name: charityName(row)}, before);
            return;
        }
        if (before !== row) selected.insertBefore(row, before);
        updateSelection();
        announce(`${charityName(row)} moved to position ${row.querySelector("[data-position]").value}. Save the event to keep this order.`);
        row.querySelector("[data-position]").focus();
    });
    picker.addEventListener("dragend", clearDrag);
    search.addEventListener("input", () => {
        controller?.abort();
        clearTimeout(timer);
        timer = setTimeout(() => loadResults(1), 200);
    });
    search.addEventListener("keydown", (event) => {
        if (event.key === "Enter") { event.preventDefault(); loadResults(1); }
    });
    selected.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && event.target.matches("[data-position]")) {
            event.preventDefault();
            event.target.dispatchEvent(new Event("change", {bubbles: true}));
        }
    });
    previous.addEventListener("click", () => loadResults(page - 1));
    next.addEventListener("click", () => loadResults(page + 1));
    updateSelection();
    loadResults();
});
