const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, '../../static/Contributors/js/contributor_filters.js'), 'utf8');

test('grouped checkbox clears only checked peers in the same group', () => {
    const options = [
        {checked: true, dataset: {filterGroup: 'email'}},
        {checked: true, dataset: {filterGroup: 'email'}},
        {checked: true, dataset: {filterGroup: 'phone'}},
        {checked: true, dataset: {}},
    ];
    let onChange;
    const form = {
        addEventListener(type, handler) { onChange = handler; },
        querySelectorAll() { return options; },
    };
    const node = {addEventListener() {}};
    vm.runInNewContext(script, {document: {
        readyState: 'complete',
        querySelector(selector) { return selector === '#spreadsheet-filter-form' ? form : node; },
    }});
    onChange({target: options[1]});
    assert.deepEqual(options.map(option => option.checked), [false, true, true, true]);

    options[0].checked = true;
    options[1].checked = false;
    onChange({target: options[1]});
    assert.equal(options[0].checked, true);
    onChange({target: options[3]});
    assert.equal(options[0].checked, true);
});

test('Clear unchecks every filter without submitting or closing the popup', () => {
    const options = [{checked: true}, {checked: false}, {checked: true}];
    let clearSelection;
    const form = {
        addEventListener() {},
        querySelectorAll(selector) {
            assert.equal(selector, 'input[name="selected_filters"]');
            return options;
        },
        reset() { throw new Error('Clear must not restore existing selections'); },
    };
    const node = {addEventListener() {}, close() { throw new Error('Clear must keep the popup open'); }};
    const clear = {addEventListener(type, handler) {assert.equal(type, 'click'); clearSelection = handler;}};
    vm.runInNewContext(script, {document: {
        readyState: 'complete',
        querySelector(selector) {
            if (selector === '#spreadsheet-filter-form') return form;
            if (selector === '#spreadsheet-filter-clear') return clear;
            return node;
        },
    }});
    clearSelection();
    assert.deepEqual(options.map(option => option.checked), [false, false, false]);
});
