const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../static/Contributors/js/contributor_contributions.js'), 'utf8');
function element(extra = {}) {
    return Object.assign({listeners: {}, value: '', textContent: '', disabled: false,
        addEventListener(type, callback) {this.listeners[type] = callback;}}, extra);
}
function setup() {
    const list = element({innerHTML: 'Old gifts'});
    const details = element({querySelector: () => list, dispatchEvent(event) {this.lastEvent = event;}});
    const sponsorDialog = element();
    const sponsorLists = [element({innerHTML: 'Sponsor one gifts'}), element({innerHTML: 'Sponsor two gifts'})];
    const dialog = element({open: false, showModal() {this.open = true;}, close() {this.open = false;}});
    const gift = element({focus() {this.focused = true;}});
    const cash = element({checked: false});
    const eventInput = element();
    const cancel = element();
    const save = element();
    const another = element();
    const form = element({attributes: {}, action: {toString: () => '[object RadioNodeList]'},
        setAttribute(name, value) {this.attributes[name] = value;},
        getAttribute(name) {return this.attributes[name];},
        reset() {gift.value = ''; cash.checked = false;},
        querySelectorAll: () => [cancel, save, another], querySelector: () => ({value: 'csrf-token'})});
    const error = element();
    const status = element();
    const nodes = {'#contributor-details-dialog': details, '#spreadsheet-modal-dialog': sponsorDialog, '#contribution-dialog': dialog,
        '#contribution-form': form, '#contribution-gift': gift, '#contribution-cash': cash,
        '#contribution-event': eventInput, '#contribution-error': error, '#contribution-status': status,
        '#contribution-cancel': cancel, '#contribution-contributor': element()};
    const document = element({readyState: 'loading', querySelector: selector => nodes[selector]});
    const button = {closest: () => null, dataset: {contributionUrl: '/contributions/7/', eventId: '23', contributorName: 'Oak'}};
    const requests = [];
    const context = {document, Object,
        CustomEvent: class {constructor(type) {this.type = type;}},
        FormData: class {constructor() {this.gift = gift.value; this.cash = cash.checked; this.event_id = eventInput.value;}},
        fetch: async (url, options) => {
            requests.push({url, options});
            return {ok: true, json: async () => ({ok: true, contributions_html: 'Updated gifts',
                sponsor_contributions_html: 'Updated sponsor gifts'})};
        }};
    vm.runInNewContext(source, context);
    document.listeners.DOMContentLoaded();
    return {context, requests, list, sponsorLists, dialog, gift, cash, eventInput, cancel, save, another, error, status,
        openSponsor: index => sponsorDialog.listeners.click({target: {closest: () => ({
            closest: () => sponsorLists[index],
            dataset: {contributionUrl: `/contributions/${index + 7}/`, eventId: '23', contributorName: `Sponsor ${index}`},
        })}}),
        open: () => details.listeners.click({target: {closest: () => button}}),
        submit: (value = 'Save') => form.listeners.submit({preventDefault() {}, submitter: {value}})};
}

test('opens contribution modal for selected contributor and event', () => {
    const ui = setup(); ui.open();
    assert.equal(ui.dialog.open, true);
    assert.equal(ui.eventInput.value, '23');
    assert.equal(ui.gift.focused, true);
    assert.equal(ui.requests.length, 0);
});

test('saving from confirmation updates only the selected sponsors contributions', async () => {
    const ui = setup(); ui.openSponsor(1); ui.gift.value = 'Voucher';
    await ui.submit('Save and Add another');
    assert.equal(ui.requests[0].url, '/contributions/8/');
    assert.equal(ui.requests[0].options.body.event_id, '23');
    assert.equal(ui.sponsorLists[1].innerHTML, 'Updated sponsor gifts');
    assert.equal(ui.sponsorLists[0].innerHTML, 'Sponsor one gifts');
    assert.equal(ui.list.innerHTML, 'Old gifts');
    assert.equal(ui.dialog.open, true);
});

test('Save persists cash and description, refreshes contributions and closes', async () => {
    const ui = setup(); ui.open(); ui.gift.value = 'Cash sponsorship'; ui.cash.checked = true;
    await ui.submit();
    const request = ui.requests[0];
    assert.equal(request.url, '/contributions/7/');
    assert.equal(request.options.method, 'POST');
    assert.equal(request.options.headers['X-CSRFToken'], 'csrf-token');
    assert.equal(request.options.body.gift, 'Cash sponsorship');
    assert.equal(request.options.body.cash, true);
    assert.equal(request.options.body.event_id, '23');
    assert.equal(ui.list.innerHTML, 'Updated gifts');
    assert.equal(ui.dialog.open, false);
});

test('Save buttons named action do not replace the contribution endpoint URL', async () => {
    const ui = setup(); ui.openSponsor(0); ui.gift.value = 'Gift voucher';
    await ui.submit();
    assert.equal(ui.requests[0].url, '/contributions/7/');
    assert.equal(ui.requests[0].options.body.gift, 'Gift voucher');
    assert.equal(ui.requests[0].options.body.cash, false);
    assert.equal(ui.sponsorLists[0].innerHTML, 'Updated sponsor gifts');
    assert.equal(ui.dialog.open, false);
});

test('Save and Add another keeps modal open, clears fields and allows another save', async () => {
    const ui = setup(); ui.open(); ui.gift.value = 'First'; ui.cash.checked = true;
    await ui.submit('Save and Add another');
    assert.equal(ui.dialog.open, true);
    assert.equal(ui.gift.value, '');
    assert.equal(ui.cash.checked, false);
    assert.equal(ui.eventInput.value, '23');
    assert.match(ui.status.textContent, /Contribution saved/);
    ui.gift.value = 'Second'; await ui.submit();
    assert.equal(ui.requests.length, 2);
    assert.equal(ui.requests[1].options.body.gift, 'Second');
});

test('Cancel closes without saving', () => {
    const ui = setup(); ui.open(); ui.cancel.listeners.click();
    assert.equal(ui.dialog.open, false);
    assert.equal(ui.requests.length, 0);
});

test('HTML server error reports HTTP status and retains the contribution', async () => {
    const ui = setup(); ui.open(); ui.gift.value = 'Voucher';
    ui.context.fetch = async () => ({status: 500, ok: false, json: async () => {throw new Error('HTML response');}});
    await ui.submit();
    assert.match(ui.error.textContent, /HTTP 500/);
    assert.match(ui.error.textContent, /save could not be verified/);
    assert.equal(ui.gift.value, 'Voucher');
    assert.equal(ui.dialog.open, true);
});

test('network failure explains uncertainty instead of claiming no save', async () => {
    const ui = setup(); ui.open();
    ui.context.fetch = async () => {throw new Error('Connection lost');};
    await ui.submit();
    assert.match(ui.error.textContent, /Could not connect/);
    assert.match(ui.error.textContent, /save could not be verified/);
});

test('login redirect tells the user to sign in again', async () => {
    const ui = setup(); ui.open();
    ui.context.fetch = async () => ({redirected: true, status: 200});
    await ui.submit();
    assert.match(ui.error.textContent, /Sign in again/);
});

test('browser update failure makes clear the contribution was already saved', async () => {
    const ui = setup(); ui.openSponsor(0);
    Object.defineProperty(ui.sponsorLists[0], 'innerHTML', {set() {throw new Error('Cannot update list');}});
    await ui.submit();
    assert.equal(ui.requests.length, 1);
    assert.match(ui.error.textContent, /contribution was saved/);
    assert.equal(ui.dialog.open, true);
});

test('cash checkbox switches between pounds amount and description entry', () => {
    const ui = setup(); ui.open();
    assert.equal(ui.gift.inputMode, 'text');
    ui.cash.checked = true;
    ui.cash.listeners.change();
    assert.equal(ui.gift.inputMode, 'decimal');
    assert.equal(ui.gift.placeholder, '£0.00');
    assert.equal(ui.gift.rows, 1);
    ui.cash.checked = false;
    ui.cash.listeners.change();
    assert.equal(ui.gift.inputMode, 'text');
    assert.equal(ui.gift.rows, 3);
});

test('failed save retains the cash flag and description for retry', async () => {
    const ui = setup(); ui.open(); ui.gift.value = 'Draft'; ui.cash.checked = true;
    ui.context.fetch = async () => ({ok: false, json: async () => ({ok: false,
        errors: {gift: [{message: 'Invalid description'}]}})});
    await ui.submit('Save and Add another');
    assert.equal(ui.dialog.open, true);
    assert.equal(ui.gift.value, 'Draft');
    assert.equal(ui.cash.checked, true);
    assert.equal(ui.error.textContent, 'Invalid description');
    assert.equal(ui.save.disabled, false);
});

test('pending save prevents duplicate submissions and modal dismissal', async () => {
    const ui = setup(); ui.open();
    let resolve; let calls = 0;
    ui.context.fetch = () => {calls++; return new Promise(done => {resolve = done;});};
    const pending = ui.submit();
    assert.equal(ui.cancel.disabled, true);
    let prevented = false;
    ui.dialog.listeners.cancel({preventDefault() {prevented = true;}});
    assert.equal(prevented, true);
    await ui.submit(); assert.equal(calls, 1);
    resolve({ok: true, json: async () => ({ok: true, contributions_html: 'Updated gifts'})});
    await pending;
    assert.equal(ui.cancel.disabled, false);
});
