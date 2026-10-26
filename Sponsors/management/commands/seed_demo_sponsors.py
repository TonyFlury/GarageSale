"""Create development sponsors and original SVG logos; see Sponsors/DEMO_SPONSORS.md."""
import json
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils.text import slugify

from Contributors.models import Contributor, ContributorEvent, ContributorHistory, Contributions
from Contributors.views.general_views import get_current_contribution_event


COMPANIES = (
    ("Willow & Wren", "HOME & GARDEN", "#315d48", "wide", "1500"),
    ("Copper Finch", "COFFEE ROASTERS", "#a35432", "wide", "1000"),
    ("Northfield Works", "BUILDING BETTER", "#234f73", "wide", "750"),
    ("Meadow & Mill", "LOCAL FOOD, GOOD COMPANY", "#807237", "wide", "500"),
    ("Foxglove", "FLORAL STUDIO", "#8b526e", "portrait", None),
    ("Harbour Cycles", "FIND YOUR WAY", "#246974", "wide", None),
    ("Little Acorn", "FAMILY NURSERY", "#748943", "square", None),
    ("Bracken Books", "A WORLD OF STORIES", "#78614d", "portrait", None),
    ("Bluebell Bakery", "BREAD • CAKE • JOY", "#586b9c", "wide", None),
    ("Hearth & Hound", "COUNTRY KITCHEN", "#a35e49", "square", None),
    ("Oakline", "JOINERY & DESIGN", "#5a6652", "portrait", None),
    ("Pebble & Pine", "GIFTS FOR EVERY DAY", "#55847a", "wide", None),
    ("Amber Lane", "LOCAL INDEPENDENT SHOP", "#af812a", "square", None),
    ("Fernwood", "GARDEN CARE", "#4f784c", "portrait", None),
    ("Silver Kite", "CREATIVE STUDIO", "#6d7190", "square", None),
    ("Moss & Stone", "LANDSCAPE DESIGN", "#6c755c", "wide", None),
    ("The Kindred Table", "NEIGHBOURHOOD DINING", "#a06c50", "portrait", None),
    ("Bramble Studio", "HANDMADE LOCALLY", "#8a6181", "square", None),
)

# Measured SVG artwork bounds, including a small margin, for these fixed demo designs.
LOGO_BOUNDS = json.loads(Path(__file__).with_name("demo_logo_bounds.json").read_text(encoding="utf-8"))


def logo_svg(name, tagline, colour, shape, index):
    width, height = {"wide": (640, 180), "square": (340, 340), "portrait": (280, 380)}[shape]
    if shape == "wide":
        symbol_x, symbol_y, text_x, text_y = 80, 85, 165, 83
        size = min(44, 410 / (len(name) * .58))
        anchor = "start"
    else:
        symbol_x, symbol_y, text_x, text_y = width / 2, height * .31, width / 2, height * .65
        size = min(34, (width - 24) / (len(name) * .58))
        # Keep stacked wordmarks close to the symbol rather than spacing them by canvas height.
        text_y = symbol_y + 50 + size * .8 + 12
        anchor = "middle"
    symbols = (
        '<circle r="44" fill="none" stroke-width="5"/><path d="M-22 20L0-25L22 20M-12 1H12" fill="none" stroke-width="5"/>',
        '<path d="M-38 20Q-40-40 0-40Q40-40 38 20ZM-24 20V-1Q0-35 24-1V20" fill="none" stroke-width="5"/><path d="M-42 30H42" stroke-width="5"/>',
        '<path d="M0-46L42 0L0 46L-42 0Z" fill="none" stroke-width="5"/><circle r="13" stroke="none"/>',
        '<path d="M-35 30Q-55-20-5-43Q35-35 30 4Q20 37-35 30Z" fill="none" stroke-width="5"/><path d="M-30 32L20-22M-8 9V-15M-8 9H18" fill="none" stroke-width="4"/>',
        '<circle r="33" fill="none" stroke-width="5"/><path d="M0-50V-39M0 39V50M-50 0H-39M39 0H50M-35-35L-27-27M27 27L35 35M-35 35L-27 27M27-27L35-35" stroke-width="5"/>',
        '<path d="M-42 26L-15-27L10 13L28-18L47 26Z" fill="none" stroke-width="5"/><circle cx="27" cy="-36" r="8" stroke="none"/>',
    )
    crop_x, crop_y, crop_width, crop_height = LOGO_BOUNDS.get(
        f"{slugify(name)}.svg", [0, 0, width, height],
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{crop_width}" height="{crop_height}" viewBox="{crop_x} {crop_y} {crop_width} {crop_height}">
<title>{escape(name)} — fictional demonstration company</title>
<rect width="{width}" height="{height}" rx="8" fill="white"/>
<g transform="translate({symbol_x} {symbol_y})" fill="{colour}" stroke="{colour}" stroke-linecap="round" stroke-linejoin="round">{symbols[index % len(symbols)]}</g>
<text x="{text_x}" y="{text_y}" text-anchor="{anchor}" font-family="Georgia,serif" font-size="{size}" fill="{colour}">{escape(name)}</text>
<text x="{text_x}" y="{text_y + 28}" text-anchor="{anchor}" font-family="Arial,sans-serif" font-size="10" letter-spacing="1.2" fill="{colour}">{escape(tagline)}</text>
</svg>'''


class Command(BaseCommand):
    help = "Seed 18 fictional sponsors for the active event in a local development database."

    def handle(self, *args, **options):
        if not settings.DEBUG or connection.settings_dict.get("HOST", "") not in ("", "localhost", "127.0.0.1", "::1"):
            raise CommandError("Demo sponsors may only be seeded in a local database with DEBUG enabled.")
        event = get_current_contribution_event()
        if event is None:
            raise CommandError("No active event exists. Activate an event before seeding demo sponsors.")
        logo_directory = Path(settings.MEDIA_ROOT) / "contributors" / "demo_sponsors"
        logo_directory.mkdir(parents=True, exist_ok=True)
        created_count = 0
        with transaction.atomic():
            for index, (name, tagline, colour, shape, cash) in enumerate(COMPANIES):
                logo_name = f"contributors/demo_sponsors/{slugify(name)}.svg"
                (logo_directory / f"{slugify(name)}.svg").write_text(
                    logo_svg(name, tagline, colour, shape, index), encoding="utf-8",
                )
                sponsor, created = Contributor.objects.get_or_create(
                    contributor_type="Sponsor", contributor_name=f"[DEMO] {name}",
                    defaults={
                        "contact_name": ("Alex Morgan", "Sam Taylor", "Jamie Reed")[index % 3],
                        "email": f"hello@{slugify(name)}.example.invalid" if index % 3 else "",
                        "phone": f"01632960{index:03d}" if index % 4 else "",
                        "description": f"Fictional demonstration sponsor for development only. {name} — {tagline.lower()}. "
                                       "This sample company and its logo are not associated with a real business.",
                        "icon": logo_name,
                        "socials": {"website": f"https://{slugify(name)}.example.invalid"} if index % 2 else {},
                    },
                )
                if not sponsor.description.startswith("Fictional demonstration sponsor for development only."):
                    raise CommandError(f"Refusing to reuse an unrecognised record named {sponsor.contributor_name}.")
                created_count += int(created)
                if created:
                    ContributorHistory.objects.create(
                        contributor=sponsor, event_category="Data", event_type="Create", related_event=event,
                        details="Created by seed_demo_sponsors for development preview.",
                    )
                latest = ContributorEvent.objects.filter(contributor=sponsor, event=event).order_by("-timestamp", "-pk").first()
                if latest is None or latest.status != "Confirmed":
                    ContributorEvent.objects.create(contributor=sponsor, event=event, status="Confirmed")
                if cash:
                    Contributions.objects.get_or_create(contributor=sponsor, event=event, cash=True, gift='', amount=Decimal(str(cash)))
                if not cash or index % 4 == 0:
                    gift = ("A £25 gift voucher", "A hamper of local treats", "Two tickets to a workshop", "A family afternoon tea voucher")[index % 4]
                    Contributions.objects.get_or_create(contributor=sponsor, event=event, cash=False, gift=gift)
        self.stdout.write(self.style.SUCCESS(
            f"Created {created_count} demo sponsors; {len(COMPANIES)} confirmed for {event}. "
            f"Logos: {logo_directory}. All company names start with [DEMO]."
        ))
