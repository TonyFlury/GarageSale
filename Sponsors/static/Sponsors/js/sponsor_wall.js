(function () {
    'use strict';
    function initialiseSponsorWall() {
        const wall = document.querySelector('#sponsor-logo-wall');
        if (!wall || typeof layoutLogos !== 'function') return;
        const tiles = Array.from(wall.querySelectorAll('.sponsor-wall-tile'));
        if (!tiles.length) return;
        let previousWidth = 0;
        let frame;
        function render() {
            const width = wall.clientWidth;
            if (!width) return;
            const columns = width < 450 ? 4 : width < 750 ? 8 : 12;
            const gap = 6;
            const cellWidth = (width - (columns - 1) * gap) / columns;
            const cellHeight = columns === 4 ? 36 : 30;
            const sponsors = tiles.map(tile => {
                const image = tile.querySelector('img');
                return {
                    id: tile.dataset.sponsorId,
                    headline: tile.dataset.headline === 'true',
                    ratio: image && image.naturalWidth && image.naturalHeight ? image.naturalWidth / image.naturalHeight : 2,
                };
            });
            const layout = layoutLogos(sponsors, columns, cellWidth, cellHeight, Number(wall.dataset.eventId) || 1);
            wall.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
            wall.style.gridTemplateRows = `repeat(${layout.rows}, ${cellHeight}px)`;
            const positions = new Map(layout.items.map(item => [item.id, item]));
            for (const tile of tiles) {
                const position = positions.get(tile.dataset.sponsorId);
                tile.style.gridColumn = `${position.x + 1} / span ${position.w}`;
                tile.style.gridRow = `${position.y + 1} / span ${position.h}`;
            }
            wall.classList.add('is-laid-out');
            previousWidth = width;
        }
        function scheduleRender() {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(render);
        }
        for (const tile of tiles) {
            const image = tile.querySelector('img');
            if (image) {
                image.addEventListener('load', scheduleRender);
                image.addEventListener('error', () => {
                    image.hidden = true;
                    tile.querySelector('.sponsor-wall-name').hidden = false;
                    scheduleRender();
                });
                if (image.complete && !image.naturalWidth) {
                    image.hidden = true;
                    tile.querySelector('.sponsor-wall-name').hidden = false;
                }
            }
            const details = document.getElementById(tile.dataset.detailsId);
            if (details && typeof details.showModal === 'function') {
                tile.addEventListener('click', event => {
                    event.preventDefault();
                    details.showModal();
                });
                details.querySelector('.sponsor-details-close').addEventListener('click', () => details.close());
            }
        }
        if (typeof ResizeObserver === 'function') {
            new ResizeObserver(() => {
                if (Math.abs(wall.clientWidth - previousWidth) > 1) scheduleRender();
            }).observe(wall);
        } else {
            window.addEventListener('resize', scheduleRender);
        }
        render();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialiseSponsorWall);
    else initialiseSponsorWall();
})();
