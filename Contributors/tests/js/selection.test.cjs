const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../static/Contributors/js/contributor_spreadsheet.js'), 'utf8');

test('locking a row disables editable fields while leaving selection available', () => {
    const selection = {disabled: false, checked: true, value: '7', dataset: {}};
    const inputs = {};
    for (const name of ['contributor_name', 'contact_name', 'phone', 'email']) {
        inputs[name] = {disabled: false, value: name, dataset: {}};
    }
    const row = {
        dataset: {},
        classList: {remove() {}, add() {}},
        querySelector(selector) {
            const name = selector.match(/name="([^"]+)"/)?.[1];
            return name === 'selected_contributor' ? selection : inputs[name];
        },
        querySelectorAll() { return []; },
    };
    const window = {};
    vm.runInNewContext(source, {window, document: {readyState: 'loading', addEventListener() {}}});
    window.ContributorSpreadsheet.lockRow(row);
    assert.equal(selection.disabled, false);
    assert.equal(selection.checked, true);
    for (const input of Object.values(inputs)) assert.equal(input.disabled, true);
    const payload = window.ContributorSpreadsheet.getPayload(row);
    assert.equal(Object.hasOwn(payload, 'selected_contributor'), false);
});

function editableRow() {
    const inputs = {};
    for (const [name, value] of Object.entries({contributor_name: 'Acme', contact_name: 'Alex', phone: '', email: ''})) {
        inputs[name] = {value, disabled: true, dataset: {originalValue: value}};
    }
    const classes = new Set(['locked']);
    const row = {
        dataset: {contributorId: '7', saveUrl: '/contributors/spreadsheet/7/save/'},
        classList: {contains: name => classes.has(name), add: (...names) => names.forEach(name => classes.add(name)),
            remove: (...names) => names.forEach(name => classes.delete(name))},
        querySelector: selector => inputs[selector.match(/name="([^"]+)"/)?.[1]] || null,
        querySelectorAll: () => [],
    };
    const document = {readyState: 'loading', cookie: '', addEventListener() {},
        querySelector: () => ({dataset: {label: 'Sponsor'}}), querySelectorAll: () => [],
        getElementById: () => ({checked: false})};
    const window = {};
    const requests = [];
    vm.runInNewContext(source, {window, document, console: {log() {}}, fetch: async (url, options) => {
        requests.push({url, payload: JSON.parse(options.body)});
        return {ok: true, json: async () => ({ok: true})};
    }});
    return {row, inputs, classes, requests, api: window.ContributorSpreadsheet};
}

test('changing only contact name saves an existing row with no contributor type input', async () => {
    const ui = editableRow();
    ui.api.unlockRow(ui.row);
    ui.inputs.contact_name.value = 'New contact';
    ui.api.markDirty(ui.row);
    await ui.api.unlockRow(ui.row);
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.requests[0].url, '/contributors/spreadsheet/7/save/');
    assert.equal(ui.requests[0].payload.contact_name, 'New contact');
    assert.equal(Object.hasOwn(ui.requests[0].payload, 'contributor_type'), false);
    assert.equal(ui.classes.has('locked'), true);
    assert.equal(ui.inputs.contact_name.dataset.originalValue, 'New contact');
});

test('Undo restores contact name, clears dirty state and locks without saving', () => {
    const ui = editableRow();
    ui.api.unlockRow(ui.row);
    ui.inputs.contact_name.value = 'Changed contact';
    ui.api.markDirty(ui.row);
    ui.classes.add('invalid');
    ui.api.undoRowEdits(ui.row);
    assert.equal(ui.inputs.contact_name.value, 'Alex');
    assert.equal(ui.classes.has('locked'), true);
    assert.equal(ui.classes.has('dirty'), false);
    assert.equal(ui.classes.has('invalid'), false);
    assert.equal(ui.inputs.contact_name.disabled, true);
    assert.equal(ui.requests.length, 0);
});
