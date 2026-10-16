const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../static/Contributors/js/contributor_details.js'), 'utf8');
function element(extra = {}) {
    return Object.assign({listeners: {}, dataset: {}, hidden: false, disabled: false, textContent: '',
        addEventListener(type, callback) {this.listeners[type] = callback;}}, extra);
}
function setup() {
    const input = element({value: 'Oak', focus() {}});
    const fieldError = element({dataset: {detailsError: 'contributor_name'}});
    const contributions = element({innerHTML: 'Initial contributions'});
    const addContribution = element();
    const fields = element({querySelector: selector => selector === '.socials-data' ? null : (selector === '#details-contributions' ? contributions : input), querySelectorAll: selector => {
        if (selector === '[data-details-error]') return [fieldError];
        if (selector === '.add-contribution') return [addContribution];
        if (selector === '.details-help') return [];
        if (selector === '.social-edit-action' || selector === '.social-pair') return [];
        return [input];
    }});
    let html = '';
    Object.defineProperty(fields, 'innerHTML', {get: () => html, set: value => {
        html = value; input.value = 'Oak'; contributions.innerHTML = 'Initial contributions';
    }});
    const row = {dataset: {contributorId: '7'}};
    const button = {dataset: {detailsUrl: '/details/7/'}, closest: () => row};
    const sheet = element({events: [], dispatchEvent(event) {this.events.push(event);}});
    const dialog = element({open: false, showModal() {this.open = true;}, close() {this.open = false;}});
    const form = element({querySelector: () => ({value: 'csrf-token'})});
    const names = ['edit', 'save', 'cancel', 'close', 'error', 'history'];
    const nodes = {'#contributor-sheet': sheet, '#contributor-details-dialog': dialog,
        '#contributor-details-form': form, '#contributor-details-fields': fields,
        '#details-add-contact-history': element()};
    for (const name of names) nodes[`#contributor-details-${name}`] = element();
    const document = element({readyState: 'loading', querySelector: selector => nodes[selector]});
    const requests = [];
    const context = {document, console, Array, Object,
        CustomEvent: class {constructor(type, options) {this.type = type; this.detail = options.detail;}},
        FormData: class {constructor() {this.name = input.value;}},
        fetch: async (url, options) => {
            requests.push({url, options});
            return {ok: true, json: async () => ({ok: true, can_edit: true, can_contact: true, html: '<input>', history_html: 'Latest history',
                contributor_id: 7, contact_history_url: '/contact/7/', contributor: {id: 7}})};
        }};
    vm.runInNewContext(source, context);
    document.listeners.DOMContentLoaded();
    return {nodes, context, requests, input, fieldError, row, sheet, dialog, form, fields, contributions, addContribution,
        open: () => sheet.listeners.click({target: {closest: () => button}}),
        edit: () => nodes['#contributor-details-edit'].listeners.click(),
        submit: () => form.listeners.submit({preventDefault() {}})};
}

test('details opens read-only, shows history and contact action, then Edit enables fields', async () => {
    const ui = setup();
    await ui.open();
    assert.equal(ui.dialog.open, true);
    assert.equal(ui.input.disabled, true);
    assert.equal(ui.form.dataset.editing, 'false');
    assert.equal(ui.nodes['#contributor-details-save'].hidden, true);
    assert.equal(ui.nodes['#contributor-details-edit'].hidden, false);
    assert.equal(ui.nodes['#contributor-details-history'].innerHTML, 'Latest history');
    const contact = ui.nodes['#details-add-contact-history'];
    assert.equal(contact.hidden, false);
    assert.equal(contact.dataset.contactHistoryUrl, '/contact/7/');
    assert.equal(contact.dataset.contributorId, 7);
    ui.edit();
    assert.equal(ui.form.dataset.editing, 'true');
    assert.equal(ui.input.disabled, false);
    assert.equal(ui.nodes['#contributor-details-save'].hidden, false);
    assert.equal(contact.hidden, false);
    assert.equal(ui.nodes['#contributor-details-close'].hidden, false);
});

test('Cancel restores original details and returns to read-only without posting', async () => {
    const ui = setup();
    await ui.open(); ui.edit(); ui.input.value = 'Draft';
    ui.nodes['#contributor-details-cancel'].listeners.click();
    assert.equal(ui.input.value, 'Oak');
    assert.equal(ui.input.disabled, true);
    assert.equal(ui.requests.length, 1);
});

test('Save posts form data with CSRF and sends updated contributor to the spreadsheet', async () => {
    const ui = setup();
    await ui.open(); ui.edit(); ui.input.value = 'Revised';
    await ui.submit();
    const request = ui.requests[1];
    assert.equal(request.options.method, 'POST');
    assert.equal(request.options.body.name, 'Revised');
    assert.equal(request.options.headers['X-CSRFToken'], 'csrf-token');
    assert.equal(ui.sheet.events[0].type, 'contributor-details-saved');
    assert.equal(ui.sheet.events[0].detail.row, ui.row);
    assert.equal(ui.dialog.open, false);
});

test('validation errors keep edits and dialog open', async () => {
    const ui = setup();
    await ui.open(); ui.edit(); ui.input.value = 'Draft';
    ui.context.fetch = async () => ({ok: false, json: async () => ({ok: false,
        errors: {contributor_name: [{message: 'Invalid name'}]}})});
    await ui.submit();
    assert.equal(ui.dialog.open, true);
    assert.equal(ui.input.value, 'Draft');
    assert.equal(ui.fieldError.textContent, 'Invalid name');
    assert.equal(ui.nodes['#contributor-details-save'].disabled, false);
});

test('recording a contact refreshes history in both modes without resetting edits', async () => {
    for (const editing of [false, true]) {
        const ui = setup();
        await ui.open();
        if (editing) {ui.edit(); ui.input.value = 'Draft';}
        ui.context.fetch = async (url) => {
            assert.equal(url, '/details/7/?history=1');
            return {ok: true, json: async () => ({ok: true, history_html: 'New contact first'})};
        };
        await ui.sheet.listeners['contact-history-saved']({detail: {row: ui.row}});
        assert.equal(ui.nodes['#contributor-details-history'].innerHTML, 'New contact first');
        assert.equal(ui.input.value, editing ? 'Draft' : 'Oak');
        assert.equal(ui.input.disabled, !editing);
    }
});

test('Close is available in both modes and does not post', async () => {
    for (const editing of [false, true]) {
        const ui = setup();
        await ui.open(); if (editing) ui.edit();
        ui.nodes['#contributor-details-close'].listeners.click();
        assert.equal(ui.dialog.open, false);
        assert.equal(ui.requests.length, 1);
    }
});

test('Add contribution remains enabled in read-only and editing modes', async () => {
    const ui = setup();
    await ui.open();
    assert.equal(ui.addContribution.disabled, false);
    ui.edit();
    assert.equal(ui.addContribution.disabled, false);
});

test('spreadsheet class flag is sent when requesting details', async () => {
    for (const [setting, expected] of [['false', '0'], ['true', '1']]) {
        const ui = setup();
        ui.sheet.dataset.showContributions = setting;
        await ui.open();
        assert.equal(ui.requests[0].url, `/details/7/?show_contributions=${expected}&data_label=Contributor`);
    }
});

test('canceling contributor edits preserves newly saved contributions', async () => {
    const ui = setup();
    await ui.open(); ui.edit(); ui.input.value = 'Draft';
    ui.contributions.innerHTML = 'Newly saved contributions';
    ui.nodes['#contributor-details-cancel'].listeners.click();
    assert.equal(ui.input.value, 'Oak');
    assert.equal(ui.contributions.innerHTML, 'Newly saved contributions');
});

function setSocialRows(ui, rows, initial = '{}') {
    const data = {value: initial};
    const originalQuery = ui.fields.querySelector;
    const originalQueries = ui.fields.querySelectorAll;
    ui.fields.querySelector = selector => selector === '.socials-data' ? data : originalQuery(selector);
    ui.fields.querySelectorAll = selector => selector === '.social-pair' ? rows : originalQueries(selector);
    return data;
}

function socialPair(key, value, originalValue) {
    return {dataset: originalValue === undefined ? {} : {originalText: value, originalValue},
        querySelector: selector => ({value: selector === '.social-key' ? key : value})};
}

test('social grid saves key/value edits and preserves unchanged non-string values', async () => {
    const ui = setup(); await ui.open(); ui.edit();
    const data = setSocialRows(ui, [socialPair('Website', 'https://new.example.com'), socialPair('Count', '3', '3')]);
    await ui.submit();
    assert.deepEqual(JSON.parse(data.value), {Website: 'https://new.example.com', Count: 3});
    assert.equal(ui.requests.length, 2);
});

test('duplicate social keys block save with a helpful error', async () => {
    const ui = setup(); await ui.open(); ui.edit();
    setSocialRows(ui, [socialPair('Website', 'one'), socialPair('Website', 'two')]);
    await ui.submit();
    assert.equal(ui.requests.length, 1);
    assert.match(ui.nodes['#contributor-details-error'].textContent, /unique site/);
    assert.equal(ui.dialog.open, true);
});

test('empty social grid preserves null or removes all existing entries', async () => {
    for (const [initial, expected] of [['null', null], ['{"Website":"old"}', {}]]) {
        const ui = setup(); await ui.open(); ui.edit();
        const data = setSocialRows(ui, [], initial);
        await ui.submit();
        assert.deepEqual(JSON.parse(data.value), expected);
    }
});

test('contribution changes refresh event history without resetting edited fields', async () => {
    const ui = setup();
    await ui.open();
    ui.edit();
    ui.input.value = 'Pending edit';
    ui.context.fetch = async url => {
        assert.equal(url, '/details/7/?history=1');
        return {ok: true, json: async () => ({ok: true, history_html: 'Updated event contributions'})};
    };
    await ui.dialog.listeners['contributions-changed']();
    assert.equal(ui.nodes['#contributor-details-history'].innerHTML, 'Updated event contributions');
    assert.equal(ui.input.value, 'Pending edit');
});
