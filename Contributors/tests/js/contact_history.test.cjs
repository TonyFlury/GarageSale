const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// Run the production script with a small DOM adapter; requests are intercepted.
const source = fs.readFileSync(path.join(__dirname, '../../static/Contributors/js/contributor_spreadsheet.js'), 'utf8');
function element(properties = {}) {
    return Object.assign({
        listeners: {}, dataset: {}, value: '', textContent: '', disabled: false,
        addEventListener(type, callback) { this.listeners[type] = callback; },
    }, properties);
}
function setup({date = '', cutoff = '', isNew = false, fromDetails = false} = {}) {
    const display = element({dataset: {date}, value: date ? '10/10/2026' : ''});
    const row = element({dataset: {isNew: isNew ? 'true' : undefined}});
    row.querySelector = selector => selector === '.last-contact-date' ? display : {value: 'Oak & Co.'};
    const button = element({dataset: {contactHistoryUrl: '/contributors/spreadsheet/7/contact-history/', contributorId: '7'},
        closest: () => fromDetails ? null : row});
    const icon = {closest: () => button};
    const dialog = element({open: false, showModal() {this.open = true;}, close() {this.open = false;}});
    const note = element({focus() {this.focused = true;}});
    const dateInput = element();
    const error = element();
    const save = element();
    const cancel = element();
    const csrf = {value: 'csrf-token'};
    const form = element({reset() {note.value = ''; dateInput.value = '';}, querySelector: () => csrf});
    const sheet = element({dataset: {historicEventDate: cutoff}, dispatchEvent() {}, querySelector: () => row});
    const nodes = {
        '#contributor-sheet': sheet, '#contact-history-dialog': dialog,
        '#contact-history-form': form, '#contact-history-error': error,
        '#contact-history-save': save, '#contact-history-cancel': cancel,
        '#contact-history-note': note, '#contact-history-date': dateInput,
        '#contact-history-contributor': element(),
        'section#toolbar button.search-icon': element(),
    };
    const document = element({readyState: 'loading', querySelector: selector => nodes[selector],
        querySelectorAll: () => [], getElementById: () => element()});
    const requests = [];
    const context = {document, window: {addEventListener() {}}, console, Date, CustomEvent: class {constructor(type, options) {this.type = type; this.detail = options.detail;}},
        FormData: class {constructor() {this.note = note.value; this.date = dateInput.value;}},
        fetch: async (url, options) => {
            requests.push({url, options});
            return {ok: true, json: async () => ({ok: true, contact_date: dateInput.value})};
        }};
    vm.runInNewContext(source, context);
    document.listeners.DOMContentLoaded();
    return {context, requests, nodes, dialog, form, note, dateInput, error, save, cancel, display,
        open() {document.listeners.click({target: icon});},
        submit() {return form.listeners.submit({preventDefault() {}});}};
}

test('clicking the row icon opens and resets the modal for the correct contributor', () => {
    const ui = setup();
    ui.note.value = 'Old draft';
    ui.error.textContent = 'Old error';
    ui.open();
    assert.equal(ui.dialog.open, true);
    assert.equal(ui.note.value, '');
    assert.equal(ui.note.focused, true);
    assert.equal(ui.error.textContent, '');
    assert.equal(ui.nodes['#contact-history-contributor'].textContent, 'Oak & Co.');
    assert.equal(ui.form.action, '/contributors/spreadsheet/7/contact-history/');
    assert.match(ui.dateInput.value, /^\d{4}-\d{2}-\d{2}$/);
    assert.equal(ui.requests.length, 0);
});

test('new rows cannot open the modal', () => {
    const ui = setup({isNew: true});
    ui.open();
    assert.equal(ui.dialog.open, false);
});

test('the details-modal contact icon opens the same contact dialog for its contributor', async () => {
    const ui = setup({fromDetails: true});
    ui.open();
    assert.equal(ui.dialog.open, true);
    assert.equal(ui.nodes['#contact-history-contributor'].textContent, 'Oak & Co.');
    ui.note.value = 'Contact from details';
    ui.dateInput.value = '2026-10-10';
    await ui.submit();
    assert.equal(ui.requests[0].options.body.note, 'Contact from details');
    assert.equal(ui.requests[0].url, '/contributors/spreadsheet/7/contact-history/');
});

test('cancel closes without saving', () => {
    const ui = setup();
    ui.open();
    ui.cancel.listeners.click();
    assert.equal(ui.dialog.open, false);
    assert.equal(ui.requests.length, 0);
});

test('explicit save posts the note, selected date and CSRF token and updates the displayed date', async () => {
    const ui = setup({cutoff: '2026-09-01'});
    ui.open();
    ui.note.value = 'Called about sponsorship';
    ui.dateInput.value = '2026-10-09';
    await ui.submit();
    assert.equal(ui.requests.length, 1);
    const request = ui.requests[0];
    assert.equal(request.url, ui.form.action);
    assert.equal(request.options.method, 'POST');
    assert.equal(request.options.headers['X-CSRFToken'], 'csrf-token');
    assert.equal(request.options.body.note, 'Called about sponsorship');
    assert.equal(request.options.body.date, '2026-10-09');
    assert.equal(ui.display.value, '09/10/2026');
    assert.equal(ui.display.dataset.date, '2026-10-09');
    assert.equal(ui.dialog.open, false);
    assert.equal(ui.save.disabled, false);
});

test('older contacts and dates on or before the historic event do not change the displayed date', async () => {
    for (const [date, cutoff, selected] of [
        ['2026-10-10', '2026-09-01', '2026-10-09'],
        ['', '2026-09-01', '2026-09-01'],
        ['', '2026-09-01', '2026-08-31'],
    ]) {
        const ui = setup({date, cutoff});
        ui.open();
        ui.dateInput.value = selected;
        const before = ui.display.value;
        await ui.submit();
        assert.equal(ui.display.value, before);
        assert.equal(ui.display.dataset.date, date);
    }
});

test('validation errors leave the modal open with its draft intact', async () => {
    const ui = setup();
    ui.context.fetch = async () => ({ok: false, json: async () => ({ok: false,
        errors: {note: [{message: 'This field is required.'}]}})});
    ui.open();
    ui.note.value = 'Draft';
    await ui.submit();
    assert.equal(ui.dialog.open, true);
    assert.equal(ui.note.value, 'Draft');
    assert.equal(ui.error.textContent, 'This field is required.');
    assert.equal(ui.cancel.disabled, false);
});

test('network failure leaves the draft available to retry', async () => {
    const ui = setup();
    ui.context.fetch = async () => {throw new Error('Offline');};
    ui.open();
    ui.note.value = 'Draft';
    await ui.submit();
    assert.equal(ui.dialog.open, true);
    assert.equal(ui.note.value, 'Draft');
    assert.match(ui.error.textContent, /Please try again/);
    assert.equal(ui.save.disabled, false);
});

test('pending saves prevent duplicate submissions and dismissal', async () => {
    const ui = setup();
    let resolve;
    let calls = 0;
    ui.context.fetch = () => {calls++; return new Promise(done => {resolve = done;});};
    ui.open();
    const pending = ui.submit();
    assert.equal(ui.save.disabled, true);
    assert.equal(ui.cancel.disabled, true);
    let prevented = false;
    ui.dialog.listeners.cancel({preventDefault() {prevented = true;}});
    assert.equal(prevented, true);
    await ui.submit();
    assert.equal(calls, 1);
    resolve({ok: true, json: async () => ({ok: true, contact_date: '2026-10-10'})});
    await pending;
    assert.equal(ui.save.disabled, false);
});
