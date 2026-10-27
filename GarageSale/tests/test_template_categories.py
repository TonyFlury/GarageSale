from types import SimpleNamespace
from datetime import date
from unittest.mock import patch

from django.contrib.staticfiles import finders
from django.core.exceptions import PermissionDenied
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse
from django_summernote.widgets import SummernoteWidget

from GarageSale.views.template_views import CommunicationTemplateCategories, CommunicationTemplateCreate, CommunicationTemplateEdit
from GarageSale.models import CommunicationTemplate
from TeamPageFramework.entry_point import get_entry_points


class CommunicationTemplateCategoryTests(SimpleTestCase):
    def setUp(self):
        warnings = patch("GarageSale.views.template_views.CommunicationTemplate.attachment_warnings_for", return_value={})
        warnings.start()
        self.addCleanup(warnings.stop)

    def request(self, authenticated=True, allowed=True):
        request = RequestFactory().get(reverse("TeamPages:CommunicationTemplates"))
        request.user = SimpleNamespace(is_authenticated=authenticated, is_active=True,
                                       has_perm=lambda permission: allowed, has_perms=lambda permissions: allowed)
        return request

    @patch("GarageSale.views.template_views.CommunicationTemplate.objects.order_by")
    def test_categories_are_sorted_and_unique(self, templates):
        templates.return_value.values_list.return_value = [(category, summary, date(2026, 1, 1), pk, "confirmed") for pk, (category, summary) in enumerate([
            ("Sponsors", "Invite"), ("Sponsors", "Invite"), ("Sponsors", None),
            ("Sponsors", ""), ("Sponsors", "Thanks"), ("Location", "created"),
        ], start=1)]
        response = CommunicationTemplateCategories.as_view()(self.request())
        self.assertEqual(response.context_data["template_categories"], [
            {"name": "Location"}, {"name": "Sponsors"},
        ])
        self.assertEqual(response.template_name, ["team_pages/communication_template_categories.html"])
        self.assertIsNone(response.context_data["selected_category"])
        self.assertEqual(response.context_data["templates"], [])

    @patch("GarageSale.views.template_views.CommunicationTemplate.objects.order_by")
    def test_category_selection_limits_summaries(self, templates):
        templates.return_value.values_list.return_value = [(category, summary, date(2026, 1, 1), pk, "confirmed") for pk, (category, summary) in enumerate([
            ("Location", "created"), ("Sponsors", "Invite"), ("Sponsors", "Thanks"),
        ], start=1)]
        for category, expected in (("Sponsors", ["Invite", "Thanks"]), ("Missing", [])):
            request = self.request()
            request.GET = request.GET.copy()
            request.GET["category"] = category
            response = CommunicationTemplateCategories.as_view()(request)
            self.assertEqual(response.context_data["templates"], [
                {"pk": pk, "summary": summary, "use_from": date(2026, 1, 1), "attachment_warning": "", "sub_category": "confirmed"} for pk, summary in enumerate(expected, start=2)
            ])
            self.assertEqual(response.context_data["selected_category"], category if expected else None)

    def test_url_and_access_controls(self):
        self.assertIs(resolve(reverse("TeamPages:CommunicationTemplates")).func.view_class, CommunicationTemplateCategories)
        self.assertEqual(CommunicationTemplateCategories.as_view()(self.request(authenticated=False)).status_code, 302)
        with self.assertRaises(PermissionDenied):
            CommunicationTemplateCategories.as_view()(self.request(allowed=False))

    def test_navigation_entry_is_in_communications_and_requires_no_event(self):
        user = SimpleNamespace(has_perm=lambda permission: permission == "GarageSale.view_communicationtemplate")
        entry = next(item for item in get_entry_points(user=user, nav_page="Communications")
                     if item["name"] == "Communication Templates")
        self.assertEqual(entry["url_path"], "TeamPages:CommunicationTemplates")
        self.assertFalse(entry["needs_event"])
        self.assertIsNotNone(finders.find("GarageSale/images/icons/folder-templates-svgrepo-com.svg"))

    @override_settings(TEMPLATES=[{
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {"loaders": [
            ("django.template.loaders.locmem.Loader", {
                "team_pages_base.html": "{% block SnappableSections %}{% endblock %}",
            }), "django.template.loaders.app_directories.Loader",
        ]},
    }])
    def test_listing_escapes_names_and_handles_empty_list(self):
        html = render_to_string("team_pages/communication_template_categories.html", {
            "template_categories": [{"name": "Sponsors <team>"}],
            "selected_category": "Sponsors <team>", "templates": [
                {"pk": 7, "summary": "Invite <now>", "use_from": date(2026, 10, 12)},
            ],
            "perms": {"GarageSale": {"add_communicationtemplate": True, "change_communicationtemplate": True, "delete_communicationtemplate": True}},
        })
        self.assertIn("Sponsors &lt;team&gt;", html)
        self.assertIn("Invite &lt;now&gt;", html)
        self.assertNotIn("Show transitions", html)
        self.assertIn('id="communication-template-list"', html)
        self.assertIn("Use from", html)
        self.assertIn("12/10/2026", html)
        self.assertNotIn('class="flex-table"', html)
        self.assertIn(reverse("TeamPages:CommunicationTemplateEdit", args=[7]), html)
        edit_url = reverse("TeamPages:CommunicationTemplateEdit", args=[7])
        self.assertEqual(html.count(f'href="{edit_url}"'), 3)
        self.assertIn("Create new template", html)
        self.assertIn(reverse("TeamPages:CommunicationTemplateDelete", args=[7]), html)
        self.assertEqual(html.count('<select'), 1)
        html = render_to_string("team_pages/communication_template_categories.html", {
            "template_categories": [{"name": "Sponsors"}],
        })
        self.assertIn("Choose a category to see its templates", html)
        self.assertNotIn("Invite", html)
        html = render_to_string("team_pages/communication_template_categories.html", {"template_categories": []})
        self.assertIn("No communication templates have been recorded", html)
        html = render_to_string("team_pages/communication_template_categories.html", {
            "template_categories": [{"name": "Sponsors"}], "selected_category": "Sponsors",
            "templates": [{"pk": 7, "summary": "Invitation", "use_from": date(2026, 10, 12)}],
        })
        self.assertEqual(html.count(f'href="{edit_url}"'), 3)


class CommunicationTemplateFormTests(SimpleTestCase):
    def setUp(self):
        atomic = patch("GarageSale.views.template_views.transaction.atomic")
        atomic.start()
        self.addCleanup(atomic.stop)

    def request(self, method="get", data=None, allowed=True):
        request = getattr(RequestFactory(), method)("/team_page/communication-templates/create/?category=Sponsors", data or {})
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: allowed, has_perms=lambda permissions: allowed)
        return request

    def template_data(self):
        return {"category": "Sponsors", "sub_category": "Invite", "summary": "Sponsor invitation",
                "subject": "Hello {{ contact_name }}", "html_content": "<p>Dear {{ contact_name }}</p>",
                "signature": "The team", "use_from": "2026-10-12",
                "attachments-TOTAL_FORMS": "0", "attachments-INITIAL_FORMS": "0"}

    def test_create_initial_values_and_urls(self):
        response = CommunicationTemplateCreate.as_view()(self.request())
        self.assertEqual(response.context_data["form"].initial["category"], "Sponsors")
        self.assertIsInstance(response.context_data["form"].fields["html_content"].widget, SummernoteWidget)
        self.assertIn("category=Sponsors", response.context_data["cancel_url"])
        self.assertIs(resolve(reverse("TeamPages:CommunicationTemplateCreate")).func.view_class, CommunicationTemplateCreate)
        self.assertIs(resolve(reverse("TeamPages:CommunicationTemplateEdit", args=[7])).func.view_class, CommunicationTemplateEdit)

    @override_settings(TEMPLATES=[{
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {"loaders": [
            ("django.template.loaders.locmem.Loader", {
                "team_pages_base.html": "{% block PageScripts %}{% endblock %}{% block SnappableSections %}{% endblock %}",
            }), "django.template.loaders.app_directories.Loader",
        ]},
    }])
    def test_create_form_renders_summernote_editor(self):
        response = CommunicationTemplateCreate.as_view()(self.request())
        html = render_to_string(response.template_name[0], response.context_data)
        self.assertIn("summernote", html)
        self.assertIn('name="html_content"', html)
        self.assertIn("Save template", html)
        context = dict(response.context_data)
        context.update(object=CommunicationTemplate(pk=7), perms={"GarageSale": {
            "add_communicationtemplate": True, "change_communicationtemplate": True, "delete_communicationtemplate": True,
        }})
        html = render_to_string(response.template_name[0], context)
        self.assertEqual(html.count('class="communication-template-actions"'), 1)
        self.assertIn('form="communication-template-form"', html)
        self.assertIn('form="communication-template-duplicate"', html)
        self.assertIn("Duplicate and edit", html)
        self.assertNotIn("Delete template", html)

    @patch("GarageSale.models.CommunicationTemplate.save")
    def test_create_saves_and_returns_to_selected_category(self, save):
        response = CommunicationTemplateCreate.as_view()(self.request("post", self.template_data()))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("TeamPages:CommunicationTemplates") + "?category=Sponsors")
        save.assert_called_once()

    @patch("GarageSale.models.CommunicationTemplate.save")
    @patch.object(CommunicationTemplateEdit, "get_object")
    def test_edit_updates_existing_template(self, lookup, save):
        template = CommunicationTemplate(pk=7, **{key: value for key, value in self.template_data().items()
                                                  if not key.startswith("attachments-")})
        lookup.return_value = template
        data = self.template_data()
        data["summary"] = "Updated invitation"
        data["category"] = "Changed category"
        response = CommunicationTemplateEdit.as_view()(self.request("post", data), pk=7)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(template.summary, "Updated invitation")
        self.assertEqual(template.sub_category, "Invite")
        self.assertEqual(template.category, "Sponsors")
        save.assert_called_once()

    @patch("GarageSale.models.CommunicationTemplate.save")
    def test_invalid_form_is_not_saved(self, save):
        data = self.template_data()
        data["subject"] = ""
        response = CommunicationTemplateCreate.as_view()(self.request("post", data))
        self.assertEqual(response.status_code, 200)
        self.assertIn("subject", response.context_data["form"].errors)
        save.assert_not_called()

    def test_create_and_edit_require_permissions(self):
        for view in (CommunicationTemplateCreate, CommunicationTemplateEdit):
            with self.assertRaises(PermissionDenied):
                view.as_view()(self.request(allowed=False))
