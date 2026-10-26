const {test} = require('node:test');
const assert = require('node:assert/strict');
const {layoutLogos} = require('../../static/Sponsors/js/sponsor_wall_layout.js');

test('responsive walls place every sponsor without overlaps across counts, tiers, shapes and seeds', () => {
    for (const count of [1, 16, 18, 20]) for (const headliners of [0, 3, 4]) {
        for (const columns of [4, 8, 12]) for (const seed of [1, 42, 2027]) {
            const sponsors = Array.from({length: count}, (_, i) => ({
                id: String(i), headline: i < headliners, ratio: [.65, 1, 2, 4.8][i % 4],
            }));
            const result = layoutLogos(sponsors, columns, 80, 30, seed);
            assert.equal(result.items.length, count);
            const occupied = new Set();
            for (const item of result.items) {
                assert.ok(item.x >= 0 && item.y >= 0);
                assert.ok(item.x + item.w <= columns && item.y + item.h <= result.rows);
                for (let y = item.y; y < item.y + item.h; y++) for (let x = item.x; x < item.x + item.w; x++) {
                    const cell = `${x},${y}`;
                    assert.equal(occupied.has(cell), false);
                    occupied.add(cell);
                }
            }
            assert.deepEqual(layoutLogos(sponsors, columns, 80, 30, seed), result);
        }
    }
});

test('missing image dimensions and empty walls have safe results', () => {
    assert.deepEqual(layoutLogos([], 4, 80, 30), {columns: 4, rows: 0, items: []});
    const sponsors = [NaN, Infinity, 0, -1].map((ratio, id) => ({id, ratio, headline: false}));
    assert.equal(layoutLogos(sponsors, 4, 80, 30).items.length, 4);
});
