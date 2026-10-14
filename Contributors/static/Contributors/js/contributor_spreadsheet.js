/* TODO Validation - make either or Phone/email mandatory
* TODO : 'Data' driven actions (edit details, communicate, invite, confirm etc */

(function () {
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
     /*   setStatus(row, "Invalid", "invalid"); */
    }

    function validateRow(row) {
        const errors = {};
        const contributorTypeInput = row.querySelector('[name="contributor_type"]');
        const contributorName = row.querySelector('[name="contributor_name"]').value.trim();
        const contactName = row.querySelector('[name="contact_name"]').value.trim();
        const phone = row.querySelector('[name="phone"]').value.trim();
        const email = row.querySelector('[name="email"]').value.trim();

        // Existing rows retain their stored type and do not have a type input.
        if (row.dataset.isNew === "true" && !contributorTypeInput?.value.trim()) {
            errors.contributor_type = `${getSheet()?.dataset.label || "Contributor"} type is required.`;
        }

        if (!contributorName) {
            errors.contributor_name = "Company name is required.";
        }

        if (contactName.length > 120) {
            errors.contact_name = "Contact name must be 120 characters or fewer.";
        }

        if (phone.length > 12) {
            errors.phone = "Phone must be 12 characters or fewer.";
        }

        if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            errors.email = "Enter a valid email address.";
        }

        if (Object.keys(errors).length > 0) {
            setErrors(row, errors);
            return false;
        }

        clearErrors(row);
        return true;
    }

    function toggleRowLock(row) {

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

  /*      const unlockButton = row.querySelector(".unlock-row");
        unlockButton.disabled = false;
        unlockButton.textContent = "Unlock"; */

        clearErrors(row);
       /* setStatus(row, "Saved", "saved"); */
    }

    function markDirty(row) {
        if (row.classList.contains("locked")) {
            return;
        }

        row.classList.add("dirty");

/*        if (row.dataset.isNew === "true") {
             setStatus(row, "New - save required", "dirty");
            return;
        }

        if (!row.classList.contains("invalid")) {
            setStatus(row, "Changed - save required", "dirty");
        } */
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

    function bindRow(row) {
        const selection = row.querySelector('[name="selected_contributor"]');
        if (selection) {
            selection.disabled = false;
            selection.addEventListener("change", () => {
                document.getElementById('select-all').checked = allSelected();
                toggle_toolbar();
            });
        }

        getRowInputs(row).forEach((input) => {
            if (input === null)
                return;

            input.dataset.originalValue = input.value;

            input.addEventListener("input", () => {
                markDirty(row);

                /* Validate on save */
                /* validateRow(row); */
            });
        });

        const unlockButton = row.querySelector("td.row-status span.status");
        unlockButton.addEventListener("click", () => {
            toggleRowLock(row);
        });

        const undoButton = row.querySelector("td.row-status span.undo");
            undoButton.addEventListener("click", () => {
            undoRowEdits(row);
        });
    }

    function createEmptyNewRow() {
        const row = document.createElement("tr");

        row.className = "unlocked new-row";
        row.dataset.isNew = "true";
        row.dataset.filterContributor_name = "";
        row.dataset.filterContact_name = "";
        row.dataset.filterEmail = "";

        row.innerHTML = `
            <td class="row-status">
                    <span class="status" > </span>
                    <span class="undo" > </span>
                </td>
            </td>

            <td>
                <input name="contributor_type" value="" maxlength="30" required>
                <span class="field-error" data-error-for="contributor_type"></span>
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

        const actionsCell = row.querySelector(".actions").closest("td");
        document.querySelectorAll("#contributor-sheet thead th.extra-column").forEach(() => {
            const cell = document.createElement("td");
            cell.className = "extra-column";
            row.insertBefore(cell, actionsCell);
        });

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

    function applyCreatedContributorToRow(row, contributor) {
        row.dataset.contributorId = contributor.id;
        row.dataset.saveUrl = contributor.save_url;
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

        row.querySelector('[name="contributor_type"]').value = contributor.contributor_type;
        row.querySelector('[name="contributor_name"]').value = contributor.contributor_name;
        row.querySelector('[name="contact_name"]').value = contributor.contact_name || "";
        row.querySelector('[name="phone"]').value = contributor.phone || "";
        row.querySelector('[name="email"]').value = contributor.email || "";

        updateFilterData(row);
    }

    async function saveRow(row) {
        if (!validateRow(row)) {
            return;
        }

        const isNew = row.dataset.isNew === "true";
        const sheet = getSheet();
        const url = isNew ? sheet.dataset.createUrl : row.dataset.saveUrl;

        let response, data;
        try {
            response = await fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCookie("csrftoken"),
                },
                body: JSON.stringify(getPayload(row)),
            });
            data = await response.json();
        } catch (failure) {
            console.error("Spreadsheet row save failed", failure);
            const message = response ?
                `The server returned an unexpected response (HTTP ${response.status}). Your edits are still available; reopen the spreadsheet to check whether they were saved.` :
                "Could not reach the server. Your edits are still available; check your connection before retrying.";
            setErrors(row, {"__all__": message});
            return;
        }

        if (!response.ok || !data.ok) {
            setErrors(row, data.errors || { "__all__": "Unable to save contributor." });
            return;
        }

        if (isNew) {
            applyCreatedContributorToRow(row, data.contributor);
            lockRow(row);
            appendEmptyNewRow();
            applyFilters();
            return;
        }

        updateFilterData(row);
        lockRow(row);
        applyFilters();
    }

    function applyFilters() {
        const filters = {};
        console.log("apply filters");

        document.querySelectorAll("[data-filter-field]").forEach((input) => {
            filters[input.dataset.filterField] = input.value.trim().toLowerCase();
        });

        document.querySelectorAll("#contributor-sheet tbody tr").forEach((row) => {
            if (row.dataset.isNew === "true") {
                row.hidden = false;
                return;
            }

            if (!row.dataset.contributorId) {
                return;
            }

            const visible = Object.entries(filters).every(([field, value]) => {
                if (!value) {
                    return true;
                }

                const dataKey = `filter${field.charAt(0).toUpperCase()}${field.slice(1)}`;
                return (row.dataset[dataKey] || "").includes(value);
            });

            row.hidden = !visible;
        });
        document.getElementById("select-all").checked = allSelected()
    }

    function anySelected() {
        /* True if any non-hidden rows are selected */
        const checks = document.querySelectorAll("#contributor-sheet tbody tr:not([hidden]) input[type='checkbox'][name='selected_contributor']")
        console.log(checks);
        for (let i = 0; i < checks.length; i++)
            if( checks[i].checked)
                return true;
        return false;
    }

    function allSelected() {
        /* True if all non-hidden rows are selected */
        const checks = document.querySelectorAll("tbody tr:not([hidden]) input[type='checkbox'][name='selected_contributor']")
        for (let i = 0; i < checks.length; i++)
            if( ! checks[i].checked)
                return false;
        return true;
    }

    function select_all(event) {
        /** Toggle selection on rows */
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

    function initialiseContactHistory() {
        const dialog = document.querySelector("#contact-history-dialog");
        const form = document.querySelector("#contact-history-form");
        const error = document.querySelector("#contact-history-error");
        const save = document.querySelector("#contact-history-save");
        const cancel = document.querySelector("#contact-history-cancel");
        let saving = false;
        let contactRow = null;

        document.addEventListener("click", (event) => {
            const button = event.target.closest(".add-contact-history");
            if (!button) return;
            contactRow = button.closest("tr") || getSheet().querySelector(`tr[data-contributor-id="${button.dataset.contributorId}"]`);
            if (!contactRow || contactRow.dataset.isNew === "true") return;
            form.reset();
            form.action = button.dataset.contactHistoryUrl;
            error.textContent = "";
            document.querySelector("#contact-history-contributor").textContent =
                contactRow.querySelector('[name="contributor_name"]').value;
            const today = new Date();
            document.querySelector("#contact-history-date").value =
                `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
            dialog.showModal();
            document.querySelector("#contact-history-note").focus();
        });

        cancel.addEventListener("click", () => dialog.close());
        dialog.addEventListener("cancel", (event) => {
            if (saving) event.preventDefault();
        });
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (saving) return;
            saving = true;
            save.disabled = true;
            cancel.disabled = true;
            error.textContent = "";
            try {
                const response = await fetch(form.action, {
                    method: "POST", body: new FormData(form),
                    headers: {"X-CSRFToken": form.querySelector('[name="csrfmiddlewaretoken"]').value},
                });
                const data = await response.json();
                if (!response.ok || !data.ok) {
                    error.textContent = Object.values(data.errors || {}).flat()
                        .map((item) => item.message).join(" ") || "Unable to save contact history.";
                    return;
                }
                const lastContact = contactRow.querySelector(".last-contact-date");
                const cutoff = getSheet().dataset.historicEventDate;
                if (data.contact_date > (cutoff || "") && data.contact_date > (lastContact.dataset.date || "")) {
                    lastContact.dataset.date = data.contact_date;
                    const [year, month, day] = data.contact_date.split("-");
                    lastContact.value = `${day}/${month}/${year}`;
                }
                dialog.close();
                getSheet().dispatchEvent(new CustomEvent("contact-history-saved", {
                    detail: {row: contactRow, contactDate: data.contact_date},
                }));
            } catch (failure) {
                error.textContent = "Unable to save contact history. Please try again.";
            } finally {
                saving = false;
                save.disabled = false;
                cancel.disabled = false;
            }
        });
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
})();
