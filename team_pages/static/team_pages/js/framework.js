
function preview_image(event, field_name) {
    /* Invoked when the form has an image field - to preview the image identified in the field */
    const reader = new FileReader();
    reader.onload = function(){
        const output = document.getElementById('output_' + field_name + '_image');
        const span = document.getElementById('id_' + field_name + '_preview');
        span.style.display='inline-block';
        output.src = reader.result;
        }
    reader.readAsDataURL(event.target.files[0]);
}

function __get_filters(){
    /* Extract filter check boxes from the filter pop-up  */
    let pop_up = document.getElementById("filter-pop-up")
       if (pop_up == null) {
           console.log("No filter pop-up");
            return null;
           }
    return pop_up.querySelectorAll('input[type="checkbox"]')
}

function __current_base_url(new_path=''){
    /** return the current base URL - excluding the query string **/
    const protocol = window.location.protocol;
    const host = window.location.host;
    let pathname = window.location.pathname;

    if(new_path)
        pathname = new_path

    return protocol+'//'+host+'/'+pathname
}

function __params_as_url() {
    /* converts the status of the filter check boxes in a URL query String*/
    let fragments = [];
    const nodes = __get_filters();

    if (nodes == null)
            return ''

    for (const node of nodes)
    {
        /* Extract the relevant query fragment from that check box field */
        let node_fragment = node.getAttribute('tp-fragment');
        if (!node_fragment)
            continue;

        let checked = node.checked;
        /* Strip off the ! from the start of a fragment attribute - and use if not checked - ie exclusion */
        if (node_fragment[0] === '!'){
            if (!checked)
                fragments.push(node_fragment.slice(1));
        }
        else
        {
            /* No leading ! - so use if checked - ie inclusion */
            if (checked)
                fragments.push(node_fragment);
        }
    }
    let fragment = fragments.join('&');

    /* return the fragment with leading ? if the fragment exists */
    return (fragment!=='')?'?'+fragment:'';
}

function __url_as_params() {
    /* converts URL query String into a set of checked or unchecked filter check boxes */
    const nodes = __get_filters();
    const queryString = window.location.search;
    const urlParams = new URLSearchParams(queryString);

    if (nodes == null)
        return

    for (const node of nodes)
    {
        let fragment_name = node.getAttribute('tp-fragment');
        if (!fragment_name)
                continue;

        /* Fragments that start with a ! are exclusion fragments - ie not checked if the fragment is present */
        if (fragment_name[0] === '!')
            node.checked = !urlParams.has(fragment_name.slice(1));
        else
            /* Fragments that don't start with a ! are inclusion fragments - ie checked if the fragment is present */
            node.checked = urlParams.has(fragment_name);
    }
}

function _popup_element(event, element, force_state) {
    if (force_state !== null) {
        element.style.visibility = force_state;
        element.style.display = (force_state === 'visible') ? 'block' : 'None';
    } else {
        /* Toggle the visibility of the window */
        element.style.display = (element.style.display === "block") ? 'None' : 'block';
        element.style.visibility = (element.style.visibility === "visible") ? 'hidden' : 'visible';
    }

    /* If triggered by a click event, then position the window based on the click */
    if (event && element.style.display === "block")
    {
        element.style.left =
            (event.pageX + element.clientWidth + 10 < document.body.clientWidth)
          ? (event.pageX + 10 + "px")
          : (document.body.clientWidth + 5 - element.clientWidth + "px");
       element.style.top =
            (event.pageY + element.clientHeight + 10 < document.body.clientHeight)
          ? (event.pageY + 10 + "px")
          : (document.body.clientHeight + 5 - element.clientHeight + "px");
    }
    else {
        <!-- Make the pop-up window to be centered -->
        element.style.left = (document.body.clientWidth - element.clientWidth)/2 + "px";
        element.style.top = (document.body.clientHeight - element.clientHeight)/2 + "px";
    }
}

function popup(event, name, force_state) {
    /* Force a change of state onto a named pop-up window  */
    const pop_window = document.getElementById(name);
    _popup_element(event, pop_window, force_state);
}

function cancel_filter_popup()
{
    /* Close and ignore the filter popup */
    popup(null, "filter-pop-up", 'hidden');
    __url_as_params(); /* Force a re-read of the URL into the filter check-boxes - revert any changes */
}

function save_list_options() {
    /* Save the current filter check boxes into the URL and reload */
    let url_parameters = __params_as_url();
    popup( null, 'filter-pop-up', 'hidden');
    window.location.replace(__current_base_url() + url_parameters);
}

/* ToDo - Extend pair system to a more generalised group idea - where at least one in the group remains checked */
function __filter_changed()
{
    /* Handle a change in the state of a filter - if it has a pair, for example, */
    /* Ensure one of the pair is always highlighted */
    const pair = this.getAttribute('tp-pair');
    if (!pair)
        return;
    const other = document.getElementById(pair);
    if (!other)
        return;

    /* If this filter is unchecked, force its pair to be checked */
    if (!this.checked)
        other.checked = true;
}

function do_action(action, id) {
    console.log(action + ' invoked for ' + id)
    /* Perform an action on a list item - ie edit, cancel, delete */
    let action_info = actions.get(action);
    if (action_info == null) {
        console.log("No action info for " + action);
        return;
    }

    const popup_element = document.getElementById(action + '-popup');

    let full_path=null;
    if (action_info.object)
        full_path = __current_base_url(url_base) + '/' + id + '/' + action + __params_as_url();
    else
        full_path = __current_base_url(url_base) + '/' + action + __params_as_url();

    if (popup_element) {
        /* Add the path to the input button on that popup */
        let confirm_button = popup_element.querySelector('input.button.confirm');
        let cancel_button = popup_element.querySelector('input.button.cancel');
        if (!confirm_button) {
            console.log('No confirm button in popup for ' + action);
            return;
        }
        if (!cancel_button) {
            console.log('No Cancel button in popup for ' + action);
            return;
        }

        cancel_button.addEventListener('click', function (event) {
            popup(null, action + '-popup', 'invisible');
            document.location.reload();
        })

        confirm_button.addEventListener('click', function (event) {
            const options = popup_element.querySelectorAll('input[type="checkbox"]');
            let query = [];
            for (const option of options) {
                let fragment = option.getAttribute('tp_fragment');
                fragment = ((fragment[0] === '!' && !option.checked))?fragment.slice(1):((fragment[0] !== '!' && option.checked)? fragment : '');
                if (fragment !== '') {
                    query.push(fragment);
                }
            }

            /* Combine any filters and options from the pop-up into a single URL */
            let fragment = query.join('&');
            let params = __params_as_url();
            if (params)
                fragment = (fragment !=='')? '&' + fragment: '';
            else
                fragment = (fragment !== '') ? '?' + fragment : '';

            full_path = full_path + fragment;
            window.location.replace(full_path);
        });
        popup(null, action + '-popup', 'visible');
    } else {
        window.location.replace(full_path);
    }
}

function __set_row_actions()
{
    /* Find the 'icons' column for each row - and set an event listener for each action */
    const list_rows = document.getElementById("tp_item_list").children
    for( const row of list_rows)
    {
        for( const column of row.children)
        {
            let column_class = column.getAttribute('class')
            if (column_class.includes('icons'))
            {
                let span = null;
                for(span of column.children)
                {
                    const action = span.getAttribute('tp_action');
                    const id = span.getAttribute('tp_row_id');
                    const action_info = actions.get(action)
                    console.log('Action : ' + action + ' ID : ' + id  + ' Info : ' + ((action_info==null)?'No':'Yes'));

                    if (action_info == null)
                        continue;
/*                    if (action_info.path === '' || action_info.path === null)
                        continue; */
                    span.addEventListener('click',
                            function(){
                                do_action( action, id );}
                                );
                }
            }
        }
    }
}

    function  __set_multi_select_actions()
    {
        /** Set the various actions for the multiple select buttons **/
        if (!allow_multiple)
            return;

        const select_all = document.querySelector('table tr.heading th.SelectAll input[type="checkbox"]');
        if (select_all) {
            select_all.addEventListener('change', function() {
                let checkboxes = document.querySelectorAll('table tbody#tp_item_list tr.data-row input[type="checkbox"][name=Select]');
                for (const checkbox of checkboxes) {
                    checkbox.checked = select_all.checked;
                }
            });
        }


    }


function __document_loaded(){

    /* Read the URL and set the filter check boxes accordingly */
    __url_as_params();


    /* Set the event listeners on the filter pop-up */
    let nodes = __get_filters();
    if (nodes){
        for(const node of nodes){
            node.addEventListener('change', __filter_changed)
        }
    }

    /* get the event_id if it exists */
    let event_id = null;
    let element = document.getElementById('tp_event_id');
    if (element)
         event_id = element.value;

    /* Establish Actions for Toolbar buttons */
    let toolbar = document.getElementById('id_al_toolbar');
    if (toolbar) {
        let buttons = toolbar.querySelectorAll('span');
        for (const button of buttons) {
            console.log('Toolbar button : ' + button.getAttribute('tp_action'));

            /* Skip the filter button */
            if (button.getAttribute('id') === 'tp-filters')
                continue

            let action = button.getAttribute('tp_action');
            if (action === null)
                continue;
            button.addEventListener('click',
                function(){
                    do_action( action, event_id );}
                );
        }

        let filter_button = document.getElementById('tp-filters');
        if (filter_button)
            filter_button.addEventListener('click',
                function( e ) {popup(e,'filter-pop-up',null); } );
    }


    __set_row_actions();

    __set_multi_select_actions();
     /**
    const cancel_button = document.getElementById('tp_cancel_form');
    if (cancel_button)
    {
            const id = cancel_button.getAttribute('item_id')
            cancel_button.addEventListener('click', function() {
                                        do_action( 'cancel', id ); } );
    }

    const edit_button = document.getElementById('tp_edit_form');
    if (edit_button){
            const id = edit_button.getAttribute('item_id')
            edit_button.addEventListener('click', function() {
                                        do_action( 'edit', id ); } );
    }
    **/


}

document.addEventListener('DOMContentLoaded', __document_loaded);

