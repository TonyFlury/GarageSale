'use strict';
{
    class SelectBox {
    cache = new Map();
    total = 0;
    filtered = 0 ;
    element = null;

    constructor( element) {
        this.element = element;
        /* Record all of the options in a cache - allows filtering */
        for (let i = 0; i < element.options.length; i++) {
            this.cache.set(element.options[i].text, element.options[i].value );
        }
        this.total = this.cache.size;
    }

     /* Reset the contents of the select box based on the filter */
     setFilter( filter_value )
     {
         if (filter_value === '') {
             this.clearFilter();
             return;
         }
         this.element.innerHTML = '';
         for (let [key, value] of this.cache) {
             if (key.toLowerCase().includes(filter_value.toLowerCase())) {
                make_element( 'option', this.element, {'value': value, 'text': key})
             }
         }
         this.filtered = this.element.options.length;
     }

     /* Display the number of items in the select box */
     count() {
          return   `${this.filtered} of ${this.total}`
      }

     /* Clear the filter */
     clearFilter() {
         this.element.innerHTML = '';
         for (let [key, value] of this.cache) {
             make_element( 'option', this.element, {'value': value, 'text': key})
         }
         this.filtered = this.total;
     }
     anyselected() {
         return this.element.selectedOptions.length > 0;
     }
     numberselected() {
         return this.element.selectedOptions.length;
     }
    }

function make_element( element_name, parent,  options) {
    let element = document.createElement(element_name);
    for (let key in options) {
        element[key] = options[key];
    }
    if (parent != null)
        parent.appendChild(element);
    return element;
    }

class FilteredSelectBox {
    select_box = null ;
    select_count = null ;
    filter_element = null;
    submit_element = null;

    constructor( element, select_count ) {
        this.select_box = new SelectBox(element);
        this.select_count = select_count;

        let fieldset = element.closest('fieldset')

        let form = fieldset.closest('form');

        if (form != null)
            form.owner_obj = this;

        /** Build the UI around the select box */
        let children = Array.from(fieldset.children);
        let outer = make_element('div', fieldset, {'classList': 'FilteredSelectBox'});
        children.forEach(function(child) {outer.appendChild(child);});

        /* Build the elements needed for the filter */
        if (element.classList.contains('select-filter')) {
            /* Build the filter element */
            let filter_div = make_element('div', null,{'classList': 'select-filter'})
            outer.insertBefore(filter_div, element);

            let filter_label = make_element('label', filter_div,
                {'innerText': '', 'htmlFor': element.id + '_filter'})
            make_element('span', filter_label, {'classList': 'tool-tip icon', 'title': 'Filter the list of users'})

            this.filter_input = make_element('input', filter_div,
                {'type': 'text', 'id': element.id + '_filter', 'class': 'filter-input', owner_obj: this});

            /* Set events for the UI */
            this.filter_input.addEventListener('keypress', function( event ) {
                let element = event.target;
                element.owner_obj.select_box.setFilter(this.value);
            })
            this.filter_input.addEventListener('keyup', function( event ) {
                let element = event.target;
                element.owner_obj.select_box.setFilter(this.value);
            })
            this.filter_input.addEventListener('keydown', function( event ) {
                let element = event.target;
                element.owner_obj.select_box.setFilter(this.value);
            })
        }

        /* Build the details for the 'new-entry' */
        if (element.classList.contains('new-entry'))
        {
            make_element('span', outer,
                            {'innerText':'or', 'style':'text-align: center;'});
            let new_entry_div = make_element('div', outer,
                    {'classList': 'new-entry-div'})
            let new_entry_label = make_element('label', new_entry_div,
                    {'innerText': '', 'htmlFor': 'new_user'})
            make_element('span', new_entry_label,
                        {'classList': 'tool-tip icon', 'title': 'Create a new user'})
            this.new_entry = make_element('input', new_entry_div,
                {'type': element.getAttribute('field-type'), 'name':'new-entry','id': 'new_entry', 'class': 'new-entry', 'owner_obj': this});
        }

        /* Warnings and errors */
        this.warning_element = make_element('div', outer, {'owner_obj': this, 'classList': 'warning'})
        make_element('span', this.warning_element, {});

        this.warning_element.addEventListener('click', function( event ) {
            let element = event.target;
            if (element.hasAttribute('owner_obj') === false)
                element = element.parentElement;
            element.owner_obj.clear_warning();
            } ) ;

        /* build the submit button */
        let submit_div = make_element('div', outer, {'classList': 'submit-button-div'})

        let button_type = 'submit'
        if (element.hasAttribute('submit_dialog'))
            button_type = 'button'

        this.submit_element = make_element('input', submit_div,
            {'type': button_type, 'value': 'Create Location for this user', 'owner_obj': this, 'classList': 'submit-button'})

        if (form && button_type==='submit')
            form.addEventListener('submit', submit_form )
        else if (button_type==='button')
            this.submit_element.addEventListener('click', function( event ) {
                let owner_obj = event.target.owner_obj;
                if (validate_select(owner_obj) ) {
                    owner_obj.submit_element.disabled = true;
                    owner_obj.submit_element.value = 'Creating...';
                    let field_name = element.getAttribute('field_name');
                    let field = document.getElementById(field_name);
                    let selected_users = owner_obj.get_selected_users()[0];
                    field.value = JSON.stringify(selected_users);

                    let dialog_name = owner_obj.select_box.element.getAttribute('submit_dialog');
                    let dialog = document.getElementById(dialog_name)
                    dialog.showModal();
                }
            } )
    }

    warning( message ){
        this.warning_element.querySelector('span').innerText = message;
        this.warning_element.classList.add('warning-active');
    }

    clear_warning(message){
        this.warning_element.querySelector('span').innerText = '';
        this.warning_element.classList.remove('warning-active');
    }

    get_selected_users() {
        let selected_users = [];
        let select_box = this.select_box;
        for (let i = 0; i < select_box.element.options.length; i++) {
            if (select_box.element.options[i].selected) {
                selected_users.push(select_box.element.options[i].text);
            }
        }
        if (this.select_box.element.hasAttribute('new-entry')) {
            selected_users.push(this.new_entry.value)
        }
        return selected_users;
    }

}


    function validate_select( owner) {
        let select_box = owner.select_box;
        let count = select_box.numberselected();
        let select_count = owner.select_count;

        if (select_box.element.classList.contains('new-entry')) {
            if (owner.new_entry.value !== '') {
                if (count > 1) {
                    owner.warning('Please only select either a user or enter a new email address');
                    return false;
                } else
                    return true
            }
        }
        if (count === 0) {
            owner.warning('Please select a user to create a location for');
            return false;
        } else if (count > select_count) {
            owner.warning(`select no more than  ${select_count} entries before submission`);
            return false;
        } else {
            return true;
        }
    }

    function submit_form(event) {
        /* event.preventDefault(); */
        let owner = event.target.owner_obj;
        return validate_select(owner);
    }


window.addEventListener('load', function(e) {
    window.selectboxes = [];
    document.querySelectorAll('select.select-filter').forEach(function (el) {
        window.selectboxes.push( new FilteredSelectBox(el, el.getAttribute('max_select')) );
    });
    } );
}