const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../static/GarageSale/js/communication_template_attachments.js'), 'utf8');

function attachment(hasFile = false) {
    const upload = {checked: false};
    const remove = {checked: false};
    const name = {focus() {this.focused = true;}};
    const file = {type: 'file'};
    const nameField = {querySelectorAll: () => [name]};
    const fileField = {querySelectorAll: () => [file]};
    const row = {dataset: {hasFile: String(hasFile)}, querySelector(selector) {
        return {'[data-attachment-upload]': upload, 'input[name$="-DELETE"]': remove,
            '[data-name-field]': nameField, '[data-file-field]': fileField, '[data-name-field] input': name}[selector];
    }};
    return {row, upload, remove, name, file, nameField, fileField};
}

function setup(hasFile = false) {
    const first = attachment(hasFile);
    const listeners = {};
    let added;
    const container = {querySelectorAll: () => [first.row], addEventListener(type, callback) {listeners[type] = callback;},
        insertAdjacentHTML(position, html) {
            this.insertedHTML = html;
            added = attachment();
            this.lastElementChild = added.row;
        }};
    let addRow;
    const add = {addEventListener(type, callback) {addRow = callback;}};
    const total = {value: '1'};
    const document = {readyState: 'complete', querySelector(selector) {
        return {'#communication-template-attachments': container, '#communication-template-attachment-add': add,
            '#communication-template-attachment-empty': {innerHTML: 'name="attachments-__prefix__-template_name" id="id_attachments-__prefix__-upload"'},
            '#id_attachments-TOTAL_FORMS': total}[selector];
    }};
    vm.runInNewContext(source, {document});
    return {first, container, total, addRow, added: () => added,
        update: () => listeners.change({target: {closest: () => first.row}}),
        removeRow: () => listeners.click({target: {closest: () => ({closest: () => first.row})}})};
}

test('Upload toggles visibility and disables the inactive fields', () => {
    const ui = setup();
    assert.equal(ui.first.nameField.hidden, false);
    assert.equal(ui.first.fileField.hidden, true);
    assert.equal(ui.first.name.required, true);
    ui.first.upload.checked = true; ui.update();
    assert.equal(ui.first.nameField.hidden, true);
    assert.equal(ui.first.name.disabled, true);
    assert.equal(ui.first.fileField.hidden, false);
    assert.equal(ui.first.file.required, true);
    ui.first.upload.checked = false; ui.update();
    assert.equal(ui.first.name.disabled, false);
    assert.equal(ui.first.file.disabled, true);
});

test('existing uploaded files do not require a replacement', () => {
    const ui = setup(true); ui.first.upload.checked = true; ui.update();
    assert.equal(ui.first.file.required, false);
});

test('x marks the row for deletion, hides it and removes browser validation', () => {
    const ui = setup(); ui.removeRow();
    assert.equal(ui.first.remove.checked, true);
    assert.equal(ui.first.row.hidden, true);
    assert.equal(ui.first.name.disabled, true);
    assert.equal(ui.first.name.required, false);
});

test('Add attachment gives new fields a unique formset index and focuses the name', () => {
    const ui = setup(); ui.addRow();
    assert.equal(ui.total.value, '2');
    assert.match(ui.container.insertedHTML, /attachments-1-template_name/);
    assert.doesNotMatch(ui.container.insertedHTML, /__prefix__/);
    assert.equal(ui.added().name.focused, true);
    ui.addRow();
    assert.equal(ui.total.value, '3');
    assert.match(ui.container.insertedHTML, /attachments-2-template_name/);
});
