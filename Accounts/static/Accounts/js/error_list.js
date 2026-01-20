import {_invoke_rest_api} from "./common.js";

function foreach(array, callback) {
    for (let i = 0; i < array.length; i++) {
        callback(array[i], i);
    }
}

function _set_category_change_event() {
    const category_element = document.querySelectorAll("div#details table#id_transactions tr.row td.category select.category");
    foreach(category_element, function(element) {
        element.addEventListener("change", function(element) {
            const row = element.target.parentElement.parentElement;
            const category = element.target.value;
            const id = row.getAttribute("id");
            const tx_id = id.split("_")[1];
            _invoke_rest_api("edit_transaction", tx_id, csrf_token, {category: category}, function(response) {
                row.querySelector("td.category").innerText = category;
            });
        });
    })
}

function _set_upload_history_selected_event() {
    /** Set change listener on the Upload pull down **/
    const upload_element = document.getElementById("id_upload")
    if (upload_element == null)
        return;
    upload_element.addEventListener("change", function() {
        const account_element = document.getElementById("id_account")
        const account = account_element.value;
        if (account == null || account.trim() === "")
            return;
        const upload = upload_element.value;
        if (upload == null || upload.trim() === "")
            return;
        window.location.href = `/Account/uploadErrors/${account}/${upload}/`;
        });
}

function _set_account_selected_event() {
    /** Set change listener on the Account pull down **/
    const account_element = document.getElementById("id_account")
    account_element.addEventListener("change", function() {
        const account = account_element.value;
        if (account == null || account.trim() === "")
            return;
        window.location.href = `/Account/uploadErrors/${account}/`;
        });
}

function _on_load() {
    _set_account_selected_event();
    _set_upload_history_selected_event();
    _set_category_change_event();
}

const script_tag = document.querySelector('script[src$="error_list.js"]');
const csrf_token = script_tag.getAttribute("csrf");

document.addEventListener('DOMContentLoaded', _on_load);
