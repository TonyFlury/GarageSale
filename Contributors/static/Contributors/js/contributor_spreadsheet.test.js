/**
 * @jest-environment jsdom
 */

function loadScript() {
    jest.resetModules();
    require("./contributor_spreadsheet");
}

function buildDom() {
    document.body.innerHTML = `
        <input data-filter-field="contributor_name">
        <input data-filter-field="contact_name">
        <input data-filter-field="email">
        <input data-filter-field="description">

        <table id="contributor-sheet" data-create-url="/contributors/spreadsheet/create/">
            <tbody>
               <tr
                    class="locked"
                    data-contributor-id="1"
                    data-save-url="/contributors/spreadsheet/1/save/"
                    data-filter-contributor_name="acme ltd"
                    data-filter-contact_name="alex smith"
                    data-filter-email="alex@example.com"
                    data-filter-description="original description"
                >
                    <td><span class="row-status locked">Locked</span></td>
                    <td>
                        <input name="contributor_type" value="Sponsor" disabled>
                        <span class="field-error" data-error-for="contributor_type"></span>
                    </td>
                    <td>
                        <input name="contributor_name" value="Acme Ltd" disabled>
                        <span class="field-error" data-error-for="contributor_name"></span>
                    </td>
                    <td>
                        <input name="contact_name" value="Alex Smith" disabled>
                        <span class="field-error" data-error-for="contact_name"></span>
                    </td>
                    <td>
                        <input name="phone" value="01234567890" disabled>
                        <span class="field-error" data-error-for="phone"></span>
                    </td>
                    <td>
                        <input name="email" value="alex@example.com" disabled>
                        <span class="field-error" data-error-for="email"></span>
                    </td>
                    <td>
                        <textarea name="description" disabled>Original description</textarea>
                        <span class="field-error" data-error-for="description"></span>
                    </td>
                    <td>
                        <button type="button" class="unlock-row">Unlock</button>
                        <button type="button" class="save-row">Save</button>
                    </td>
                </tr>

                <tr
                    class="locked"
                    data-contributor-id="2"
                    data-save-url="/contributors/spreadsheet/2/save/"
                    data-filter-contributor_name="beta ltd"
                    data-filter-contact_name="casey green"
                    data-filter-email="casey@example.com"
                    data-filter-description="another description"
                >
                    <td><span class="row-status locked">Locked</span></td>
                    <td>
                        <input name="contributor_type" value="Donor" disabled>
                        <span class="field-error" data-error-for="contributor_type"></span>
                    </td>
                    <td>
                        <input name="contributor_name" value="Beta Ltd" disabled>
                        <span class="field-error" data-error-for="contributor_name"></span>
                    </td>
                    <td>
                        <input name="contact_name" value="Casey Green" disabled>
                        <span class="field-error" data-error-for="contact_name"></span>
                    </td>
                    <td>
                        <input name="phone" value="07123456789" disabled>
                        <span class="field-error" data-error-for="phone"></span>
                    </td>
                    <td>
                        <input name="email" value="casey@example.com" disabled>
                        <span class="field-error" data-error-for="email"></span>
                    </td>
                    <td>
                        <textarea name="description" disabled>Another description</textarea>
                        <span class="field-error" data-error-for="description"></span>
                    </td>
                    <td>
                        <button type="button" class="unlock-row">Unlock</button>
                        <button type="button" class="save-row">Save</button>
                    </td>
                </tr>
            </tbody>
        </table>
    `;
}

describe("Contributor spreadsheet", () => {
    beforeEach(() => {
        buildDom();
        loadScript();
    });

    // ... existing code ...

    test("createEmptyNewRow creates an unlocked new dirty row", () => {
        const row = window.ContributorSpreadsheet.createEmptyNewRow();

        expect(row.dataset.isNew).toBe("true");
        expect(row.classList.contains("new-row")).toBe(true);
        expect(row.classList.contains("unlocked")).toBe(true);
        expect(row.classList.contains("dirty")).toBe(true);
        expect(row.querySelector('[name="contributor_name"]').disabled).toBe(false);
        expect(row.querySelector(".row-status").textContent).toBe("New - save required");
    });

    test("appendEmptyNewRow appends a new unlocked row to the sheet", () => {
        const originalRowCount = document.querySelectorAll("#contributor-sheet tbody tr").length;

        window.ContributorSpreadsheet.appendEmptyNewRow();

        const newRowCount = document.querySelectorAll("#contributor-sheet tbody tr").length;
        const newRow = document.querySelector("#contributor-sheet tbody tr:last-child");

        expect(newRowCount).toBe(originalRowCount + 1);
        expect(newRow.dataset.isNew).toBe("true");
    });
    test("rows are locked by default", () => {
        const row = document.querySelector('[data-contributor-id="1"]');
        const input = row.querySelector('[name="contributor_name"]');

        expect(row.classList.contains("locked")).toBe(true);
        expect(input.disabled).toBe(true);
    });

    test("unlockRow unlocks inputs and updates status", () => {
        const row = document.querySelector('[data-contributor-id="1"]');

        window.ContributorSpreadsheet.unlockRow(row);

        expect(row.classList.contains("unlocked")).toBe(true);
        expect(row.querySelector('[name="contributor_name"]').disabled).toBe(false);
        expect(row.querySelector(".row-status").textContent).toBe("Unlocked");
    });

    test("markDirty marks unlocked row as changed", () => {
        const row = document.querySelector('[data-contributor-id="1"]');

        window.ContributorSpreadsheet.unlockRow(row);
        window.ContributorSpreadsheet.markDirty(row);

        expect(row.classList.contains("dirty")).toBe(true);
        expect(row.querySelector(".row-status").textContent).toBe("Changed - save required");
    });

    test("validateRow rejects blank company name", () => {
        const row = document.querySelector('[data-contributor-id="1"]');

        window.ContributorSpreadsheet.unlockRow(row);

        row.querySelector('[name="contributor_name"]').value = "";

        const isValid = window.ContributorSpreadsheet.validateRow(row);

        expect(isValid).toBe(false);
        expect(row.classList.contains("invalid")).toBe(true);
        expect(row.querySelector('[data-error-for="contributor_name"]').textContent).toBe(
            "Company name is required."
        );
    });

    test("validateRow rejects invalid email", () => {
        const row = document.querySelector('[data-contributor-id="1"]');

        window.ContributorSpreadsheet.unlockRow(row);

        row.querySelector('[name="email"]').value = "not-an-email";

        const isValid = window.ContributorSpreadsheet.validateRow(row);

        expect(isValid).toBe(false);
        expect(row.classList.contains("invalid")).toBe(true);
        expect(row.querySelector('[data-error-for="email"]').textContent).toBe(
            "Enter a valid email address."
        );
    });

    test("applyFilters hides non-matching rows", () => {
        const filter = document.querySelector('[data-filter-field="contributor_name"]');

        filter.value = "acme";

        window.ContributorSpreadsheet.applyFilters();

        const acmeRow = document.querySelector('[data-contributor-id="1"]');
        const betaRow = document.querySelector('[data-contributor-id="2"]');

        expect(acmeRow.hidden).toBe(false);
        expect(betaRow.hidden).toBe(true);
    });

    test("getPayload returns editable contributor fields", () => {
        const row = document.querySelector('[data-contributor-id="1"]');

        const payload = window.ContributorSpreadsheet.getPayload(row);

        expect(payload).toEqual({
            contributor_type: "Sponsor",
            contributor_name: "Acme Ltd",
            contact_name: "Alex Smith",
            phone: "01234567890",
            email: "alex@example.com",
            description: "Original description",
        });
    });
});