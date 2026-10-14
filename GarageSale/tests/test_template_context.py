from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from GarageSale.models import CommunicationTemplate


@override_settings(ALLOWED_HOSTS=["templates.example.com"])
class TemplateBaseURLTests(SimpleTestCase):
    def setUp(self):
        self.template = CommunicationTemplate(
            category="Sponsors", sub_category="confirmed", summary="Thanks", use_from=date(2026, 10, 13),
            subject="Visit {{ base_url }}", html_content='<a href="{{ base_url }}support/">Support</a>', signature="Team",
        )
        self.request = RequestFactory().get('/team_page/templates/?category=Sponsors',
                                            secure=True, HTTP_HOST='templates.example.com:8443')
        self.request.current_event = None

    def test_email_subject_and_body_use_website_root(self):
        context = {"email": ["sponsor@example.com"], "from": "team@example.com"}
        message = self.template.render_template_as_email(self.request, context)
        self.assertEqual(message.subject, "Visit https://templates.example.com:8443/")
        self.assertIn('href="https://templates.example.com:8443/support/"', message.alternatives[0][0])

    @patch.object(CommunicationTemplate, "pdf_from_template_str")
    @patch.object(CommunicationTemplate, "pdf_header_template", return_value="header")
    def test_pdf_header_and_body_receive_website_root(self, header, pdf):
        context = {}
        self.template.render_template_as_pdf(self.request, context)
        self.assertEqual(header.call_args.args[0]["base_url"], "https://templates.example.com:8443/")
        self.assertEqual(pdf.call_args.args[0]["base_url"], "https://templates.example.com:8443/")

    def test_without_request_base_url_is_empty(self):
        context = {}
        self.template.render_template_as_email(None, context)
        self.assertEqual(context["base_url"], "")

    def test_event_defaults_are_available_to_email_and_pdf_for_any_category(self):
        organisations = Mock()
        organisations.order_by.return_value = [
            SimpleNamespace(name="Hospice", logo=SimpleNamespace(url="/media/hospice.svg")),
            SimpleNamespace(name="Food Bank", logo=None),
        ]
        self.request.current_event = SimpleNamespace(
            event_date=date(2027, 6, 12), event_logo=SimpleNamespace(url="/media/event.svg"),
            supporting_organisations=organisations, get_event_date_display=lambda: "12 June 2027",
        )
        self.template.category = "OtherApp"
        self.template.subject = "{{ year }}: {{ supporting }}"
        context = {"from": "other@example.com", "email": ["recipient@example.com"]}
        message = self.template.render_template_as_email(self.request, context)
        self.assertEqual(message.subject, "2027: Hospice and Food Bank")
        self.assertEqual(message.from_email, "other@example.com")
        self.assertEqual(context["event_date"], "12 June 2027")
        self.assertEqual(context["event_logo"], "https://templates.example.com:8443/media/event.svg")
        self.assertIn("https://templates.example.com:8443/media/hospice.svg", context["supporting_icons"])
        with patch.object(CommunicationTemplate, "pdf_from_template_str") as pdf, \
             patch.object(CommunicationTemplate, "pdf_header_template", return_value="header"):
            self.template.render_template_as_pdf(self.request, {})
        self.assertEqual(pdf.call_args.args[0]["supporting"], "Hospice and Food Bank")
        self.assertEqual(pdf.call_args.args[0]["year"], "2027")
        organisations.order_by.assert_called_with("index", "pk")

    def test_explicit_values_override_defaults_and_no_sender_is_inferred(self):
        context = {"year": "Custom year", "base_url": "https://custom.example/", "supporting": "Custom charity"}
        self.template.render_template_as_email(self.request, context)
        self.assertEqual(context["year"], "Custom year")
        self.assertEqual(context["base_url"], "https://custom.example/")
        self.assertEqual(context["supporting"], "Custom charity")
        self.assertNotIn("from", CommunicationTemplate.default_context(self.request))
