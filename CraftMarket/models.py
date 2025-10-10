from pipes import Template

import logging
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from GarageSale.models import EventData, CommunicationTemplate
from django.utils.translation import gettext_lazy as _
from django.core.mail import EmailMessage
from django.template import Template, Context

import typing

# Create your models here.

from django.utils.text import slugify


class MarketerState(models.TextChoices):
    New = "NW", _("New")
    Invited = "IN", _("Invited")
    Confirmed = "CO", _("Confirmed")
    Rejected = "RE", _("Rejected")

StateTypes = typing.List[MarketerState]

def save_logo_to( instance, file_name:str):
    return f'marketeer_{instance.event.event_date.year}/{slugify(instance.company_name)}_{file_name}'

class MarketerManager(models.Manager):
    def create(self, **obj_data):
        event = obj_data.get('event')
        try:
            instance = super().create(**obj_data)
            instance.state = MarketerState.New
            instance.save()
        except Exception as e:
            logging.error(f"Unable to create or save entry for Marketeer {obj_data.get("name")} on {event.event_date} - {e}")
            raise e from None

        # Directly create a history entry rather than call update_state method
        try :
            History.objects.create(marketeer=instance, state=MarketerState.New)
        except Exception as e:
            logging.error(f"Unable to create History entry for Marketeer {self!s}  "
                          f"{MarketerState.New.label} @ {timezone.now()} - {e}")
        return instance

class Marketer(models.Model):
    """Model to hold data for the Marketeer"""

    class Meta:
        """Customise permissions for the Craft Market """
        default_permissions = ()
        permissions = [
            ("can_view", "Is able to view Craft Market participants"),
            ("can_suggest", "Is able to suggest Craft Market participants"),
            ("can_manage", "Is able to manage Craft Market participants"),
        ]
        indexes = [models.Index(fields=['event', 'name'])]

    objects = MarketerManager()
    event:EventData = models.ForeignKey(EventData, related_name="CraftMarketeers", on_delete=models.CASCADE)
    name:str = models.CharField(max_length=120)
    icon:str = models.ImageField(upload_to="save_logo_to", null=True, blank=True)
    email:str = models.EmailField(max_length=254, null=True, blank=True)
    facebook:str = models.URLField(max_length=254, null=True, blank=True)
    instagram:str = models.URLField(max_length=254, null=True, blank=True)
    state:MarketerState = models.CharField(max_length=2, choices=MarketerState.choices, default=MarketerState.New)

    # def __init__(self, *args, **kwargs):
    #     """Ensure new entries are given their first entry"""
    #     super().__init__( *args, **kwargs)
    #     inst = History.objects.create(marketeer=self, state=MarketeerState.NoAction)

    def __str__(self) -> str:
        """Readable friendly name of this Craft Marketeer"""
        return f'{self.name}'

    def __repr__(self) -> str:
        """Useful friendly name of this Craft Marketeer"""
        return f'{self.event.event_date.year} - {self.id} :{self.name}'

    def update_state(self, new_state, send_email=True)  -> MarketerState:
        """Encapsulate state transition:
                * support only valid transition
                 * add a History entry
                 * send an email if requested"""
        valid_transitions:dict[MarketerState, StateTypes] = {
            MarketerState.New: [MarketerState.Invited],
            MarketerState.Invited: [MarketerState.Confirmed, MarketerState.Rejected],
             }

        if new_state not in valid_transitions[self.state]:
            raise ValueError(f"Invalid transition from {self.state.label} {new_state.label}") from None
        self.state = new_state

        with transaction.atomic():
            self.save()

            try:
                History.objects.create(marketeer=self, state=new_state)
            except Exception as e:
                logging.error(
                    f"Unable to create History entry for Marketeer {self!s} "
                    f"{new_state.label} @ {timezone.now()} - {e}")
                raise e from None

        if send_email:
            category = settings.APPS_SETTINGS.get("CraftMarket", {}).get('EmailTemplateCategory', 'CraftMarket')

            template = CommunicationTemplate.objects.filter(category=category,
                                                            transition=new_state,
                                                            use_from__lte=timezone.now() ).order_by("-use_from").first()
            if template:
                self.send_email(template)
            else:
                logging.error(
                    f"Unable to send transition email for {self!s} "
                    f"transition: {new_state.label!r}; Expected category: {category!r} - Valid Template not found")
                return new_state

        # Always return the new state - regardless of email success/failure
        return new_state

    def send_email(self, template):
        """Send email to this Marketeer"""
        if not template:
            logging.error("Template is None in Marketeer.send_email")
            raise ValueError(f'Template cannot be None')

        expected_category = settings.APPS_SETTINGS.get("CraftMarket", {}).get('EmailTemplateCategory', 'CraftMarket')

        if template.category != expected_category:
            logging.error(f"Invalid template for a Craft Market Email - Category {template.category}, expected {expected_category}")
            raise ValueError(f"Invalid template for a Craft Market Email - Category {template.category}, expected {expected_category}")

        body_template = Template(str(template.content))

        app_settings = settings.APPS_SETTINGS.get("CraftMarket", {})

        msg = EmailMessage(
              to = [self.email,],
              from_email =  settings.APPS_SETTINGS.get("CraftMarket", {}).get('EmailFrom', 'CraftMarket@BranthamGarageSale.org.uk'),
              subject = template.subject,
              body = body_template.render(Context({'name':self.name, 'email':self.email}, use_tz=True))
                     + "\n-- " + "\n" + template.signature,
              bcc =  ["Trustees@branthamGarageSale.org.uk",]
          )
        return msg.send()

class History(models.Model):
    """History model for Craft Market state transitions"""
    class Meta:
        indexes = [models.Index(fields=['marketeer', 'timestamp',]),
                   models.Index(fields=['marketeer', 'state', 'timestamp',]),]

    marketeer = models.ForeignKey(Marketer, on_delete=models.CASCADE, related_name="history")
    state = models.CharField(max_length=20, choices=MarketerState.choices, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)