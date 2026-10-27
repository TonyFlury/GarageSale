# Entry-point navigation

Each feature registers its own label, URL, icon, permission, grouping and order.
Use the existing `nav_page` field for grouping; no separate route manifest is
needed. Lower order values appear first within a group. Equal values are sorted
alphabetically, ignoring case. Use 10, 20, 30 and so on for initial registrations,
leaving room to insert tasks between them. Duplicate priorities are valid. The
default order is 100, preserving existing alphabetical menus.

Function registration:

```python
register('Example task', 'Example:Root', static('Example/icon.svg'),
         permission='Example.view_task', needs_event=False,
         nav_page='Event participation', order=10)
```

Class registration:

```python
class Example(EntryPointMixin, View):
    entry_point_label = 'Example task'
    entry_point_url = 'Example:Root'
    entry_point_icon = static('Example/icon.svg')
    entry_point_permission = 'Example.view_task'
    entry_point_nav_page = 'Event participation'
    entry_point_order = 10
```

The team-page template renders the groups in page order using the existing tag:

```django
{% categoryList 'Event participation' heading=True %}
```

`heading=True` displays the group name only when the user can see entries in it.
Omit `heading` for existing unheaded submenu lists. The main groups are Overview,
Event participation, Prizes, Communications, Finance and funding, and Setup and
administration. Entries using the legacy default `TeamPage` appear under Other
tasks. Account submenus retain `AccountsEntryPoint` and their existing behaviour.
