
function htmlDecode(input) {
  var doc = new DOMParser().parseFromString(input, "text/html");
  return doc.documentElement.textContent;
}

/*
    Extract all of the various parameters and generate a URL fragment
*/
function __get_filters(){
       pop_up = document.getElementById("filter-pop-up")
       if (pop_up == null)
            return null;

       nodes = pop_up.querySelectorAll('input[type="checkbox"]')
       return nodes;
}

function __current_base_url(new_path=''){
    const protocol = window.location.protocol;
    const host = window.location.host;
    const port = window.location.port;
    const search = window.location.search;
    const hash = window.location.hash;
    var pathname = window.location.pathname;

    if(new_path)
        pathname = new_path

    console.log(pathname)
    return protocol+'//'+host+pathname
}

function __params_as_url() {
/*
    Need to find a way to data drive this
*/
       var fragments = [];
       const nodes = __get_filters();

       if (nodes == null)
            return ''

       for (const node of nodes)
       {
            var node_fragment = node.getAttribute('tp-fragment');
            if (!node_fragment)
                continue;

            var checked = node.checked;
            /* Strip off the ! from the start of a fragment attribute */
            if (node_fragment[0] == '!'){
                if (!checked)
                    fragments.push(node_fragment.slice(1));
            }
            else
            {
                if (checked)
                    fragments.push(node_fragment);
            }
       }
       fragment = fragments.join('&');

       return (fragment!='')?'?'+fragment:'';
}

function __url_as_params() {
    const nodes = __get_filters();
    const queryString = window.location.search;
    const urlParams = new URLSearchParams(queryString);

    if (nodes == null)
        return

    for (const node of nodes)
    {
        fragment_name = node.getAttribute('tp-fragment');
        if (!fragment_name)
                continue;

        if (fragment_name[0] == '!')
            node.checked = !urlParams.has(fragment_name.slice(1));
        else
            node.checked = urlParams.has(fragment_name);
    }
}

function popup(name, force_state) {
   var pop_window = document.getElementById(name);
   if (force_state != '') {
        pop_window.style.display = force_state;
        return;
   }
   if (pop_window.style.display === "none") {
       pop_window.style.display = "block";
  } else {
        pop_window.style.display = "none";
    }
}

function save_list_options() {
    url_parameters = __params_as_url();
    popup('filter-pop-up', 'None');
    console.log(__current_base_url() + url_parameters);
    window.location.replace(__current_base_url() + url_parameters);
}

function __filter_changed()
{
    pair = this.getAttribute('tp-pair');
    if (!pair)
        return;
    other = document.getElementById(pair);
    if (!other)
        return;
    if (!this.checked)
        other.checked = true;
}

function do_action(action, id)
{
    var pattern = patterns.get(action);

    console.log( action, name, pattern);

    var path = '/team_page/' + pattern.replace('<int:news_id>',id);
    path = path.replace('<int:sponsor_id>',id);
    path = path.replace('<int:event_id>',id);

    path = path.replace('<str:action>', action);
    window.location.replace(__current_base_url(path) + __params_as_url());
}

function __document_loaded(){

    __url_as_params();


    /* Set the event listeners on the filter pop-up */
    var nodes = __get_filters();
    if (nodes){
        for(const node of nodes){
            node.addEventListener('change', __filter_changed)
        }
    }

    /* get the event_id if it exists */
    element = document.getElementById('tp_event_id');
    if (element)
        event_id = element.value;
    else
        event_id = null;


    /* Establish Actions for Sublist Toolbar buttons */
    toolbar = document.getElementById('id_al_toolbar');
    if (toolbar) {
        new_button = document.getElementById('tp-create');
        if (new_button)
            new_button.addEventListener('click', function() {do_action( 'create', event_id );} );

        filter_button = document.getElementById('tp-filters');
        if (filter_button)
            filter_button.addEventListener('click', function() {popup('filter-pop-up',''); } );
    }

    /* set the forms buttons if any */
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
            column_class = column.getAttribute('class')
            if (column_class == 'icons')
            {
                for(span of column.children)
                {
                    const action = span.getAttribute('tp_action');
                    const id = span.getAttribute('tp_row_id');
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

