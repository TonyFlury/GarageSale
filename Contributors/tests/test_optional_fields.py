from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from Contributors.models import Contributor
from Contributors.views.rest_api import _validate_contributor


class ContributorOptionalFieldTests(SimpleTestCase):
    def test_name_and_type_are_sufficient(self):
        contributor = Contributor(contributor_name="Acme", contributor_type="Sponsor")
        contributor.full_clean(validate_unique=False, validate_constraints=False)
        self.assertEqual(_validate_contributor(contributor), {})

    def test_only_name_and_type_are_required(self):
        with self.assertRaises(ValidationError) as raised:
            Contributor().clean_fields()
        self.assertEqual(set(raised.exception.message_dict), {"contributor_name", "contributor_type"})

    def test_contact_name_can_change_with_other_details_empty(self):
        contributor = Contributor(contributor_name="Acme", contributor_type="Sponsor", contact_name="Alex")
        self.assertEqual(_validate_contributor(contributor), {})

    def test_optional_email_must_be_valid_when_supplied(self):
        contributor = Contributor(contributor_name="Acme", contributor_type="Sponsor", email="invalid")
        self.assertIn("email", _validate_contributor(contributor))
