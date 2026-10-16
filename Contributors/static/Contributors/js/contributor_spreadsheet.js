

'use strict';
{
    const newRowHTML = `
            <td class="select"></td>
            <td class="row-status">
                    <span class="status" > </span>
                    <span class="undo" > </span>
                </td>

            <td>
                <input name="contributor_name" value="" maxlength="120" required>
                <span class="field-error" data-error-for="contributor_name"></span>
            </td>

            <td>
                <input name="contact_name" value="" maxlength="120">
                <span class="field-error" data-error-for="contact_name"></span>
            </td>

            <td>
                <input name="phone" value="" maxlength="12">
                <span class="field-error" data-error-for="phone"></span>
            </td>

            <td>
                <input name="email" type="email" value="" maxlength="254">
                <span class="field-error" data-error-for="email"></span>
            </td>

            <td><input class="last-contact-date" type="text" readonly aria-label="Last contact date" data-date="" value=""></td>

            <td>
                <div class="actions">
                </div>
            </td>
        `;

    const editableFields = [
        "contributor_name",
        "contact_name",
        "phone",
        "email",
    ];

    function getCookie(name) {
        const cookies = document.cookie ? document.cookie.split(";") : [];

        for (const cookie of cookies) {
            const trimmed = cookie.trim();

            if (trimmed.startsWith(`${name}=`)) {
                return decodeURIComponent(trimmed.substring(name.length + 1));
            }
        }

        return "";
    }

    function getSheet() {
        return document.querySelector("#contributor-sheet");
    }

    function getRowInputs(row) {
        return editableFields.map((field) => row.querySelector(`[name="${field}"]`));
    }

    function setStatus(row, text, className) {
        const status = row.querySelector(".row-status");

        status.textContent = text;
        status.className = `row-status ${className}`;
    }

    function clearErrors(row) {
        row.querySelectorAll(".field-error").forEach((element) => {
            element.textContent = "";
        });

        row.classList.remove("invalid");
    }

    function setErrors(row, errors) {
        clearErrors(row);

        Object.entries(errors).forEach(([field, message]) => {
            const errorElement = row.querySelector(`[data-error-for="${field}"]`) ||
                row.querySelector('[data-error-for="contributor_name"]');

            if (errorElement) {
                errorElement.textContent = message;
            }
        });

        row.classList.add("invalid");
     
    }

    /** Validate inline fields without losing edits that need correction. */
    function validateRow(row) {
        const errors = rowValidationErrors(row);

        // Keep invalid input available so the user can correct it in place.
        if (Object.keys(errors).length > 0) {
            setErrors(row, errors);
            return false;
        }
        clearErrors(row);
        return true;
    }

    /** Apply the same required-name and length rules as the row API. */
    function rowValidationErrors(row) {
        const errors = {};
        const type = row.querySelector('[name="contributor_type"]');
        const name = row.querySelector('[name="contributor_name"]').value.trim();
        const contact = row.querySelector('[name="contact_name"]').value.trim();
        const phone = row.querySelector('[name="phone"]').value.trim();
        const email = row.querySelector('[name="email"]').value.trim();

        // Existing rows retain their stored type and do not need a type input.
        if (row.dataset.isNew === "true" && !type?.value.trim()) {
            errors.contributor_type = `${getSheet()?.dataset.label || "Contributor"} type is required.`;
        }

        // Reject whitespace identities and values longer than the rendered input limits.
        if (!name) errors.contributor_name = "Company name is required.";
        if (contact.length > 120) errors.contact_name = "Contact name must be 120 characters or fewer.";
        if (phone.length > 12) errors.phone = "Phone must be 12 characters or fewer.";

        // Email is optional but must resemble an address when present.
        if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = "Enter a valid email address.";
        return errors;
    }

    function toggleRowLock(row) {
        if (row.dataset.canEdit === "false") return;

        if (row.classList.contains("unlocked") && !row.classList.contains('dirty')) {
            lockRow(row);
            return;
        }

        if (row.classList.contains("unlocked") && row.classList.contains('dirty')) {
            return saveRow(row);
        }

        row.classList.remove("locked");
        row.classList.add("unlocked");

        getRowInputs(row).forEach((input) => {
            input.disabled = false;
        });

    }

    function lockRow(row, options={}) {
        row.classList.remove("unlocked", "dirty", "invalid", "new-row");
        row.classList.add("locked");

        delete row.dataset.isNew;

        getRowInputs(row).forEach((input) => {
            input.disabled = true;
            input.dataset.originalValue = input.value;
        });

  

        clearErrors(row);
       
    }

    function markDirty(row) {
        if (row.classList.contains("locked")) {
            return;
        }

        row.classList.add("dirty");


    }

    function getPayload(row) {
        const payload = {};

        editableFields.forEach((field) => {
            payload[field] = row.querySelector(`[name="${field}"]`).value;
        });

        // Only new rows supply a contributor type; existing rows keep theirs.
        if (row.dataset.isNew === "true") {
            payload.contributor_type = row.querySelector('[name="contributor_type"]').value;
        }

        return payload;
    }

    function updateFilterData(row) {
        row.dataset.filterContributor_name = row.querySelector('[name="contributor_name"]').value.toLowerCase();
        row.dataset.filterContact_name = row.querySelector('[name="contact_name"]').value.toLowerCase();
        row.dataset.filterEmail = row.querySelector('[name="email"]').value.toLowerCase();
    }

    function undoRowEdits(row) {
        editableFields.forEach((field) => {
            const input = row.querySelector(`[name="${field}"]`);
            input.value = input.dataset.originalValue;
        });
        clearErrors(row);
        row.classList.remove('dirty');

        // Keep the blank entry row available, but finish editing existing rows.
        if (row.dataset.isNew !== "true") {
            lockRow(row);
        }
    }

    /** Bind editing and selection controls for initial or newly created rows. */
    function bindRow(row) {
        const selection = row.querySelector('[name="selected_contributor"]');

        // Unsaved rows have no persistent identity and cannot join toolbar selections.
        if (selection) {
            selection.disabled = false;
            selection.addEventListener("change", selectionChanged);
        }

        // Cache original values so Undo does not require another server request.
        for (const input of getRowInputs(row)) {
            if (input === null) continue;
            input.dataset.originalValue = input.value;
            input.addEventListener("input", markInputDirty);
        }
        row.querySelector("td.row-status span.status").addEventListener("click", toggleClickedRow);
        row.querySelector("td.row-status span.undo").addEventListener("click", undoClickedRow);
    }

    /** Synchronize bulk-selection controls after a row checkbox changes. */
    function selectionChanged() {
        document.getElementById('select-all').checked = allSelected();
        toggle_toolbar();
    }

    /** Mark the owning row dirty while deferring validation until save. */
    function markInputDirty(event) {
        markDirty(event.target.closest('tr'));
    }

    /** Use the status control as an unlock, save, or relock action. */
    function toggleClickedRow(event) {
        return toggleRowLock(event.currentTarget.closest('tr'));
    }

    /** Restore the owning row's cached values from its Undo control. */
    function undoClickedRow(event) {
        undoRowEdits(event.currentTarget.closest('tr'));
    }

    /** Build an entry row with room for subclass-specific display columns. */
    function createEmptyNewRow() {
        const row = document.createElement("tr");
        row.className = "unlocked new-row";
        row.dataset.isNew = "true";
        row.dataset.filterContributor_name = "";
        row.dataset.filterContact_name = "";
        row.dataset.filterEmail = "";
        row.innerHTML = newRowHTML;
        const typeField = document.querySelector('#contributor-sheet [name="contributor_type"]').cloneNode(true);
        typeField.disabled = false;
        row.querySelector('.select').appendChild(typeField);
        const actionsCell = row.querySelector(".actions").closest("td");

        // Display-only extension columns still need blank cells to preserve alignment.
        for (const column of document.querySelectorAll("#contributor-sheet thead th.extra-column")) {
            const cell = document.createElement("td");
            cell.className = "extra-column";
            row.insertBefore(cell, actionsCell);
        }
        bindRow(row);
        return row;
    }

    function appendEmptyNewRow() {
        const tbody = document.querySelector("#contributor-sheet tbody");
        const row = createEmptyNewRow();

        tbody.appendChild(row);

        const firstInput = row.querySelector('[name="contributor_type"]');

        if (firstInput) {
            firstInput.focus();
        }

        return row;
    }

    /** Promote a saved entry row to a contributor with details and contact actions. */
    function applyCreatedContributorToRow(row, contributor) {
        row.dataset.contributorId = contributor.id;
        row.dataset.saveUrl = contributor.save_url;
        addCreatedRowActions(row, contributor);

        // Server-normalized values become both the display and the next Undo baseline.
        for (const field of ["contributor_type", ...editableFields]) {
            row.querySelector(`[name="${field}"]`).value = contributor[field] || "";
        }
        updateFilterData(row);
    }

    /** Clone trusted button templates rather than building contributor HTML strings. */
    function addCreatedRowActions(row, contributor) {
        const contactButton = document.querySelector("#contact-history-button-template")
            .content.firstElementChild.cloneNode(true);
        contactButton.dataset.contactHistoryUrl = contributor.contact_history_url;
        contactButton.setAttribute("aria-label", `Record contact with ${contributor.contributor_name}`);
        row.querySelector(".actions").appendChild(contactButton);
        const detailsButton = document.querySelector("#contributor-details-button-template")
            .content.firstElementChild.cloneNode(true);
        detailsButton.dataset.detailsUrl = contributor.details_url;
        detailsButton.setAttribute("aria-label", `Details for ${contributor.contributor_name}`);
        row.querySelector(".actions").appendChild(detailsButton);
    }

    /** Save valid edits and leave uncertain results unlocked for inspection. */
    async function saveRow(row) {

        // Client-side validation avoids a request while retaining invalid edits.
        if (!validateRow(row)) return;
        const isNew = row.dataset.isNew === "true";
        const result = await requestRowSave(row, isNew);

        // Transport and validation errors already display beside the row.
        if (!result) return;

        // A successful creation consumes the entry row and needs a fresh blank replacement.
        if (isNew) {
            applyCreatedContributorToRow(row, result.contributor);
            lockRow(row);
            appendEmptyNewRow();
        } else {
            updateFilterData(row);
            lockRow(row);
        }
        applyFilters();
    }

    /** Separate uncertain transport outcomes from returned validation failures. */
    async function requestRowSave(row, isNew) {
        const url = isNew ? getSheet().dataset.createUrl : row.dataset.saveUrl;
        let response;

        // A non-JSON reply may follow a committed save, so edits must remain available.
        try {
            response = await fetch(url, {
                method: "POST", headers: {"Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken")},
                body: JSON.stringify(getPayload(row)),
            });
            const data = await response.json();
            if (!response.ok || !data.ok) {
                setErrors(row, data.errors || {"__all__": "Unable to save contributor."});
                return null;
            }
            return data;
        } catch (failure) {
            reportRowSaveFailure(row, response, failure);
            return null;
        }
    }

    /** Avoid encouraging duplicate creation after an unverified server response. */
    function reportRowSaveFailure(row, response, failure) {
        console.error("Spreadsheet row save failed", failure);
        const message = response ?
            `The server returned an unexpected response (HTTP ${response.status}). Your edits are still available; reopen the spreadsheet to check whether they were saved.` :
            "Could not reach the server. Your edits are still available; check your connection before retrying.";
        setErrors(row, {"__all__": message});
    }

    /** Filter saved rows while keeping the blank entry row accessible. */
    function applyFilters() {
        const filters = {};

        // Normalize once so each row uses the same case-insensitive substring rules.
        for (const input of document.querySelectorAll("[data-filter-field]")) {
            filters[input.dataset.filterField] = input.value.trim().toLowerCase();
        }

        // Selection is preserved on hidden rows but excluded from toolbar actions.
        for (const row of document.querySelectorAll("#contributor-sheet tbody tr")) {
            if (row.dataset.isNew === "true") {
                row.hidden = false;
            } else if (row.dataset.contributorId) {
                row.hidden = !rowMatchesFilters(row, filters);
            }
        }
        document.getElementById("select-all").checked = allSelected();
    }

    /** Combine nonempty search fields without requiring exact matches. */
    function rowMatchesFilters(row, filters) {

        // Every populated field must match so adding a search term narrows the list.
        for (const [field, value] of Object.entries(filters)) {
            if (!value) continue;
            const key = `filter${field.charAt(0).toUpperCase()}${field.slice(1)}`;
            if (!(row.dataset[key] || "").includes(value)) return false;
        }
        return true;
    }

    function anySelected() {
        
        const checks = document.querySelectorAll("#contributor-sheet tbody tr:not([hidden]) input[type='checkbox'][name='selected_contributor']")
        console.log(checks);
        for (let i = 0; i < checks.length; i++)
            if( checks[i].checked)
                return true;
        return false;
    }

    function allSelected() {
        
        const checks = document.querySelectorAll("tbody tr:not([hidden]) input[type='checkbox'][name='selected_contributor']")
        for (let i = 0; i < checks.length; i++)
            if( ! checks[i].checked)
                return false;
        return true;
    }

    function select_all(event) {
        
        const selection = event.target.checked;
        document.querySelectorAll("#contributor-sheet tbody tr").forEach((row) => {
            if (! row.hidden && !row.dataset.isNew) {
                row.querySelector('input[type="checkbox"][name="selected_contributor"]').checked = selection;
            }
        });
        toggle_toolbar();
    }

    function toggle_toolbar() {
        const enable_button = anySelected();
        const toolbar_elements = document.querySelectorAll("section#toolbar span");
        toolbar_elements.forEach( (element) => {
                if (enable_button)
                    element.removeAttribute("disabled");
                else
                    element.toggleAttribute("disabled", true);
            })
    }

    function initialiseRows() {
        document.querySelectorAll("#contributor-sheet tbody tr").forEach((row) => {
            if (row.hasAttribute('data-filter-contributor_name')) {
                bindRow(row);
            }
        });
        const selectAll = document.getElementById('select-all');
        selectAll.disabled = false;
        window.addEventListener('pageshow', () => { selectAll.disabled = false; });
        selectAll.addEventListener('change', (event) => {
            select_all( event);
        })
    }

    function initialiseFilters() {
        document.querySelector(
            'section#toolbar button.search-icon').addEventListener('click', (event)=>{
                const button = event.currentTarget;
                const searchBar = document.getElementById('search-bar');
                const expanded = searchBar.toggleAttribute('active');
                button.classList.toggle('active', expanded);
                button.setAttribute('aria-expanded', String(expanded));
        });

        document.querySelectorAll("[data-filter-field]").forEach((input) => {
            input.addEventListener("input", applyFilters);
        });
    }

    const contact = {saving: false, row: null};

    /** Bind the shared contact dialog once for current and dynamically added rows. */
    function initialiseContactHistory() {
        contact.dialog = document.querySelector("#contact-history-dialog");
        contact.form = document.querySelector("#contact-history-form");
        contact.error = document.querySelector("#contact-history-error");
        contact.save = document.querySelector("#contact-history-save");
        contact.cancel = document.querySelector("#contact-history-cancel");
        document.addEventListener("click", openContactHistory);
        contact.cancel.addEventListener("click", closeContactHistory);
        contact.dialog.addEventListener("cancel", cancelContactHistory);
        contact.form.addEventListener("submit", submitContactHistory);
    }

    /** Populate identity and local date without permitting notes on unsaved rows. */
    function openContactHistory(event) {
        const button = event.target.closest(".add-contact-history");

        // Most document clicks do not target contact controls.
        if (!button) return;
        contact.row = button.closest("tr") || getSheet().querySelector(`tr[data-contributor-id="${button.dataset.contributorId}"]`);

        // Details dialogs locate their saved contributor row through its persistent identity.
        if (!contact.row || contact.row.dataset.isNew === "true") return;
        contact.form.reset();
        contact.form.action = button.dataset.contactHistoryUrl;
        contact.error.textContent = "";
        document.querySelector("#contact-history-contributor").textContent =
            contact.row.querySelector('[name="contributor_name"]').value;
        const today = new Date();
        document.querySelector("#contact-history-date").value =
            `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
        contact.dialog.showModal();
        document.querySelector("#contact-history-note").focus();
    }

    /** Close an idle contact popup from its Cancel control. */
    function closeContactHistory() {
        contact.dialog.close();
    }

    /** Keep an unresolved contact save visible until the server responds. */
    function cancelContactHistory(event) {

        // Escape must follow the same restriction as the disabled Cancel control.
        if (contact.saving) event.preventDefault();
    }

    /** Prevent duplicate notes while preserving input after validation failures. */
    async function submitContactHistory(event) {
        event.preventDefault();

        // Repeated submit events must not append duplicate history records.
        if (contact.saving) return;
        setContactSaving(true);
        contact.error.textContent = "";

        // Release the popup controls after both transport and server-side failures.
        try {
            await saveContactHistory();
        } catch (failure) {
            contact.error.textContent = "Unable to save contact history. Please try again.";
        } finally {
            setContactSaving(false);
        }
    }

    /** Keep save and cancellation controls consistent with the pending request. */
    function setContactSaving(value) {
        contact.saving = value;
        contact.save.disabled = value;
        contact.cancel.disabled = value;
    }

    /** Publish contact changes only after the note has been accepted by the server. */
    async function saveContactHistory() {
        const response = await fetch(contact.form.action, {
            method: "POST", body: new FormData(contact.form),
            headers: {"X-CSRFToken": contact.form.querySelector('[name="csrfmiddlewaretoken"]').value},
        });
        const data = await response.json();

        // Keep the note editable when validation rejects its date or text.
        if (!response.ok || !data.ok) {
            contact.error.textContent = Object.values(data.errors || {}).flat()
                .map(/** Extract server field messages. */ item => item.message).join(" ") || "Unable to save contact history.";
            return;
        }
        updateLastContact(contact.row, data.contact_date);
        contact.dialog.close();
        getSheet().dispatchEvent(new CustomEvent("contact-history-saved", {
            detail: {row: contact.row, contactDate: data.contact_date},
        }));
    }

    /** Advance contact indicators only for newer notes belonging to this event cycle. */
    function updateLastContact(row, date) {
        const lastContact = row.querySelector(".last-contact-date");
        const cutoff = getSheet().dataset.historicEventDate;

        // Backdated notes belong in history but must not regress the visible last-contact date.
        if (date > (cutoff || "") && date > (lastContact.dataset.date || "")) {
            lastContact.dataset.date = date;
            const [year, month, day] = date.split("-");
            lastContact.value = `${day}/${month}/${year}`;
        }
    }

    function initialiseContributorSpreadsheet() {
        initialiseRows();
        initialiseFilters();
        initialiseContactHistory();
        getSheet().addEventListener("contributor-details-saved", (event) => {
            const {row, contributor} = event.detail;
            for (const field of ["contributor_name", "contact_name", "phone", "email", "contributor_type"]) {
                const input = row.querySelector(`[name="${field}"]`);
                if (input) input.value = contributor[field] || "";
            }
            lockRow(row);
            updateFilterData(row);
            applyFilters();
            row.querySelector(".contributor-details-button").setAttribute("aria-label", `Details for ${contributor.contributor_name}`);
            row.querySelector(".add-contact-history").setAttribute("aria-label", `Record contact with ${contributor.contributor_name}`);
        });

    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialiseContributorSpreadsheet);
    } else {
        initialiseContributorSpreadsheet();
    }

    window.ContributorSpreadsheet = {
        validateRow,
        unlockRow: toggleRowLock,
        lockRow,
        markDirty,
        undoRowEdits,
        applyFilters,
        getPayload,
        createEmptyNewRow,
        appendEmptyNewRow,
    };
}
