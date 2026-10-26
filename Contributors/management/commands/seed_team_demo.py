"""Build the small, repeatable contributor demonstration described in TEAM_DEMO.md."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from xml.sax.saxutils import escape

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from Contributors.models import Contributor, ContributorEvent, ContributorHistory, Contributions
from Contributors.views.general_views import get_current_contribution_event
from GarageSale.models import EventData


# A separate namespace keeps this set distinct from the older seed_demo_sponsors
# command. The description marker prevents accidentally adopting a real record.
PREFIX = "[TEAM DEMO] "
MARKER = "Fictional seed_team_demo contributor."
SPONSORS = (
    ("Alder Hardware", "Alex Morgan", "#315d48", "AH"),
    ("Bramble Bakery", "Sam Taylor", "#a35432", "BB"),
    ("Cedar Books", "Jamie Reed", "#234f73", "CB"),
    ("Daisy Florist", "Robin Ellis", "#8b526e", "DF"),
    ("Elm Cycles", "Chris Lane", "#246974", "EC"),
    ("Fern Coffee", "Pat Casey", "#807237", "FC"),
    ("Grove Gardens", "Jo Parker", "#748943", "GG"),
    ("Hazel Homewares", "Charlie Bell", "#6d7190", "HH"),
)
TRADERS = (
    ("Juniper Pottery", "Morgan Lee"),
    ("Maple Textiles", "Casey Green"),
    ("Rowan Jewellery", "Taylor Brook"),
    ("Willow Woodcraft", "Drew Harper"),
)


def sponsor_logo(name, colour, initials):
    """Create an original vector wordmark without external assets or packages."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="180" viewBox="0 0 640 180">
<title>{escape(name)} — fictional demo sponsor</title>
<rect width="640" height="180" rx="16" fill="#fff"/>
<circle cx="80" cy="90" r="58" fill="{colour}"/>
<text x="80" y="103" text-anchor="middle" font-family="sans-serif" font-size="36" fill="#fff">{escape(initials)}</text>
<text x="158" y="87" font-family="sans-serif" font-size="32" fill="{colour}">{escape(name)}</text>
<text x="160" y="119" font-family="sans-serif" font-size="16" fill="{colour}">FICTIONAL COMMUNITY SPONSOR</text>
</svg>'''


class Command(BaseCommand):
    help = "Create 8 fictional sponsors and 4 traders for the current event, with logos, contacts and donations."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report proposed data without saving records or logos.")
        parser.add_argument("--user-email", help="Attribute new contact and status records to an existing user.")

    def handle(self, *args, **options):
        event = get_current_contribution_event()

        # Use exactly the same event selection as the contributor spreadsheets.
        # Expired events hide confirmation indicators and cannot support live RSVP.
        if event is None:
            raise CommandError("No current event exists. Set an event's Use from date before today, then retry.")
        if event.event_date < timezone.localdate():
            raise CommandError("The current event has passed. Activate an upcoming event before creating the demo.")
        user = self._user(options.get("user_email"))
        self.stdout.write(f"Database: {Contributor.objects.db}; current event: {event}")

        # Check every reserved name before writing anything. No real contributors
        # are renamed, updated or deleted, including same-name records of another type.
        self._check_names()
        created = 0
        with transaction.atomic():
            for index, (name, contact, colour, initials) in enumerate(SPONSORS):
                sponsor, is_new = self._contributor(name, contact, "Sponsor", index)
                created += int(is_new)
                logo_name = f"contributors/team_demo/{slugify(name)}.svg"

                # The file is installed only after a successful database commit.
                # Dry runs roll back without scheduling storage writes at all.
                if not sponsor.icon:
                    sponsor.icon = logo_name
                    sponsor.save(update_fields=["icon"])
                if not options["dry_run"] and sponsor.icon.name == logo_name:
                    transaction.on_commit(
                        lambda path=logo_name, content=sponsor_logo(name, colour, initials), storage=sponsor.icon.storage:
                        self._save_logo(storage, path, content)
                    )

                # Exactly the first four sponsors start with contact history.
                # Give two of them multiple contacts, including two on one date,
                # to demonstrate contact filters and append-only CSV duplicate checks.
                if index < 4:
                    self._contact(sponsor, event, user, "Called to discuss sponsorship.")
                if index < 2:
                    self._contact(sponsor, event, user, "Emailed the event information and donation options.")

                # The first two sponsors are confirmed for this event, one cash
                # donor and one non-cash donor. No other sponsors receive a status.
                if index < 2:
                    self._status(sponsor, event, user, "Confirmed")
                    Contributions.objects.get_or_create(
                        contributor=sponsor, event=event, cash=index == 0,
                        gift="" if index == 0 else "Gift hamper for the prize draw",
                        defaults={"amount": Decimal("250.00") if index == 0 else Decimal("50.00"),
                                  "classification": Contributions.Classification.UNCLASSIFIED if index == 0
                                  else Contributions.Classification.PRIZE_DRAW},
                    )

            for index, (name, contact) in enumerate(TRADERS):
                trader, is_new = self._contributor(name, contact, "Marketer", index + 8)
                created += int(is_new)

                # Invitations are event status records; no email is sent. The
                # application can generate RSVP links from these records normally.
                if index < 2:
                    self._status(trader, event, user, "Invited")

            if options["dry_run"]:
                transaction.set_rollback(True)

        action = "Would create" if options["dry_run"] else "Created"
        self.stdout.write(self.style.SUCCESS(
            f"{action} {created} contributors. Demo set: 8 sponsors (4 contacted, 4 uncontacted), "
            "2 confirmed donors (£250 cash; £50 hamper), 4 market traders (2 invited)."
        ))
        self.stdout.write("All names begin [TEAM DEMO]. Reruns preserve existing records and demo edits; no emails are sent.")

    @staticmethod
    def _user(email):
        """Allow attribution without creating users or changing their permissions."""
        if not email:
            return None
        user = get_user_model().objects.filter(email=email).first()
        if user is None:
            raise CommandError(f"No user exists with email {email}.")
        return user

    @staticmethod
    def _check_names():
        """Reject collisions before creating the first contributor or logo."""
        expected = {PREFIX + row[0]: kind for rows, kind in ((SPONSORS, "Sponsor"), (TRADERS, "Marketer"))
                    for row in rows}
        seen = set()
        for contributor in Contributor.objects.filter(contributor_name__in=expected):
            if (contributor.contributor_name in seen or contributor.contributor_type != expected[contributor.contributor_name]
                    or not contributor.description.startswith(MARKER)):
                raise CommandError(f"Reserved demo name belongs to an unexpected or duplicate record: {contributor.contributor_name}")
            seen.add(contributor.contributor_name)

    @staticmethod
    def _contributor(name, contact, kind, index):
        """Create once, then retain any edits made while demonstrating the app."""
        return Contributor.objects.get_or_create(
            contributor_name=PREFIX + name, contributor_type=kind,
            defaults={
                "contact_name": contact, "email": f"{slugify(name)}@example.invalid",
                "phone": f"01632960{index:03d}",
                "description": f"{MARKER} {name}; created for team demonstrations.",
                "socials": {"website": f"https://{slugify(name)}.example.invalid"},
            },
        )

    @staticmethod
    def _contact(contributor, event, user, note):
        """Seed notes after the last past event so contacted filters show them."""
        today = timezone.localdate()
        previous = EventData.objects.filter(event_date__lt=today).order_by("-event_date").first()
        day = max(today - timedelta(days=2), previous.event_date + timedelta(days=1)) if previous else today - timedelta(days=2)

        # Date is a creation default, not part of identity: running tomorrow must
        # not create a second copy of the same sample note.
        ContributorHistory.objects.get_or_create(
            contributor=contributor, event_category="Contact", event_type="Comment", related_event=event, details=note,
            defaults={"user": user, "timestamp": timezone.make_aware(datetime.combine(day, time(hour=10)))},
        )

    @staticmethod
    def _status(contributor, event, user, status):
        """Do not append duplicate statuses or override subsequent demo actions."""
        if not ContributorEvent.objects.filter(contributor=contributor, event=event).exists():
            ContributorEvent.objects.create(contributor=contributor, event=event, status=status, user=user)

    @staticmethod
    def _save_logo(storage, path, content):
        """Use the ImageField storage backend and keep filenames stable on reruns."""
        if not storage.exists(path):
            storage.save(path, ContentFile(content.encode("utf-8")))
