# Subclassing the contributor spreadsheet view

`ContributorSpreadsheetView` in `Contributors/views/general_views.py` provides
the contributor spreadsheet, login protection, optional display columns,
toolbar POST actions, and structured checkbox filters. Subclass it to configure
a spreadsheet for a particular contributor type.

## A basic spreadsheet

```python
from Contributors.views.general_views import ContributorSpreadsheetView


class SponsorSpreadsheetView(ContributorSpreadsheetView):
    contributor_type = "Sponsor"
    show_contributions = True
    data_label = "Sponsor"
    extra_context = {"title": "Sponsors"}
```

Register the subclass in your app's URL configuration:

```python
from django.urls import path
from .views import SponsorSpreadsheetView

urlpatterns = [
    path("spreadsheet/", SponsorSpreadsheetView.as_view(), name="spreadsheet"),
]
```

`contributor_type` must match the stored value, including case. Its default,
`None`, includes all contributor types. `show_contributions` defaults to `True`
and controls contribution functionality in the details interface.

`data_label` is the singular display name, defaulting to `"Contributor"`.
Set it to `"Sponsor"` or `"Marketer"` to customize spreadsheet titles, search
and filter labels, details and history headings, and details loading messages.
It is supplied in context and does not change model fields or URL names.

The default model is `Contributor`, the template is
`contributor_spreadsheet.html`, and the template's row collection is named
`contributors`. The template uses the existing `contributors:` URLs for row
editing and dialogs; keep those URLs available when registering a subclass.

The base class requires login. Add Django's `PermissionRequiredMixin` before
the spreadsheet class when the page needs an additional permission, as the
existing `Sponsors.views.SponsorSpreadsheetView` does.

## Read-only extra columns

Define an ordered sequence of dictionaries:

```python
extra_columns = (
    {"label": "Description", "template": "widgets/sponsor_description.html"},
    {"label": "Email status", "template": "widgets/sponsor_email_status.html"},
)
```

Every extra column appears immediately before Actions. Each cell template
receives `contributor` and `column`, as well as the surrounding page context.
Write only the cell content; the spreadsheet supplies the `<td>` element.

For `Contributors/templates/widgets/sponsor_description.html`:

```django
{{ contributor.description|default:"—" }}
```

For `Contributors/templates/widgets/sponsor_email_status.html`:

```django
{% if contributor.email %}Has email{% else %}No email{% endif %}
```

These columns are for read-only values such as strings or icons. They do not
participate in row saving. Unsaved rows have blank cells, including new rows
created by JavaScript. A full page reload renders the saved contributor's cells.

Override `get_extra_columns()` when the definitions depend on the request.
Return a reusable list or tuple because the template iterates it for both
headers and rows.

## Toolbar actions

Each dictionary defines a button and its handler. An empty dictionary inserts
a vertical separator. The optional actions also have a leading separator.

```python
from django.contrib import messages
from Contributors.views.general_views import ContributorSpreadsheetView


class SponsorSpreadsheetView(ContributorSpreadsheetView):
    contributor_type = "Sponsor"
    extra_toolbar_actions = (
        {"name": "count", "label": "Count sponsors", "handler": "count_sponsors"},
        {},
        {
            "name": "count_email",
            "label": "Count sponsors with email",
            "handler": "count_sponsors_with_email",
            "icon": "GarageSale/images/icons/email-open-svgrepo-com.svg",
        },
    )

    def count_sponsors(self, post_data):
        count = self.get_queryset().count()
        messages.info(self.request, f"{count} sponsors in the current spreadsheet.")

    def count_sponsors_with_email(self, post_data):
        count = self.get_queryset().exclude(email__isnull=True).exclude(email="").count()
        messages.info(self.request, f"{count} sponsors have email addresses.")
```

| Key | Meaning |
| --- | --- |
| `name` | Unique action identifier submitted as `toolbar_action`. |
| `label` | Visible text, or the accessible label and tooltip when using an icon. |
| `handler` | Method name, or a callable accepting `(view, post_data)`. |
| `icon` | Optional static asset path, without a `/static/` prefix. |
| `requires_selection` | Optional boolean; defaults to false. Requires at least one selected visible row. |

Icon buttons display the image instead of the label. Text-only buttons use the
same toolbar button styling. Do not call `static()` on an icon path here; the
template resolves it.

A callable can be supplied directly by defining the method before the list:

```python
def count_sponsors(self, post_data):
    # Perform the action here.
    pass

extra_toolbar_actions = (
    {"name": "count", "label": "Count sponsors", "handler": count_sponsors},
)
```

Buttons submit a CSRF-protected POST to the current spreadsheet URL. The base
`post()` looks up the submitted name only in `get_extra_toolbar_actions()` and
passes the full `request.POST` QueryDict to the handler. A missing or unknown
action returns HTTP 400. Separators are skipped during dispatch.

Handlers can access `self.request` and `self.selected_filters`. Returning an HTTP
response sends it directly to the browser, allowing downloads without rerendering.
Otherwise, after the handler completes, the base view clears its cached
historic event date, fetches the queryset again, and renders the whole page.
This is a direct response to the POST, so refreshing that response may resubmit
the action. Exceptions from handlers propagate through Django normally.

The built-in toolbar form submits the action, CSRF token, active structured
filters, and the IDs of selected visible rows as repeated `selected_contributor`
fields. Read these in a handler with `post_data.getlist("selected_contributor")`.
Rows hidden by browser search are not included. Add explicit form fields if
an action needs additional input.

Set `"requires_selection": True` on an action to disable its button while no
visible contributor is selected. Disabled buttons have a light-grey translucent
overlay. Individual checkboxes, Select All, and browser search update their state.
Actions without the flag remain available, even when no rows are selected.

```python
extra_toolbar_actions = (
    {"name": "email", "label": "Send email", "handler": "send_email",
     "requires_selection": True},
)

def send_email(self, post_data):
    selected_ids = post_data.getlist("selected_contributor")
    recipients = self.get_queryset().filter(pk__in=selected_ids)
    # Prepare the email workflow for these recipients.
```

The base POST handler rejects a selection-required action with HTTP 400 if no
selected IDs are supplied. Handlers must still validate and scope submitted IDs
to the contributors they are allowed to act on. Selection is not an authorization
check. Toolbar actions remain ordinary POSTs; re-rendering the page resets the
row checkboxes.

Override `get_extra_toolbar_actions()` to define actions dynamically. For data
updates, apply the appropriate authorization in the subclass or handler and
scope updates explicitly. Using `self.get_queryset()` targets the currently
filtered rows; use a separate scoped queryset when an action should cover all
contributors of that type.

## Structured checkbox filters

A nonempty `filter_options` sequence enables the funnel button automatically;
you do not add a filter handler to `extra_toolbar_actions`. The funnel button
has a vertical separator after it. Empty dictionaries in the options sequence
render horizontal lines in the dialog.

```python
class SponsorSpreadsheetView(ContributorSpreadsheetView):
    contributor_type = "Sponsor"
    filter_options = (
        {"name": "has_email", "label": "Has email"},
        {},
        {"name": "has_phone", "label": "Has phone"},
    )

    def filter_queryset(self, queryset):
        if "has_email" in self.selected_filters:
            queryset = queryset.exclude(email__isnull=True).exclude(email="")
        if "has_phone" in self.selected_filters:
            queryset = queryset.exclude(phone="")
        return queryset
```

Each option needs a unique `name` and a `label`. The popup displays a checkbox
for each option, plus Cancel and Filter buttons. Cancel or Escape discards
pending edits; reopening restores the last applied selections.

An optional nonempty `group` makes options mutually exclusive within that
group. For example:

```python
filter_options = (
    {"name": "has_email", "label": "Has email", "group": "email_status"},
    {"name": "no_email", "label": "No email", "group": "email_status"},
    {},
    {"name": "has_phone", "label": "Has phone"},
)
```

Checking “Has email” clears “No email” and vice versa. Ungrouped options and
options in different groups remain independent. Users can uncheck every option
in a group; no selection is required. Separators do not define group boundaries.
Use string group names. If a manually constructed GET or POST submits multiple
options in a group, the view keeps the first selected option in definition order.
This ensures `self.selected_filters` and the rendered checked states agree.

Filter submits a normal GET to the spreadsheet URL and renders the whole page.
Checked names are repeated `selected_filters` parameters, for example:

```text
?selected_filters=has_email&selected_filters=has_phone
```

`self.selected_filters` contains only known option names, deduplicated and
ordered according to the option definitions. The same list is supplied as
`selected_filters` in template context so the popup checks the applied options.
Submitting with nothing checked clears the filters. Active selections are
also included as hidden fields in toolbar POSTs and survive those actions.
Selections are carried in requests, rather than stored in a session.

The base `filter_queryset(queryset)` returns the queryset unchanged. Your
override decides what the checkboxes mean, including whether multiple
selections combine with AND or OR. The example above uses AND. Override
`get_filter_options()` for request-dependent definitions, keeping them stable
during the request because both filtering and rendering use them.

The existing company/contact/email search boxes operate in the browser on
already loaded rows. They are separate from these server-side filters and
their values are not preserved by the full-page filter reload. The filter
form submits its own fields; other existing URL parameters are not retained.

## View-provided modal dialogs

Set `modal_html` or override `get_modal_html()` to supply a **pre-rendered HTML
fragment**. A nonempty fragment causes the spreadsheet template to render
`#spreadsheet-modal-dialog`; `contributor_modal.js` opens it automatically when
the page loads. With no fragment, no modal is rendered or opened.

The spreadsheet supplies only the dialog shell, backdrop, and close button.
Your fragment supplies all content, including its own `<form>`, `method`,
`action`, fields, submit buttons, and CSRF token. It must not contain another
`<dialog>`. The form submits normally to its destination; there is no automatic
AJAX interception or dispatch through spreadsheet toolbar handlers.

For example, a toolbar action can prepare a modal instead of updating data:

```python
from django.template.loader import render_to_string
from django.urls import reverse


class SponsorSpreadsheetView(ContributorSpreadsheetView):
    contributor_type = "Sponsor"
    data_label = "Sponsor"
    extra_toolbar_actions = (
        {"name": "review", "label": "Review", "handler": "show_review"},
    )

    def show_review(self, post_data):
        self.modal_html = render_to_string(
            "sponsors/review_dialog.html",
            {
                "data_label": self.data_label,
                # Register this destination in your app's URL configuration.
                "destination": reverse("Sponsors:confirm_review"),
                "selected_filters": self.selected_filters,
            },
            request=self.request,
        )
```

The fragment template could contain:

```django
<h2>Review {{ data_label }} records</h2>
<form method="post" action="{{ destination }}">
    {% csrf_token %}
    {% for name in selected_filters %}
        <input type="hidden" name="selected_filters" value="{{ name }}">
    {% endfor %}
    <label>Notes <textarea name="notes"></textarea></label>
    <button type="submit">Confirm</button>
</form>
```

When the handler does not return an HTTP response, the spreadsheet POST flow rebuilds
the page and includes `self.modal_html`. Set the attribute on the current view
instance as above; it is not persisted between requests. Alternatively,
`get_modal_html()` can call `render_to_string()` for a modal needed on a GET.
The view can also supply `modal_html` directly through `get_context_data()`.

The close button and Escape dismiss the popup without submitting its form.
The destination view handles validation, updates, and its own response or
redirect. If it re-renders the spreadsheet with a populated `modal_html`, the
modal opens again, which can be used to display validation errors.

The template inserts the fragment with `|safe`: supply trusted server-rendered
HTML, using normal Django escaping for user-provided values inside the fragment.
Pass `request=self.request` to `render_to_string()` so a POST form can render
its CSRF token. Keep any fragment-specific JavaScript in a separately loaded
script; `contributor_modal.js` only opens and closes the shell.

Implementation: `templates/contributor_spreadsheet.html`,
`static/Contributors/js/contributor_modal.js`, and the
`#spreadsheet-modal-dialog` rules in `spreadsheetview.css`. This modal is
independent of the details, contact-history, contribution, and filter dialogs.

## Queryset and context hooks

The base `get_queryset()` performs these steps:

1. Fetch `Contributor` objects and apply `contributor_type`, when configured.
2. Call `filter_queryset(queryset)`.
3. Annotate `latest_contact_timestamp` from contact-history comments.
4. Order by `contributor_name`.

Prefer `filter_queryset()` for filtering. It runs before the contact timestamp
annotation, so it cannot reference that annotation unless it adds its own.
For extra display annotations or related-object loading, extend
`get_queryset()` with `super()`:

```python
def get_queryset(self):
    queryset = super().get_queryset()
    return queryset.prefetch_related("contributions_set")
```

Replacing `get_queryset()` entirely bypasses the base filter hook and contact
annotation. The context builder expects each row to have
`latest_contact_timestamp`, so retain that annotation when replacing it.

For additional template context, retain the base context:

```python
def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context["title"] = "Sponsors"
    return context
```

The base context includes `contributors`, `historic_event_date`,
`show_contributions`, `contributor_type`, `extra_columns`,
`extra_toolbar_actions`, `filter_options`, `selected_filters`, `data_label`, and
`modal_html`. It also sets
`last_contact_date` on each contributor for display, hiding contacts on or
before the most recent past event date.

Simple class attributes can also be configured through `as_view()`, for example
`ContributorSpreadsheetView.as_view(contributor_type="Sponsor")`. Use a
subclass when adding handler methods or changing queryset behavior.

## Implementation and tests

For how the initially empty details popup is populated and edited, see
[Details popup construction](DETAILS_POPUP_GUIDE.md).

- View: `Contributors/views/general_views.py`
- Template: `Contributors/templates/contributor_spreadsheet.html`
- Toolbar and popup styles: `Contributors/static/Contributors/styles/spreadsheetview.css`
- Popup behavior: `Contributors/static/Contributors/js/contributor_filters.js`
- View-provided modal behavior: `Contributors/static/Contributors/js/contributor_modal.js`
- Toolbar selection behavior: `Contributors/static/Contributors/js/contributor_toolbar.js`
- Focused tests: `Contributors/tests/test_spreadsheet_class_view.py`

The focused tests cover class configuration, extra columns, action dispatch,
login protection, separators, icons, filter selection, and filter rendering.

### Spreadsheet scrolling

The spreadsheet page is a height-constrained flex column inside the team page's
card container. The toolbar and search controls sit outside
`.spreadsheet-grid-scroll`, which owns both table scrollbars. Native table
layout keeps headings and cells aligned; sticky header cells stay at the top
while rows scroll vertically. During horizontal scrolling the headings move
with their corresponding columns, while the toolbar stays in place. Toolbar
buttons wrap at narrow widths instead of making the page scroll sideways.
