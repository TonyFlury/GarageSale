
    function _decimal2int(decimal_string) {
        /* Convert a decimal string to an integer */
        let parts = decimal_string.split(".");
        if (parts.length === 1)
            return parseInt(decimal_string)*100;
        else
            parts[1] = parts[1].padEnd(2, '0');
        return parseInt(decimal_string.split(".").join(''));
    }

    function _int2decimal(integer) {
        /* Convert an integer to a decimal string */
        return String(Math.floor(integer / 100) )+ "." + String(integer % 100).padStart(2, '0');
    }

    function _build_DOM_element(name, options) {
        /** build a DDOM element with the given name and options **/
       let element = document.createElement(name)
        for (let key in options) {
            element[key] = options[key];
        }
        return element;
    }

    function _invoke_rest_api( verb, object_id, data, callback) {
        /* Send a REST API request to the server */
        let request = new Request(`/Account/${verb}/${object_id}/`,
            {method: "PUT", headers: {"X-CSRFToken": csrf_token,
                "Content-Type": "application/json"},
            body: JSON.stringify(data)
            });

        fetch(request).
                then(response => {
                    if (!response.ok)
                        console.log("Error: " + response.statusText);
                    return response.json();
                }).
        then( response => {callback(object_id, response)}).catch(error => console.log(error));
    }

    function _revert_edit_on_child(row_element) {
        /* Discard any edits made to a child row */
        const table = document.getElementById("transactions");
            if (row_element.classList.contains("new")) {
                table.deleteRow(row_element.rowIndex);
                return;
            }
            let id = row_element.id;
            let parent_id = row_element.getAttribute("parent_id");
            let parent_row = document.getElementById(parent_id);
            let type = (parent_row.querySelector(".debit").innerText !== "")? "debit":"credit";

            let name_element = document.getElementById(id + "__name");
            let amount_element = document.getElementById(id + "__" + type);
            name_element.innerHTML = name_element.children[0].value;
            amount_element.innerHTML = amount_element.children[0].value;
            row_element.classList.remove("editing");
    }

    function _revert_edit_on_non_child(row_element) {
        /* Discard any edits made to a non-child row */
        let id = row_element.id
        let name_element = document.getElementById(id + "__name");
        let category_element = document.getElementById(id + "__category");
        name_element.innerHTML = name_element.children[0].value;
        category_element.innerHTML = category_element.children[0].value;
    }

    function revert_edit(row_element) {
        /* Revert any edits made to a row - invoked when the revert button is clicked*/
        row_element.classList.remove("editing");

        if (row_element.classList.contains("child"))
            _revert_edit_on_child(row_element);
        else
            _revert_edit_on_non_child(row_element);
    }

    function _child_edit_complete(id, response) {

        console.log(response)

        let row_element = document.getElementById(id);

        if (!row_element.classList.contains('child')) {
            row_element = document.getElementById(`${id}__new`);
            id = row_element.id;
        }

        const parent_id = row_element.getAttribute("parent_id");
        const parent_row = document.getElementById(parent_id);
        const type = (parent_row.querySelector(".debit").innerText !== "") ? "debit" : "credit";

        const name_element = document.getElementById(id + "__name_edit");
        const amount_element = document.getElementById(id + "__" + type + "_edit");

        name_element.parentElement.innerHTML = name_element.value;
        amount_element.parentElement.innerHTML = amount_element.value;

        let amount_max = _decimal2int(parent_row.getAttribute("remaining_" + type)) + _decimal2int(amount_element.defaultValue);

        /* Recalculate the remaining credit/debit on the parent row */
        let remaining = amount_max - _decimal2int(amount_element.value);
        parent_row.setAttribute("remaining_" + type, _int2decimal(remaining));

        /* Update the summary row */
        let summary_field = document.querySelector(`tr.child.summary[parent_id="${parent_row.id}"] td.col.${type}`)
        summary_field.innerText = _int2decimal(remaining);

        /* Delete the edit fields */
        name_element.remove()
        amount_element.remove()

        row_element.classList.remove("editing");

        /* A new transaction needs to be 'converted' into a child row
            More to do in this case - need to set the correct attributes
        * */
        if (row_element.classList.contains("new")) {

            row_element.classList.remove("new");
            row_element.classList.add("child");

            /* Record the id as returned by the server  and change the name and debit/credit cells*/
            row_element.id = response.id;
            name_element.id = `${row_element.id}__name`;
            amount_element.id = `${row_element.id}__${type}`;

            /* Set the event listeners on the edit and revert buttons so they can be edited later*/
            const edit_button = row_element.querySelector(".edit_button");
            edit_button.addEventListener("click", edit_transaction);
            edit_button.id = id + "__edit"

            const revert_button = row_element.querySelector(".revert_button");
            revert_button.id = id + "__revert"
            revert_button.addEventListener("click", function (event) {
                                revert_edit(event.target.parentElement)
                            })
        }
    }

    function _save_child_edit(row_element, parent_row) {
        /* Save any edits made to the row - invoked when the save button is clicked*/

        /* Is this a debit or credit split? */
        let type = (parent_row.querySelector(".debit").innerText !== "") ? "debit" : "credit";

        let name_element, amount_element;

        /* Find the edit elements */
        let verb = row_element.classList.contains("new")? "add_split" : "edit_split";
        let id = row_element.id;
        let object_id = row_element.classList.contains("new")? row_element.getAttribute("parent_id"): row_element.id;

        name_element = document.getElementById(id + "__name_edit");
        amount_element = document.getElementById(id + "__" + type + "_edit");

        /* Identify how much actually remains to be accounted for in this transaction  */
        let amount_max = _decimal2int(parent_row.getAttribute("remaining_" + type)) + _decimal2int(amount_element.defaultValue);

        /* Did the user enter an amount in range */
        let amount_input = _decimal2int(amount_element.value);
        if (amount_input > amount_max)
        {
            amount_element.setCustomValidity("Amount exceeds available balance");
            amount_element.reportValidity();
            return;
        }

        _invoke_rest_api(verb, object_id, {name: name_element.value, [type]: amount_element.value}, _child_edit_complete);
    }

    function _non_child_edit_complete(id, response) {
            let row_element = document.getElementById(id);
            let name_element = document.getElementById(id + "__name_edit");
            let category_element = document.getElementById(id + "__category_edit");
            name_element.parentElement.innerHTML = name_element.value;
            category_element.parentElement.innerHTML = category_element.value;
            row_element.classList.remove("editing");
            name_element.remove();
            category_element.remove();
        }

    function _save_non_child_edit(row_element) {
        /* Save any edits made to the row - invoked when the save button is clicked*/
        let id = row_element.id
        let name_element = document.getElementById(id + "__name_edit");
        let category_element = document.getElementById(id + "__category_edit");

        _invoke_rest_api("edit_transaction", id, {name: name_element.value, category: category_element.value}, _non_child_edit_complete);
    }

    function save_edit(row_element) {
        /* Save any edits made to the row - invoked when the save button is clicked*/
        if (!row_element.classList.contains("child"))
            _save_non_child_edit(row_element)
        else {
            let parent_id = row_element.getAttribute("parent_id");
            let parent_row = document.getElementById(parent_id);
            _save_child_edit(row_element, parent_row);
        }
    }

    function _edit_child(id, parent_row) {
        /** Allow editing of a child row - can change name and amount **/
        const name_element = document.getElementById(`${id}__name`);

        let type = (parent_row.querySelector(".debit").innerText !== "")? "debit":"credit";
        const amount_element = document.getElementById(`${id}__${type}`);

        let name = _build_DOM_element("input", { id : `${id}__name_edit`,
                                                type: "text",
                                                required: true,
                                                defaultValue: name_element.innerText,
                                                value: name_element.innerText});
        name_element.innerHTML = "";
        name_element.appendChild(name);

        let amount = _build_DOM_element("input", { id : `${id}__${type}_edit`, type:"text",
                                                    required: true,
                                                    defaultValue: amount_element.innerText,
                                                    value:amount_element.innerText});
        amount_element.innerHTML = "";
        amount_element.appendChild(amount);
    }

    function _create_child_row(parent_row) {
        /** Allow creation of a new child row **/
        const table = document.getElementById("transactions");

        let new_row = table.insertRow(parent_row.rowIndex+1)
        new_row.classList.add("child","row",'editing','expanded', 'new');
        new_row.setAttribute("parent_id", parent_row.id);
        new_row.id = `${parent_row.id}__new`;
        new_row.classList.add("editing");

        new_row.innerHTML = `<td class="col"></td><td class="col date"></td><td class="col name"></td><td class="col debit"></td><td class="col credit"></td><td class="col balance"></td><td class="col category"></td><td class='row_button edit_button'></td><td class='row_button revert_button'></td><td class='link_button'></td>`

        let type = (parent_row.querySelector(".debit").innerText !== "")? "debit":"credit";

        let name_element = _build_DOM_element("input", { id: `${parent_row.id}__new__name_edit`, type:"text",
                                                        required:true });
        let name_cell = new_row.querySelector('.col.name');
        name_cell.innerHTML = name_element.outerHTML;

        let amount_element = _build_DOM_element("input", { id: `${parent_row.id}__new__${type}_edit`, type:"text", required:true,
                                                            defaultValue: "0.00"});
        amount_element.classList.add(type);
        new_row.querySelector(`.${type}`).innerHTML = amount_element.outerHTML;

        /* Need to set the save and revert buttons */
        let edit_button = new_row.querySelector(".edit_button");
        edit_button.addEventListener("click", edit_transaction);

        let revert_button = new_row.querySelector(".revert_button");
        revert_button.addEventListener("click", function(event) {revert_edit(event.target.parentElement)});
    }


    function _edit_non_child(row_id) {
        /** Specific editing of a non-child row - can change name and category **/
        const name_element = document.getElementById(row_id + "__name");
        const category_element = document.getElementById(row_id + "__category");

        let name = _build_DOM_element("input", { id : `${row_id}__name_edit`,
                                                type: "text",
                                                required: true,
                                                value: name_element.innerText});

        name_element.innerHTML = "";
        name_element.appendChild(name);

        let category = _build_DOM_element("input", { id : `${row_id}__category_edit`, type:"text",
                                                    required: true,
                                                    value:category_element.innerText});
        category_element.innerHTML = "";
        category_element.appendChild(category);
    }

    function edit_transaction(event) {
        /** Allow editing of a row - invoked when the edit button is clicked **/
        let id = event.target.id.split("__")[0];
        const row = event.target.parentElement;
        if (row.classList.contains("editing"))
        {
            console.log("Saving ....");
            save_edit(row);
            return;
        }

        /** Find anything currently being edited **/
        const currently_editing = document.querySelectorAll(".editing");
        for(let i=0; i<currently_editing.length; i++) {
            revert_edit(currently_editing[i]);
        }

        if (row.classList.contains("editing"))  {
            revert_edit(row);
            return ;
        }

        row.classList.toggle("editing");

        /* Allow editing of name and category fields for parent rows only */
        if (!row.classList.contains("child")) {
            _edit_non_child(id);
        }
        else {
            let parent_id = row.getAttribute("parent_id");
            let parent_row = document.getElementById(parent_id);
            _edit_child(id, parent_row);
        }
    }

    function _toggle_edit() {
        /** Toggle the global edit mode on and off **/
        let button = document.getElementById("toggle_edit");
        button.value = button.value==="Edit" ? "Stop Editing":"Edit";
        let edit_flag = button.value!=="Edit";
        if (!edit_flag)
            _revert_all_edits();

        let edit_buttons = document.getElementsByClassName("edit_button");
        for (let i=0; i<edit_buttons.length; i++) {
            let row = edit_buttons[i].parentElement;
            edit_buttons[i].style.display = edit_flag ? "table-cell" : "none";
            let id = row.id.split("__")[0];
            if (!row.classList.contains("child")) {
                let link_button = row.querySelector(".link_button");
                link_button.style.display = edit_flag ? "table-cell" : "none";
            }
            if (row.classList.contains("editing")) {
                revert_edit(parent);
            }
        }
    }

    function _set_year_selected_event() {
        /** Set the change listener on the year pull down **/
        const year_element= document.getElementById("id_year")
        year_element.addEventListener("change", function() {
            console.log("year changed");
            const year_selected = document.getElementById("year_selected").value;
            const queryString = window.location.search;
            let urlParams = new URLSearchParams(queryString);
            if (year_element.value !== year_selected) {
                if (year_element.value !== "all")
                    urlParams.set("year", year_element.value);
                else
                    urlParams.delete("year");
                urlParams.set("page", "1");
                window.location.search = urlParams.toString();
            }
        });
    }

    function _revert_all_edits() {
        _revert_child_edits();
        _revert_non_child_edits();
    }

    function _revert_non_child_edits() {
        const table = document.getElementById("transactions");
        let any_non_child_editing = document.querySelectorAll("tr.editing:not(.child)");
        /* Should only be one - but loop anyway */
        for (let i=0; i<any_non_child_editing.length; i++) {
            let row = any_non_child_editing[i];
            row.classList.remove("editing")
            _revert_edit_on_non_child(row)
        }
    }

    function _revert_child_edits(){
        /* Revert any existing edits - which means that any new rows are just thrown away */

        const table = document.getElementById("transactions");
        let any_child_editing = document.querySelectorAll("tr.editing.child");
        for (let i=0; i<any_child_editing.length; i++) {
            let parent_id = any_child_editing[i].getAttribute("parent_id");
            let parent_row = document.getElementById(parent_id);

            let row = any_child_editing[i];
            row.classList.remove("editing")
            if (row.classList.contains("new"))
                table.deleteRow(row.rowIndex);
            else
                _revert_edit_on_child(row)
        }
    }

    function close_delete_popup( row_element ) {
        const popup_element = document.getElementById("delete-popup");
        _revert_edit_on_child(row_element);

        popup_element.classList.toggle("visible");
    }

    function delete_transaction_confirmed(id, response) {

        const row_element = document.getElementById(id);
        const table = document.getElementById("transactions");

        const parent_id = row_element.getAttribute("parent_id");
        const parent_row = document.getElementById(parent_id);

        const type = (parent_row.querySelector(".debit").innerText !== "") ? "debit" : "credit";

        const name_element = document.getElementById(id + "__name_edit");
        const amount_element = document.getElementById(id + "__" + type + "_edit");

        name_element.parentElement.innerHTML = name_element.value;
        amount_element.parentElement.innerHTML = amount_element.value;

        /* Update the remaining balance in the parent row */
        let mew_remaining = _decimal2int(parent_row.getAttribute("remaining_" + type)) + _decimal2int(amount_element.defaultValue);
        parent_row.setAttribute("remaining_" + type, _int2decimal(mew_remaining));

        /* Update the summary row */
        let summary_field = document.querySelector(`tr.child.summary[parent_id="${parent_row.id}"] td.col.${type}`)
        summary_field.innerText = _int2decimal(mew_remaining);

        table.deleteRow( row_element.rowIndex)

        const popup_element = document.getElementById("delete-popup");
        popup_element.classList.toggle("visible");

    }

    function delete_transaction(row_element) {
        const popup_element = document.getElementById("delete-popup");
        const id = row_element.id;

        popup_element.classList.toggle("visible");
        popup_element.style.left = (document.body.clientWidth - popup_element.clientWidth)/2 + "px";
        popup_element.style.top = (document.body.clientHeight - popup_element.clientHeight)/2 + "px";

        name = document.getElementById(`${id}__name_edit`).defaultValue;

        const popup_details = document.getElementById("delete-popup-details");
        popup_details.innerText = `Confirm deletion of transaction \"${name}\" ?`;

        const close_button = document.getElementById("delete-close");
        close_button.addEventListener("click",  function() {close_delete_popup(row_element);} );

        const confirm_button = document.getElementById("delete-confirm");
        confirm_button.addEventListener("click", function() {
            _invoke_rest_api("delete_transaction", id, {}, delete_transaction_confirmed);
        });
    }

    function _disable_edit_buttons()
    {
        /** turn off edit buttons for all rows - used when a new child is being created **/
        let edit_buttons = document.querySelectorAll(".edit_button")
        for (i=0;i<edit_buttons.length;i++)
            edit_buttons[i].style.display = "none";
    }

    function link_edit(row_element) {
        /** Allow creation of a new child row **/
        const table = document.getElementById("transactions");

        /* Discard any other editing of child rows */
        _revert_child_edits();

        /* Expand all of the child rows */
        _expand_collapse(row_element, true);

        /* Disable all edit buttons while the child row is active */
        _disable_edit_buttons();

        /* Create a brand new child row */
        _create_child_row(row_element);
    }

    function _set_edit_and_revert_event()
    {
        /** Set click listeners on the row buttons - edit, revert, link **/
        let rows = document.querySelectorAll(".row:not(.summary)");
        for (let i=0; i<rows.length; i++) {
            const edit_button = rows[i].querySelector(".edit_button");
            edit_button.addEventListener("click", edit_transaction);
            const revert_button = rows[i].querySelector(".revert_button");
            revert_button.addEventListener("click", function(event) {revert_edit(event.target.parentElement)});
            const link_button = rows[i].querySelector(".link_button");
            link_button.addEventListener("click", function(event) {link_edit(event.target.parentElement)});
            const delete_button = rows[i].querySelector(".delete_button");
            delete_button.addEventListener("click", function(event) {delete_transaction(event.target.parentElement)});

        }

        /** Need to set the listeners on new child rows too **/
    }

    function _expand_collapse(parent_row, force_state ) {
        /** Expand or collapse a parent row and all of its children **/
        const id = parent_row.id;
        const children = document.querySelectorAll(`[parent_id="${id}"]`)
        if (force_state) {
            parent_row.classList.add('expanded');
            for (let i=0; i<children.length; i++)
                children[i].classList.add('expanded')
        }
        else
        {
            parent_row.classList.toggle('expanded');
            for (let i=0; i<children.length; i++)
                children[i].classList.toggle('expanded')
        }
    }

    function _toggle_collapse() {
        /** Expand or collapse all parent rows, depending on the current state of the button**/
        let button = document.getElementById("toggle_collapse");
        const rows = document.querySelectorAll(".row.parent, .row.child");
        for (let i=0; i<rows.length; i++) {
            if (button.value==="Expand All")
                rows[i].classList.add("expanded");
            else
                rows[i].classList.remove("expanded");
        }
        button.value = button.value==="Collapse All" ? "Expand All":"Collapse All";
    }

    function _set_collapse_expand_event() {
        /** Set listener on the collapse expand button on the parent rows **/
        const rows  = document.querySelectorAll(".row.parent");
        for (let i=0; i<rows.length; i++) {
            const button = rows[i].querySelector(".col.button");
            const parent_row = rows[i]
            button.addEventListener("click", function() {
                parent_row.classList.toggle("expanded");
                let t_id = parent_row.getAttribute("t_id")
                let child_rows = document.querySelectorAll(".row.child[parent_id='" + t_id + "']");
                for (let j=0; j<child_rows.length; j++) {
                    child_rows[j].classList.toggle("expanded");
                }
            });
        }
    }

    function _on_load() {


        /** Set change listener on the Account pull down **/
        const account_element = document.getElementById("id_account")
        account_element.addEventListener("change", function() {
                const account = account_element.value;
                if (account == null || account.trim() === "")
                    return;
                window.location.href = "/Account/report/transactions/" + account + "/";
        });

        _set_year_selected_event();
        _set_collapse_expand_event();
        _set_edit_and_revert_event();
    }

script_tag = document.querySelector('script[src$="transaction_list.js"]');
const csrf_token = script_tag.getAttribute("csrf");

document.addEventListener('DOMContentLoaded', _on_load);
