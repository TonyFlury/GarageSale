export function _decimal2int(decimal_string) {
    /* Convert a decimal string to an integer */
    let parts = decimal_string.split(".");
    if (parts.length === 1)
        return parseInt(decimal_string) * 100;
    else
        parts[1] = parts[1].padEnd(2, '0');
    return parseInt(decimal_string.split(".").join(''));
}

export function _int2decimal(integer) {
    /* Convert an integer to a decimal string */
    return String(Math.floor(integer / 100)) + "." + String(integer % 100).padStart(2, '0');
}

export function _build_DOM_element(name, options) {
    /** build a DDOM element with the given name and options **/
    let element = document.createElement(name)
    for (let key in options) {
        element[key] = options[key];
    }
    return element;
}

export function _invoke_rest_api(verb, object_id, csrf_token, data, callback, method = 'PUT') {
    /* Send a REST API request to the server */

    let init= ''
    if (method === 'GET')
        init ={method:'GET', headers: {"X-CSRFToken": csrf_token, "Content-Type": "application/json"}}
    else
        init = {method:method,
            headers: {"X-CSRFToken": csrf_token, "Content-Type": "application/json"},
                    body: JSON.stringify(data)}
    let request = new Request(`/Account/${verb}/${object_id}/`,
        init);

    fetch(request).then(response => {
        if (!response.ok)
            console.log("Error: " + response.statusText);
        return response.json();
    }).then(response => {
        callback(object_id, response)
    }).catch(error => console.log(error));
}