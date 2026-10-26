(function () {
    'use strict';
    function initialise() {
        const board = document.querySelector('#contribution-board');
        if (!board || board.dataset.canEdit !== 'true') return;
        const columns = Array.from(board.querySelectorAll('.contribution-column'));
        const items = new Map(Array.from(board.querySelectorAll('.contribution-item')).map(item => [Number(item.dataset.id), item]));
        const status = board.querySelector('#contribution-board-status');
        const error = board.querySelector('#contribution-board-error');
        const reload = board.querySelector('#contribution-board-reload');
        let saving = false;
        let blocked = false;
        let dragged = null;
        const marker = document.createElement('li');
        marker.className = 'contribution-drop-marker';
        marker.setAttribute('aria-hidden', 'true');
        function snapshot() {
            return Object.fromEntries(columns.map(column => [column.dataset.classification,
                Array.from(column.querySelectorAll('.contribution-item')).map(item => Number(item.dataset.id))]));
        }
        function restore(previous) {
            for (const column of columns) {
                const list = column.querySelector('.contribution-items');
                for (const id of previous[column.dataset.classification]) list.append(items.get(id));
            }
        }
        function refresh() {
            for (const column of columns) {
                const classification = column.dataset.classification;
                const rows = Array.from(column.querySelectorAll('.contribution-item'));
                column.querySelector('.contribution-count').textContent = rows.length;
                column.querySelector('.contribution-empty').hidden = rows.length > 0;
                rows.forEach((item, index) => {
                    item.draggable = !saving && !blocked;
                    const position = item.querySelector('.prize-number');
                    position.hidden = classification !== 'prize_draw';
                    position.textContent = index + 1;
                    const select = item.querySelector('.contribution-move');
                    select.value = classification;
                    select.disabled = saving || blocked;
                    item.querySelector('.prize-order-controls').hidden = classification !== 'prize_draw';
                    item.querySelector('.prize-up').disabled = saving || blocked || index === 0;
                    item.querySelector('.prize-down').disabled = saving || blocked || index === rows.length - 1;
                });
            }
            document.querySelectorAll('.contribution-event-form select, .contribution-event-form button').forEach(control => {
                control.disabled = saving;
            });
        }
        async function persist(previous) {
            const arranged = snapshot();
            if (JSON.stringify(previous) === JSON.stringify(arranged)) { refresh(); return; }
            const focused = document.activeElement;
            saving = true;
            refresh();
            board.setAttribute('aria-busy', 'true');
            error.textContent = '';
            status.textContent = 'Saving arrangement…';
            try {
                const response = await fetch(board.dataset.saveUrl, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', 'Accept': 'application/json',
                        'X-CSRFToken': board.querySelector('[name="csrfmiddlewaretoken"]').value},
                    body: JSON.stringify({columns: arranged, revision: board.dataset.revision}),
                });
                if (response.redirected) throw new Error('Your session may have expired. Sign in again and reload this board.');
                let data;
                try { data = await response.json(); }
                catch (_) { throw new Error('The save could not be confirmed. Reload the board before making another move.'); }
                if (!response.ok || !data.ok) throw new Error(data.message || 'The arrangement could not be saved. Reload to get the latest board.');
                board.dataset.revision = data.revision;
                status.textContent = 'Arrangement saved.';
            } catch (failure) {
                restore(previous);
                blocked = true;
                status.textContent = 'Previous arrangement restored on this page.';
                error.textContent = failure.message || 'Connection failed. Reload the board to check whether the move was saved.';
                reload.hidden = false;
            } finally {
                saving = false;
                board.setAttribute('aria-busy', 'false');
                refresh();
                if (!blocked && focused && board.contains(focused)) {
                    const nextFocus = focused.disabled ? focused.closest('.contribution-item')?.querySelector('.contribution-move') : focused;
                    nextFocus?.focus();
                }
            }
        }
        function move(item, destination, before = null) {
            if (saving || blocked) return;
            const previous = snapshot();
            if (before === item) return;
            destination.insertBefore(item, before);
            return persist(previous);
        }
        board.addEventListener('change', event => {
            const select = event.target.closest('.contribution-move');
            if (!select) return;
            const column = columns.find(column => column.dataset.classification === select.value);
            if (column) move(select.closest('.contribution-item'), column.querySelector('.contribution-items'));
        });
        board.addEventListener('click', event => {
            const button = event.target.closest('.prize-up, .prize-down');
            if (!button || saving || blocked) return;
            const item = button.closest('.contribution-item');
            if (item.closest('.contribution-column').dataset.classification !== 'prize_draw') return;
            if (button.classList.contains('prize-up') && item.previousElementSibling) move(item, item.parentElement, item.previousElementSibling);
            if (button.classList.contains('prize-down') && item.nextElementSibling) move(item, item.parentElement, item.nextElementSibling.nextElementSibling);
        });
        board.addEventListener('dragstart', event => {
            if (saving || blocked || event.target.closest('select, button, label')) { event.preventDefault(); return; }
            dragged = event.target.closest('.contribution-item');
            if (!dragged) return;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', dragged.dataset.id);
            dragged.classList.add('is-dragging');
        });
        board.addEventListener('dragover', event => {
            if (!dragged || saving || blocked) return;
            const column = event.target.closest('.contribution-column');
            if (!column) return;
            event.preventDefault();
            event.dataTransfer.dropEffect = 'move';
            columns.forEach(item => item.classList.toggle('is-drop-target', item === column));
            const list = column.querySelector('.contribution-items');
            const rows = Array.from(list.querySelectorAll('.contribution-item')).filter(item => item !== dragged);
            const before = rows.find(item => event.clientY < item.getBoundingClientRect().top + item.getBoundingClientRect().height / 2);
            list.insertBefore(marker, before || null);
        });
        function clearDrag() {
            marker.remove();
            dragged?.classList.remove('is-dragging');
            dragged = null;
            columns.forEach(column => column.classList.remove('is-drop-target'));
        }
        board.addEventListener('drop', event => {
            if (!dragged || saving || blocked) return;
            const column = event.target.closest('.contribution-column');
            if (!column) return;
            event.preventDefault();
            const list = column.querySelector('.contribution-items');
            const before = marker.parentElement === list ? marker.nextElementSibling : null;
            const item = dragged;
            clearDrag();
            move(item, list, before);
        });
        board.addEventListener('dragend', clearDrag);
        reload.addEventListener('click', () => window.location.reload());
        window.addEventListener('beforeunload', event => { if (saving) { event.preventDefault(); event.returnValue = ''; } });
        refresh();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialise);
    else initialise();
})();
