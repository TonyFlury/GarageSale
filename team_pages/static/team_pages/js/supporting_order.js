"use strict";
document.querySelectorAll(".supporting-picker").forEach((picker) => {
    function updateButtons() {
        const rows = [...picker.querySelectorAll("li")];
        rows.forEach((row, index) => {
            const up = row.querySelector('[data-move="up"]');
            const down = row.querySelector('[data-move="down"]');
            if (up) up.disabled = index === 0;
            if (down) down.disabled = index === rows.length - 1;
        });
    }
    picker.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-move]");
        if (!button) return;
        const row = button.closest("li");
        if (button.dataset.move === "up" && row.previousElementSibling) {
            row.parentElement.insertBefore(row, row.previousElementSibling);
        } else if (button.dataset.move === "down" && row.nextElementSibling) {
            row.parentElement.insertBefore(row.nextElementSibling, row);
        }
        updateButtons();
        if (button.disabled) row.querySelector('input[type="checkbox"]').focus();
        else button.focus();
    });
    updateButtons();
});
