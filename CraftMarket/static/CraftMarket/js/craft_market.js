function showPopup(element, name, action)
{
     element.style.display = 'block'
     console.log('Window : ' + window.innerWidth + 'x' + window.innerHeight)
     console.log('Pop-up : ' + element.offsetWidth + 'x' + element.offsetHeight)
    element.style.left = (window.innerWidth - element.offsetWidth)/ 2 + 'px'
    element.style.top = (window.innerHeight - element.offsetHeight)/ 2 + 'px'

     const name_elements = element.querySelectorAll('span.name')
     for (let i = 0; i < name_elements.length; i++) {
         name_elements[i].innerText = name
     }

     const cancel_button = element.querySelector('input.button.cancel')
     const confirm_button = element.querySelector('input.button.confirm')
     cancel_button.addEventListener('click', function() {
         element.hidden = true
         element.style.display = 'none'
         return false
     })

     confirm_button.addEventListener('click', function() {
         const email_element = element.querySelector('#send_email')
         let email = true;
         if (email_element)
             email = email_element.checked ;

         element.hidden = true ;
         element.style.display = 'none' ;

         if (email)
             window.location.href = action;
        else
             window.location.href = action + '?no_email';

         return true
     })
    return true;
}

function __set_action_event(action, event_id, url_head)
{
    let popup = document.getElementById(action + '_popup')

    console.assert(popup != null, action +'_popup element does not exist')

    let actions = document.querySelectorAll('span.action[tp_action="' + action + '"]')
    console.log('Found ' + action + ' Actions : ' + actions.length)
    for (let i = 0; i < actions.length; i++) {
        const id = actions[i].getAttribute('tp_row_id')
        const parent_row = actions[i].parentElement.parentElement
        console.assert(parent_row.classList.contains('data-row'), 'Grand-Parent element is not a row')

        const name = parent_row.querySelector('td.cell.name[tp_row_id="' + id + '"]').textContent
        console.log('Mame for ID : ' + id + ' is ' + name)

        const action_url = url_head + id + '/' + action + '/'
        actions[i].addEventListener('click',
            function () { showPopup(popup, name, action_url)})
        }
}

function __document_loaded() {
    let eventId = document.getElementById('tp_event_id').value
    const url_head = window.location.protocol + '//' + window.location.host + '/CraftMarket/'
    console.log('Event ID : ' + eventId)

    __set_action_event('invite', eventId, url_head)
    __set_action_event('confirm', eventId, url_head)
    __set_action_event('reject', eventId, url_head)

}

document.addEventListener('DOMContentLoaded', __document_loaded);
