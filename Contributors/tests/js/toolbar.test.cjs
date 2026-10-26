const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '../../static/Contributors/js/contributor_toolbar.js'), 'utf8');

test('selection updates required actions and submits current selected IDs', () => {
    let selected = [];
    const required = {disabled: false};
    const always = {disabled: false};
    const events = {};
    const hidden = [];
    const form = {
        querySelectorAll(selector) {
            return selector === '[data-requires-selection]' ? [required] : hidden.slice();
        },
        addEventListener(type, callback) { events[type] = callback; },
        appendChild(input) { hidden.push(input); },
    };
    const sheet = {
        querySelectorAll() { return selected; },
        addEventListener(type, callback) { events.change = callback; },
    };
    vm.runInNewContext(script, {
        window: {addEventListener(type, callback) { events[type] = callback; }},
        document: {
            readyState: 'complete',
            querySelector(selector) { return selector === '#contributor-sheet' ? sheet : form; },
            querySelectorAll() { return [{addEventListener(type, callback) { events.search = callback; }}]; },
            createElement() { return {remove() { hidden.splice(hidden.indexOf(this), 1); }}; },
        },
    });
    assert.equal(required.disabled, true);
    assert.equal(always.disabled, false);
    selected = [{value: '7'}, {value: '8'}];
    events.change();
    assert.equal(required.disabled, false);
    events.submit({submitter: {hasAttribute: () => true}});
    assert.deepEqual(hidden.map(input => input.value), ['7', '8']);
    selected = [{value: '8'}];
    events.submit({submitter: {hasAttribute: () => false}});
    assert.deepEqual(hidden.map(input => input.value), ['8']);
    selected = [];
    events.search();
    assert.equal(required.disabled, true);
    let prevented = false;
    events.submit({submitter: {hasAttribute: () => true}, preventDefault() { prevented = true; }});
    assert.equal(prevented, true);
    assert.equal(always.disabled, false);
});
