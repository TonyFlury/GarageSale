const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, '../../static/Contributors/js/contributor_modal.js'), 'utf8');

test('view-provided dialog opens and close button dismisses it', () => {
    let opened = false;
    let onClose;
    const dialog = {
        showModal() { opened = true; },
        close() { opened = false; },
        querySelector() { return {addEventListener(type, handler) { onClose = handler; }}; },
    };
    vm.runInNewContext(script, {document: {readyState: 'complete', querySelector: () => dialog}});
    assert.equal(opened, true);
    onClose();
    assert.equal(opened, false);
});

test('missing fragment leaves the page alone', () => {
    vm.runInNewContext(script, {document: {readyState: 'complete', querySelector: () => null}});
});
