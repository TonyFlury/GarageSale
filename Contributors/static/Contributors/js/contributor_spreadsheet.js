/* TODO Validation - make either or Phone/email mandatory
*  TODO : Remove 'Edit' button, and allow edit on text area by clicking the text itself (less screen real estate)
* TODO : 'Data' driven actions (edit details, communicate, invite, confirm etc */


(function () {
    const editableFields = [
        "contributor_type",
        "contributor_name",
        "contact_name",
        "phone",
        "email",
        "description",
    ];

        let activeDescriptionRow = null;
    let activeDescriptionInput = null;

    function getDescriptionDialog() {
        return document.querySelector("#description-editor-dialog");
    }

    function getDescriptionEditor() {
        return document.querySelector("#description-editor-textarea");
    }

    function updateDescriptionCounter() {
        const editor = getDescriptionEditor();
        const counter = document.querySelector("#description-editor-count");

        if (!editor || !counter) {
            return;
        }

        counter.textContent = `${editor.value.length} / ${editor.maxLength}`;
    }

    function openDescriptionEditor(row, input) {
        if (row.classList.contains("locked")) {
            return;
        }

        const dialog = getDescriptionDialog();
        const editor = getDescriptionEditor();

        if (!dialog || !editor) {
            return;
        }

        activeDescriptionRow = row;
        activeDescriptionInput = input;

        editor.value = input.value;
        updateDescriptionCounter();

        dialog.showModal();
        editor.focus();
        editor.select();
    }

    function applyDescriptionEditor() {
        const dialog = getDescriptionDialog();
        const editor = getDescriptionEditor();

        if (!activeDescriptionRow || !activeDescriptionInput || !dialog || !editor) {
            return;
        }

        activeDescriptionInput.value = editor.value;
        activeDescriptionInput.title = editor.value;

        markDirty(activeDescriptionRow);
        validateRow(activeDescriptionRow);

        dialog.close();

        activeDescriptionRow = null;
        activeDescriptionInput = null;
    }

    function cancelDescriptionEditor() {
        const dialog = getDescriptionDialog();

        if (dialog) {
            dialog.close();
        }

        activeDescriptionRow = null;
        activeDescriptionInput = null;
    }

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
            const errorElement = row.querySelector(`[data-error-for="${field}"]`);

            if (errorElement) {
                errorElement.textContent = message;
            }
        });

        row.classList.add("invalid");
        setStatus(row, "Invalid", "invalid");
    }

    function validateRow(row) {
        const errors = {};
        const contributorType = row.querySelector('[name="contributor_type"]').value.trim();
        const contributorName = row.querySelector('[name="contributor_name"]').value.trim();
        const contactName = row.querySelector('[name="contact_name"]').value.trim();
        const phone = row.querySelector('[name="phone"]').value.trim();
        const email = row.querySelector('[name="email"]').value.trim();
        const description = row.querySelector('[name="description"]').value.trim();

        if (!contributorType) {
            errors.contributor_type = "Contributor type is required.";
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

        if (description.length > 1000) {
            errors.description = "Description must be 1000 characters or fewer.";
        }

        if (Object.keys(errors).length > 0) {
            setErrors(row, errors);
            return false;
        }

        clearErrors(row);
        return true;
    }

    function unlockRow(row) {
        if (row.dataset.isNew === "true") {
            return;
        }

        row.classList.remove("locked");
        row.classList.add("unlocked");

        getRowInputs(row).forEach((input) => {
            input.disabled = false;
        });

        const descriptionInput = row.querySelector('[name="description"]');

        if (descriptionInput) {
            descriptionInput.readOnly = true;
        }

        const editDescriptionButton = row.querySelector(".edit-description");

        if (editDescriptionButton) {
            editDescriptionButton.disabled = false;
        }

        setStatus(row, "Unlocked", "unlocked");
    }

    function lockRow(row) {
        row.classList.remove("unlocked", "dirty", "invalid", "new-row");
        row.classList.add("locked");

        delete row.dataset.isNew;

        getRowInputs(row).forEach((input) => {
            input.disabled = true;
            input.dataset.originalValue = input.value;
        });

        const editDescriptionButton = row.querySelector(".edit-description");

        if (editDescriptionButton) {
            editDescriptionButton.disabled = true;
        }

        const unlockButton = row.querySelector(".unlock-row");
        unlockButton.disabled = false;
        unlockButton.textContent = "Unlock";

        clearErrors(row);
        setStatus(row, "Saved", "saved");
    }

    function markDirty(row) {
        if (row.classList.contains("locked")) {
            return;
        }

        row.classList.add("dirty");

        if (row.dataset.isNew === "true") {
            setStatus(row, "New - save required", "dirty");
            return;
        }

        if (!row.classList.contains("invalid")) {
            setStatus(row, "Changed - save required", "dirty");
        }
    }

    function getPayload(row) {
        const payload = {};

        editableFields.forEach((field) => {
            payload[field] = row.querySelector(`[name="${field}"]`).value;
        });

        return payload;
    }

    function updateFilterData(row) {
        row.dataset.filterContributor_name = row.querySelector('[name="contributor_name"]').value.toLowerCase();
        row.dataset.filterContact_name = row.querySelector('[name="contact_name"]').value.toLowerCase();
        row.dataset.filterEmail = row.querySelector('[name="email"]').value.toLowerCase();
        row.dataset.filterDescription = row.querySelector('[name="description"]').value.toLowerCase();
    }

    function bindRow(row) {
        getRowInputs(row).forEach((input) => {
            input.dataset.originalValue = input.value;

            if (input.name === "description") {
                input.addEventListener("click", () => {
                    openDescriptionEditor(row, input);
                });

                input.addEventListener("focus", () => {
                    openDescriptionEditor(row, input);
                });

                return;
            }

            input.addEventListener("input", () => {
                markDirty(row);
                validateRow(row);
            });
        });

        const editDescriptionButton = row.querySelector(".edit-description");

        if (editDescriptionButton) {
            editDescriptionButton.addEventListener("click", () => {
                const descriptionInput = row.querySelector('[name="description"]');

                if (descriptionInput) {
                    openDescriptionEditor(row, descriptionInput);
                }
            });
        }

        const unlockButton = row.querySelector(".unlock-row");

        unlockButton.addEventListener("click", () => {
            unlockRow(row);
        });

        row.querySelector(".save-row").addEventListener("click", () => {
            saveRow(row);
        });
    }

    function createEmptyNewRow() {
        const row = document.createElement("tr");

        row.className = "unlocked new-row dirty";
        row.dataset.isNew = "true";
        row.dataset.filterContributor_name = "";
        row.dataset.filterContact_name = "";
        row.dataset.filterEmail = "";
        row.dataset.filterDescription = "";

        row.innerHTML = `
            <td>
                <span class="row-status dirty">New - save required</span>
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

            <td>
                <div class="description-cell">
                    <input
                        name="description"
                        class="description-preview"
                        value=""
                        maxlength="1000"
                        readonly
                        title=""
                    >
                    <button
                        type="button"
                        class="edit-description"
                    >
                        Edit
                    </button>
                </div>
                <span class="field-error" data-error-for="description"></span>
            </td>

            <td>
                <div class="actions">
                    <button type="button" class="unlock-row" disabled>Unlocked</button>
                    <button type="button" class="save-row">Save</button>
                </div>
            </td>
        `;

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

        row.querySelector('[name="contributor_type"]').value = contributor.contributor_type;
        row.querySelector('[name="contributor_name"]').value = contributor.contributor_name;
        row.querySelector('[name="contact_name"]').value = contributor.contact_name || "";
        row.querySelector('[name="phone"]').value = contributor.phone || "";
        row.querySelector('[name="email"]').value = contributor.email || "";
        row.querySelector('[name="description"]').value = contributor.description || "";

        updateFilterData(row);
    }

    async function saveRow(row) {
        if (!validateRow(row)) {
            return;
        }

        const isNew = row.dataset.isNew === "true";
        const sheet = getSheet();
        const url = isNew ? sheet.dataset.createUrl : row.dataset.saveUrl;

        const response = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify(getPayload(row)),
        });

        const data = await response.json();

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
    }

    function initialiseRows() {
        document.querySelectorAll("#contributor-sheet tbody tr").forEach((row) => {
            if (row.querySelector('[name="contributor_type"]')) {
                bindRow(row);
            }
        });
    }

    function initialiseFilters() {
        document.querySelectorAll("[data-filter-field]").forEach((input) => {
            input.addEventListener("input", applyFilters);
        });
    }

    function initialiseDescriptionEditor() {
        const editor = getDescriptionEditor();
        const applyButton = document.querySelector("#description-editor-apply");
        const cancelButton = document.querySelector("#description-editor-cancel");
        const dialog = getDescriptionDialog();

        if (!editor || !applyButton || !cancelButton || !dialog) {
            return;
        }

        editor.addEventListener("input", updateDescriptionCounter);

        applyButton.addEventListener("click", applyDescriptionEditor);
        cancelButton.addEventListener("click", cancelDescriptionEditor);

        dialog.addEventListener("cancel", () => {
            activeDescriptionRow = null;
            activeDescriptionInput = null;
        });
    }

    function initialiseContributorSpreadsheet() {
        initialiseRows();
        initialiseFilters();
        initialiseDescriptionEditor();

    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialiseContributorSpreadsheet);
    } else {
        initialiseContributorSpreadsheet();
    }

    window.ContributorSpreadsheet = {
        validateRow,
        unlockRow,
        lockRow,
        markDirty,
        applyFilters,
        getPayload,
        createEmptyNewRow,
        appendEmptyNewRow,
        openDescriptionEditor,
        applyDescriptionEditor,
        cancelDescriptionEditor
    };
})();