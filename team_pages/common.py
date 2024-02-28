import re

# Match up to two sub-parts
compiled_pattern = re.compile(r'/team_page/((?P<event_date>.+?)/)?((?P<category>.+?)/)?')


def extract_url_components(path):
    """"Extract components from the  url
        Return : a 'normalised' dictionary of components

        Normalisation:
            Missing items replaced with a ''
            prefix removed if present
    """
    match = compiled_pattern.fullmatch(path)
    if match is None:
        return {'event_date': '', 'category': ''}

    components = match.groupdict().copy()
    components = {k: (v if v is not None else '') for k, v in components.items()}
    components['event_date'] = components['event_date'] if not components.get('event_date', '').startswith('event:') \
        else components['event_date'][6:].replace('_','-')
    components['category'] = components['category'] if not components.get('category', '').startswith('data:') \
        else components['category'][4:]

    return components
