
function preview_image(event, field_name) {
    var reader = new FileReader();
    reader.onload = function(){
        var output = document.getElementById('output_'+field_name + '_image');
        var span = document.getElementById('id_'+field_name + '_preview');
        span.style.display='inline-block';
        output.src = reader.result;
        }
    reader.readAsDataURL(event.target.files[0]);
}

function htmlDecode(input) {
  let doc = new DOMParser().parseFromString(input, "text/html");
  return doc.documentElement.textContent;
}

function get_icon_for_action(action) {
    let action_data = actions.get(action)
    if (action_data == null)
    {
        console.log("No action data for " + action);
        return ''
    }

    return action_data.icon;
}

/*
    Extract all the various parameters and generate a URL fragment
*/
function __get_filters(){
    let pop_up = document.getElementById("filter-pop-up")
       if (pop_up == null) {
           console.log("No filter pop-up");
            return null;
           }
    return pop_up.querySelectorAll('input[type="checkbox"]')
}

function __current_base_url(new_path=''){
    const protocol = window.location.protocol;
    const host = window.location.host;
    let pathname = window.location.pathname;

    if(new_path)
        pathname = new_path

    return protocol+'//'+host+pathname
}

function __params_as_url() {
/*
    Need to find a way to data drive this
*/
    let fragments = [];
    const nodes = __get_filters();

       if (nodes == null)
            return ''

       for (const node of nodes)
       {
           let node_fragment = node.getAttribute('tp-fragment');
           if (!node_fragment)
                continue;

           let checked = node.checked;
           /* Strip off the ! from the start of a fragment attribute */
            if (node_fragment[0] === '!'){
                if (!checked)
                    fragments.push(node_fragment.slice(1));
            }
            else
            {
                if (checked)
                    fragments.push(node_fragment);
            }
       }
    let fragment = fragments.join('&');

    return (fragment!=='')?'?'+fragment:'';
}

function __url_as_params() {
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

        if (fragment_name[0] === '!')
            node.checked = !urlParams.has(fragment_name.slice(1));
        else
            node.checked = urlParams.has(fragment_name);
    }
}

function popup(event, name, force_state) {
    const pop_window = document.getElementById(name);
    if (force_state !== null) {
        pop_window.style.visibility = force_state;
        return;
    }

   if (pop_window.style.visibility === "hidden" || pop_window.style.visibility === "") {
       pop_window.style.display = "block";
       pop_window.style.visibility = "visible";
  } else {
        pop_window.style.display = "None";
        pop_window.style.visibility = "hidden";
    }
    if (event)
    {
        pop_window.style.left =
            (event.pageX + pop_window.clientWidth + 10 < document.body.clientWidth)
          ? (event.pageX + 10 + "px")
          : (document.body.clientWidth + 5 - pop_window.clientWidth + "px");
       pop_window.style.top =
            (event.pageY + pop_window.clientHeight + 10 < document.body.clientHeight)
          ? (event.pageY + 10 + "px")
          : (document.body.clientHeight + 5 - pop_window.clientHeight + "px");
    }
    else {
        <!-- Make pop-up window to be centered -->
        pop_window.style.left = (document.body.clientWidth - pop_window.clientWidth)/2 + "px";
        pop_window.style.top = (document.body.clientHeight - pop_window.clientHeight)/2 + "px";
    }
}

function cancel_filter_popup()
{
    popup(null, "filter-pop-up", 'hidden');
    __url_as_params(); /* Force a re-read of the URL into the filter check-boxes - revert any changes */
}

function save_list_options() {
    let url_parameters = __params_as_url();
    popup( null, 'filter-pop-up', 'hidden');
    window.location.replace(__current_base_url() + url_parameters);
}

function __filter_changed()
{
    const pair = this.getAttribute('tp-pair');
    if (!pair)
        return;
    const other = document.getElementById(pair);
    if (!other)
        return;

    if (!this.checked)
        other.checked = true;
}

function do_action(action, id)
{
    let action_info = actions.get(action);
    if (action_info == null)
        {
            console.log("No action info for " + action);
            return;
        }

    let path = action_info.path;

    for(let i=0;i < fields.length;i++)
    {
        path = path.replace(fields[i], id);
    }

    window.location.replace(__current_base_url(path) + __params_as_url());
}

function __document_loaded(){

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


    /* Establish Actions for Sublist Toolbar buttons */
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

    /* set the form's buttons if any */
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

    const list_rows = document.getElementById("tp_tbody_item_list").children
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
                    if (action_info == null)
                        continue;
                    if (action_info.path === '' || action_info.path === null)
                        continue;
                    span.addEventListener('click',
                            function(){
                                do_action( action, id );}
                                );
                }
            }
        }
    }
}

document.addEventListener('DOMContentLoaded', __document_loaded);

