from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from django.template.loader import render_to_string
from django.test import override_settings
from django.urls import resolve, reverse

from Contributors.views.general_views import ContributorSpreadsheetView


class ContributorSpreadsheetClassViewTests(SimpleTestCase):
    def test_details_history_starts_collapsed_and_close_is_outside_scrolling_content(self):
        from pathlib import Path
        from bs4 import BeautifulSoup
        from django.template import Context, Template
        # Render the actual dialog shell without unrelated page or database setup.
        source = (Path(__file__).parents[1]/'templates/contributor_spreadsheet.html').read_text()
        shell = '<dialog id="contributor-details-dialog"' + source.split(
            '<dialog id="contributor-details-dialog"',1)[1].split('</dialog>',1)[0] + '</dialog>'
        soup = BeautifulSoup(Template('{% load static %}'+shell).render(Context({'data_label':'Sponsor'})),'html.parser')
        self.assertFalse(soup.select_one('#contributor-history-panel').has_attr('open'))
        self.assertIsNotNone(soup.select_one('#contributor-history-panel > summary'))
        self.assertIsNotNone(soup.select_one('#contributor-details-scroll #contributor-details-history'))
        self.assertIsNone(soup.select_one('#contributor-details-scroll #contributor-details-close'))
        self.assertIsNotNone(soup.select_one('#contributor-details-form > .buttons #contributor-details-close'))

    def request(self, authenticated=True):
        request = RequestFactory().get(reverse("contributors:spreadsheet"))
        request.user = SimpleNamespace(is_authenticated=authenticated, is_active=True, has_perm=lambda permission: True)
        return request

    def test_url_uses_class_based_view_and_requires_login(self):
        self.assertIs(resolve(reverse("contributors:spreadsheet")).func.view_class, ContributorSpreadsheetView)
        self.assertEqual(ContributorSpreadsheetView.as_view()(self.request(False)).status_code, 302)

    def test_subclass_controls_details_flag_and_queryset(self):
        contributor = SimpleNamespace(latest_contact_timestamp=datetime(2026, 10, 9, tzinfo=timezone.utc))

        class NoContributionsSpreadsheet(ContributorSpreadsheetView):
            show_contributions = False
            historic_event_date = date(2026, 9, 1)

            def get_queryset(self):
                return [contributor]

        response = NoContributionsSpreadsheet.as_view()(self.request())
        self.assertFalse(response.context_data["show_contributions"])
        self.assertEqual(response.context_data["contributors"], [contributor])
        self.assertEqual(contributor.last_contact_date, date(2026, 10, 9))
        self.assertEqual(response.context_data["historic_event_date"], date(2026, 9, 1))
        self.assertTrue(ContributorSpreadsheetView.show_contributions)
        self.assertEqual(response.context_data["data_label"], "Contributor")
        self.assertIsNone(response.context_data["modal_html"])

    def test_as_view_can_override_flag(self):
        with patch.object(ContributorSpreadsheetView, "get_queryset", return_value=[]), \
             patch("Contributors.views.general_views.EventData.objects.filter") as events:
            events.return_value.aggregate.return_value = {"latest": None}
            response = ContributorSpreadsheetView.as_view(show_contributions=False)(self.request())
        self.assertFalse(response.context_data["show_contributions"])
        self.assertEqual(response.context_data["contributors"], [])

    def test_default_queryset_includes_every_type(self):
        queryset = ContributorSpreadsheetView().get_queryset()
        self.assertIsNone(ContributorSpreadsheetView.contributor_type)
        self.assertEqual(len(queryset.query.where.children), 1)
        self.assertEqual(queryset.query.where.children[0].lhs.target.name, 'is_hidden')
        self.assertFalse(queryset.query.where.children[0].rhs)
        self.assertIn("latest_contact_timestamp", queryset.query.annotations)

    def test_subclass_filters_by_configured_contributor_type(self):
        class SponsorSpreadsheet(ContributorSpreadsheetView):
            contributor_type = "sponsor"

        queryset = SponsorSpreadsheet().get_queryset()
        condition = queryset.query.where.children[0]
        self.assertEqual(condition.lhs.target.name, "contributor_type")
        self.assertEqual(condition.rhs, "sponsor")
        self.assertEqual(queryset.query.order_by, ("contributor_name",))

    def test_as_view_type_is_available_in_template_context(self):
        with patch.object(ContributorSpreadsheetView, "get_queryset", return_value=[]), \
             patch("Contributors.views.general_views.EventData.objects.filter") as events:
            events.return_value.aggregate.return_value = {"latest": None}
            response = ContributorSpreadsheetView.as_view(contributor_type="sponsor")(self.request())
        self.assertEqual(response.context_data["contributor_type"], "sponsor")

    def test_extra_columns_can_be_configured_or_computed_by_view(self):
        columns = ({"label": "Description", "template": "description_cell.html"},)
        with patch.object(ContributorSpreadsheetView, "get_queryset", return_value=[]), \
             patch("Contributors.views.general_views.EventData.objects.filter") as events:
            events.return_value.aggregate.return_value = {"latest": None}
            response = ContributorSpreadsheetView.as_view(extra_columns=columns)(self.request())
            self.assertEqual(response.context_data["extra_columns"], columns)

            class CustomSpreadsheet(ContributorSpreadsheetView):
                def get_extra_columns(self):
                    return columns if self.request.user.is_authenticated else ()

            response = CustomSpreadsheet.as_view()(self.request())
            self.assertEqual(response.context_data["extra_columns"], columns)
        self.assertEqual(ContributorSpreadsheetView.extra_columns, ())

    def test_toolbar_post_calls_method_with_all_post_data_and_reloads_rows(self):
        calls = []
        rows = []

        class ActionSpreadsheet(ContributorSpreadsheetView):
            historic_event_date = None
            extra_toolbar_actions = (
                {},
                {"name": "refresh", "label": "Refresh data", "handler": "refresh_data"},
                {},
            )

            def refresh_data(self, post_data):
                calls.append(post_data)
                rows.append(SimpleNamespace(latest_contact_timestamp=None))
                self.modal_html = '<form method="post" action="/confirm/"><button>Confirm</button></form>'

            def get_queryset(self):
                return list(rows)

        get_response = ActionSpreadsheet.as_view()(self.request())
        self.assertEqual(calls, [])
        self.assertEqual(get_response.context_data["contributors"], [])
        self.assertEqual(get_response.context_data["extra_toolbar_actions"][:len(ActionSpreadsheet.extra_toolbar_actions)], ActionSpreadsheet.extra_toolbar_actions)
        request = RequestFactory().post(reverse("contributors:spreadsheet"), {
            "toolbar_action": "refresh", "selected_contributor": ["1", "2"],
        })
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        response = ActionSpreadsheet.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertIs(calls[0], request.POST)
        self.assertEqual(calls[0].getlist("selected_contributor"), ["1", "2"])
        self.assertEqual(response.context_data["contributors"], rows)
        self.assertIn('action="/confirm/"', response.context_data["modal_html"])

    def test_toolbar_supports_callable_handlers_and_dynamic_action_list(self):
        calls = []

        class ActionSpreadsheet(ContributorSpreadsheetView):
            historic_event_date = None

            def refresh_data(self, post_data):
                calls.append((self.request, post_data))

            def get_extra_toolbar_actions(self):
                return ({"name": "refresh", "label": "Refresh", "handler": type(self).refresh_data},)

            def get_queryset(self):
                return []

        request = RequestFactory().post("/", {"toolbar_action": "refresh"})
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        response = ActionSpreadsheet.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [(request, request.POST)])

    def test_unknown_or_missing_toolbar_action_cannot_dispatch_arbitrary_methods(self):
        for data in ({}, {"toolbar_action": "get_queryset"}):
            request = RequestFactory().post("/", data)
            request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
            with patch.object(ContributorSpreadsheetView, "get_queryset") as queryset:
                response = ContributorSpreadsheetView.as_view(extra_toolbar_actions=({},))(request)
            self.assertEqual(response.status_code, 400)
            queryset.assert_not_called()

    def test_toolbar_post_requires_login(self):
        request = RequestFactory().post("/", {"toolbar_action": "refresh"})
        request.user = SimpleNamespace(is_authenticated=False)
        with patch.object(ContributorSpreadsheetView, "post") as post:
            response = ContributorSpreadsheetView.as_view()(request)
        self.assertEqual(response.status_code, 302)
        post.assert_not_called()

    def test_selection_required_action_rejects_empty_selection_before_handler(self):
        class SelectionSpreadsheet(ContributorSpreadsheetView):
            extra_toolbar_actions = (
                {"name": "selected", "label": "Selected", "handler": "handle_selected",
                 "requires_selection": True},
            )

            def handle_selected(self, post_data):
                pass

        for ids, expected in (([], 400), ([""], 400), (["7", "8"], 200)):
            request = RequestFactory().post("/", {"toolbar_action": "selected", "selected_contributor": ids})
            request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
            with patch.object(SelectionSpreadsheet, "handle_selected") as handler, \
                 patch.object(SelectionSpreadsheet, "get") as get:
                get.return_value = SimpleNamespace(status_code=200)
                response = SelectionSpreadsheet.as_view()(request)
                self.assertEqual(response.status_code, expected)
                if expected == 200:
                    handler.assert_called_once_with(request.POST)
                else:
                    handler.assert_not_called()
                    get.assert_not_called()

    def test_selected_filters_are_validated_and_used_by_queryset_hook(self):
        class FilterSpreadsheet(ContributorSpreadsheetView):
            filter_options = (
                {"name": "sponsor", "label": "Sponsors"}, {},
                {"name": "email", "label": "Has email"},
            )

            def filter_queryset(self, queryset):
                if "sponsor" in self.selected_filters:
                    queryset = queryset.filter(contributor_type="sponsor")
                return queryset

        view = FilterSpreadsheet()
        view.setup(RequestFactory().get("/", {"selected_filters": ["sponsor", "unknown", "sponsor"]}))
        view.request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        queryset = view.get_queryset()
        self.assertEqual(view.selected_filters, ["sponsor"])
        self.assertTrue(any(condition.rhs == "sponsor" for condition in queryset.query.where.children))
        self.assertIn("latest_contact_timestamp", queryset.query.annotations)

    def test_filter_selections_survive_toolbar_post_and_can_be_cleared(self):
        class FilterSpreadsheet(ContributorSpreadsheetView):
            historic_event_date = None
            filter_options = ({"name": "active", "label": "Active"},)
            extra_toolbar_actions = ({"name": "refresh", "label": "Refresh", "handler": "refresh"},)

            def refresh(self, data):
                pass

            def get_queryset(self):
                return []

        for method, data, expected in (
            ("get", {"selected_filters": "active"}, ["active"]),
            ("post", {"toolbar_action": "refresh", "selected_filters": "active"}, ["active"]),
            ("get", {}, []),
        ):
            request = getattr(RequestFactory(), method)("/", data)
            request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
            response = FilterSpreadsheet.as_view()(request)
            self.assertEqual(response.context_data["selected_filters"], expected)
        self.assertEqual(response.context_data["filter_options"][:len(FilterSpreadsheet.filter_options)], FilterSpreadsheet.filter_options)

    def test_filter_groups_normalize_conflicts_in_get_and_post(self):
        options = (
            {"name": "email", "label": "Has email", "group": "email_status"}, {},
            {"name": "no_email", "label": "No email", "group": "email_status"},
            {"name": "phone", "label": "Has phone", "group": "phone_status"},
            {"name": "independent", "label": "Independent"},
        )
        for method in ("get", "post"):
            view = ContributorSpreadsheetView(filter_options=options)
            view.setup(getattr(RequestFactory(), method)("/", {
                "selected_filters": ["no_email", "email", "phone", "independent", "unknown"],
            }))
            self.assertEqual(view.selected_filters, ["email", "phone", "independent"])

        view = ContributorSpreadsheetView(filter_options=options)
        view.setup(RequestFactory().get("/", {"selected_filters": "no_email"}))
        self.assertEqual(view.selected_filters, ["no_email"])

    @override_settings(TEMPLATES=[{
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {"loaders": [
            ("django.template.loaders.locmem.Loader", {
                "team_pages_base.html": "{% block SnappableSections %}{% endblock %}",
                "description_cell.html": "{{ contributor.description }}",
                "type_cell.html": "{{ contributor.contributor_type }}",
            }),
            "django.template.loaders.app_directories.Loader",
        ]},
    }])
    def test_extra_cells_render_before_actions_and_blank_row_stays_aligned(self):
        contributor = SimpleNamespace(
            pk=1, contributor_name="Acme", contact_name="Alex", phone="", email="",
            description="<description>", contributor_type="Sponsor",
        )
        context = {"can_add": True, "can_import": True, "can_export": True, "contributors": [contributor], "extra_columns": (
            {"label": "Description", "template": "description_cell.html"},
            {"label": "Type", "template": "type_cell.html"},
        )}
        html = render_to_string("contributor_spreadsheet.html", context)
        self.assertInHTML(
            '<th class="extra-column">Description</th><th class="extra-column">Type</th><th>Actions</th>',
            html,
        )
        self.assertInHTML(
            '<td class="extra-column">&lt;description&gt;</td><td class="extra-column">Sponsor</td>',
            html,
        )
        self.assertEqual(html.count('<td class="extra-column"></td>'), 2)
        context.pop("extra_columns")
        html = render_to_string("contributor_spreadsheet.html", context)
        self.assertNotIn('class="extra-column"', html)
        self.assertEqual(html.count('class="toolbar-separator"'), 2)
        self.assertLess(html.index('id="spreadsheet-new-button"'), html.index('class="toolbar-separator"'))
        download = html.index('title="Download CSV"')
        self.assertLess(download, html.index('class="toolbar-separator"', download))
        self.assertLess(html.index('class="toolbar-separator"'), html.index('class="search-icon"'))
        context["extra_toolbar_actions"] = (
            {"name": "refresh", "label": "Refresh data", "handler": "refresh_data"},
            {},
            {"name": "sync", "label": "Sync data", "handler": "sync_data",
             "icon": "Contributors/images/icons/upload-svgrepo-com.svg"},
        )
        context["csrf_token"] = "test-token"
        html = render_to_string("contributor_spreadsheet.html", context)
        self.assertInHTML(
            '<button class="toolbar-action" type="submit" name="toolbar_action" value="refresh" '
            'aria-label="Refresh data" title="Refresh data">Refresh data</button>', html,
        )
        self.assertInHTML(
            '<button class="toolbar-action" type="submit" name="toolbar_action" value="sync" '
            'aria-label="Sync data" title="Sync data">'
            '<img src="/static/Contributors/images/icons/upload-svgrepo-com.svg" alt="" width="24" height="24">'
            '</button>', html,
        )
        self.assertEqual(html.count('class="toolbar-separator"'), 4)
        self.assertLess(html.index('class="toolbar-separator"'), html.index('value="refresh"'))
        self.assertLess(html.index('value="refresh"'), html.rindex('class="toolbar-separator"'))
        self.assertLess(html.rindex('class="toolbar-separator"'), html.index('value="sync"'))
        self.assertIn('name="csrfmiddlewaretoken" value="test-token"', html)
        self.assertIn('<form method="post" class="extra-toolbar-actions">', html)
        self.assertNotIn('id="spreadsheet-filter-dialog"', html)
        context["filter_options"] = (
            {"name": "active", "label": "Active"}, {},
            {"name": "email", "label": "Has email"},
        )
        context["selected_filters"] = ["active"]
        html = render_to_string("contributor_spreadsheet.html", context)
        self.assertIn('id="spreadsheet-filter-button"', html)
        self.assertIn('funnel-svgrepo-com.svg', html)
        self.assertInHTML('<input type="checkbox" name="selected_filters" value="active" checked>', html)
        self.assertInHTML('<input type="checkbox" name="selected_filters" value="email">', html)
        self.assertInHTML('<input type="hidden" name="selected_filters" value="active">', html)
        self.assertIn('<hr>', html)
        self.assertInHTML('<input type="submit" value="Filter">', html)
        self.assertInHTML('<input type="button" id="spreadsheet-filter-cancel" value="Cancel">', html)
        context["data_label"] = "Sponsor"
        html = render_to_string("contributor_spreadsheet.html", context)
        self.assertIn('data-label="Sponsor"', html)
        self.assertIn('aria-label="Search sponsor records"', html)
        self.assertIn('aria-label="Filter sponsor records"', html)
        self.assertIn('title="Sponsor details"', html)
        self.assertIn('>Sponsor details</h2>', html)
        self.assertIn('>Confirmation and contribution history</summary>', html)
        self.assertNotIn('id="spreadsheet-modal-dialog"', html)
        context["modal_html"] = '<form method="post" action="/confirm/"><button>Confirm</button></form>'
        html = render_to_string("contributor_spreadsheet.html", context)
        self.assertIn('id="spreadsheet-modal-dialog"', html)
        self.assertInHTML(context["modal_html"], html)
        self.assertNotIn('&lt;form', html)
        context["extra_toolbar_actions"] = (
            {"name": "selected", "label": "Selected", "handler": "handle_selected",
             "requires_selection": True},
            {"name": "always", "label": "Always", "handler": "handle_always"},
        )
        html = render_to_string("contributor_spreadsheet.html", context)
        self.assertEqual(html.count('data-requires-selection="true" disabled'), 1)
