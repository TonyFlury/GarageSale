import logging
from django.conf import settings
from django.db import models, transaction
from django.db.models import Q, Max
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from GarageSale.models import EventData, CommunicationTemplate, TemplateAttachment
from django.utils.translation import gettext_lazy as _
from django.template import Template, Context

import typing

# Create your models here.

from django.utils.text import slugify
from django.conf import settings


class MarketerState(models.TextChoices):
    New = "NW", _("New")
    Invited = "IN", _("Invited")
    Confirmed = "CO", _("Confirmed")
    Rejected = "RE", _("Rejected")

StateTypes = typing.List[MarketerState]


class MostRecent(models.Manager):
    def get_queryset(self):
        return super().get_queryset().annotate(latest_timestamp=Max('timestamp'))

class History(models.Model):
    """History model for Craft Market state transitions"""

    class Meta:
        indexes = [models.Index(fields=['marketeer', 'timestamp', ]),
                   models.Index(fields=['marketeer', 'state', 'timestamp', ]), ]

    objects = models.Manager()
    most_recent = MostRecent()
    marketeer = models.ForeignKey('Marketer', on_delete=models.CASCADE, related_name="history")
    state = models.CharField(max_length=20, choices=MarketerState.choices, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)


def save_logo_to(instance, file_name: str) -> str:
    return f'marketeer_{instance.event.event_date.year}/{slugify(instance.trading_name)}_{file_name}'


class MarketerManager(models.Manager):
    def create(self, **obj_data):
        event = obj_data.get('event')
        try:
            instance = super().create(**obj_data)
            instance.state = MarketerState.New
            instance.save()
        except Exception as e:
            logging.error(
                f"Unable to create or save entry for Marketeer {obj_data.get("trading_name")} on {event.event_date} - {e}")
            raise e from None

        # Directly create a history entry rather than call update_state method
        try:
            History.objects.create(marketeer=instance, state=MarketerState.New)
        except Exception as e:
            logging.error(f"Unable to create History entry for Marketeer {self!s}  "
                          f"{MarketerState.New.label} @ {timezone.now()} - {e}")
        return instance

#ToDo - Make Marketer a many to many relationship to Events :
# Need a new Jira - and a new branch etc.
# Changes:
# 1 Change the Model - including recording state against the Markerter/Event.
#    1a New Model to hold the Relationship and the state and derived code.
#    1b Change the history model to link to the new model in 1a.
#    1c change to the Marketer model to remove the current link to the event data.
#    1d Managers on the Marketer model to emulate a simpler relationship.
#    1e Code generation is at the relationship level - not the Marketer - index on the code: expend the code to 8 digits ?
# 2 Change the test scripts:
#     2a build marketer without event data
#     2b Change Marketer state for a given event
# 3 Change the views - to ensure that the Views work as now, but the data is separated
#   3a Creation of Marketer wont be again the current event.
#   3b Invites, confirmation and rejection will be against the Marketer/Event relationship.
#   3c Views will need to be updated to reflect the new relationship.

class Marketer(models.Model):
    """Model to hold data for the Marketeer"""

    class Checksum:
        allowed_digits = '3456789ABCDEFGHJKLMPQRSTUVWXY'
        base_n = len(allowed_digits)

        @classmethod
        def validate_checksum(cls, code) -> bool:
            """Validate the checksum of a code
                :param code: The code to be validated
                :return: True if the checksum is valid, False otherwise
            """

            def to_decimal(value: str):
                if len(value) == 1:
                    return cls.allowed_digits.index(value)
                else:
                    return to_decimal(value[-1]) + cls.base_n * to_decimal(value[:-1])

            if (not code) or len(code) < 7:
                return False

            checksum = code[-1]
            # break the code into two sets of 3-digit values
            split_codes = [''.join([code[i], code[i + 2], code[i + 4]]) for i in [0, 1]]

            try:
                values = list(map(to_decimal, split_codes))
                checksum_value = to_decimal(checksum)
            except ValueError:
                # There will be a ValueError if the code contains invalid characters
                return False

            return checksum_value == sum(values) % 15

        @classmethod
        def generate_code(cls, email_address, timestamp) -> str | None:
            """Generate a valid code for this email address and timestamp
                :param email_address: The email address to be used in the code
                :param timestamp: The timestamp to be used in the code
                :return: The code generated based on the email address and timestamp
            """

            def to_base_n(num):
                """Convert a number to base n - with leading 'zeros'"""
                base_n = len(cls.allowed_digits)
                if num == 0:
                    return cls.allowed_digits[0]
                return (to_base_n(num // base_n).lstrip(cls.allowed_digits[0]) +
                        cls.allowed_digits[num % base_n])

            modulo = cls.base_n ** 2  # Allow 3 digits

            # Code builds a 6 digit alphanumeric code from invite timestamp and the marketer email.
            # Digit 0,2,4 are built from the 3^29 modular sum of the odd bytes
            # Digit 1,3,5 are built from the 3^29 modular sum of the even bytes
            # Digit 6 is a modular 15 sum of the even and odd digits
            sums = [0, 0]

            data = bytes(email_address, 'utf-8') + bytes(str(timestamp), 'utf-8')
            for index, byte in enumerate(data):
                if index % 2:
                    sums[0] += byte % modulo
                else:
                    sums[1] += byte % modulo

            checksum = (sums[0] + sums[1]) % 15
            checksum = f'{to_base_n(checksum):s}'

            # Convert each sum into base n
            non_interleaved = [f'{to_base_n(i):{cls.allowed_digits[0]}>3}' for i in sums]

            final = ''.join(non_interleaved[i][j] for j in [0, 1, 2] for i in [0, 1]) + checksum
            return final

    class Meta:
        """Customise permissions for the Craft Market """
        default_permissions = ()
        permissions = [
            ("can_view", "Is able to view Craft Market participants"),
            ("can_suggest", "Is able to suggest Craft Market participants"),
            ("can_manage", "Is able to manage Craft Market participants"),
        ]
        indexes = [models.Index(fields=['event', 'trading_name']),
                   models.Index(name='with_code', fields=['email', 'code'],
                                condition=Q(code__isnull=False, state=MarketerState.Invited))]

    objects = MarketerManager()
    event: EventData = models.ForeignKey(EventData, related_name="CraftMarketeers", on_delete=models.CASCADE)
    trading_name: str = models.CharField(max_length=120, blank=False)
    icon: str = models.ImageField(upload_to=save_logo_to, null=True, blank=True)
    email: str = models.EmailField(max_length=254, null=True, blank=False)
    contact_name: str = models.CharField(max_length=120, blank=True)
    website: str = models.URLField(max_length=254, null=True, blank=True)
    facebook: str = models.URLField(max_length=254, null=True, blank=True)
    instagram: str = models.URLField(max_length=254, null=True, blank=True)
    state: MarketerState = models.CharField(max_length=2, choices=MarketerState.choices, default=MarketerState.New)
    code: str | None = models.CharField(max_length=7, null=True)

    def save(self, *args, **kwargs):
        """Ensure that any save generates a new security code"""
        new_code = None if self.state != MarketerState.Invited \
                            else self.Checksum.generate_code(self.email,
                                        History.most_recent.filter(marketeer=self,
                                        state=MarketerState.Invited)[0].latest_timestamp)
        self.code = new_code
        super().save(*args, **kwargs)

    def is_valid_code(self, code):
        """Confirm that this code is valid for this marketeer - both the Checksum and that the code is right for this marketeer

            :param code: The code to be verified
            :return: True if the code is valid, False otherwise
        """
        cls = self.__class__
        return (cls.Checksum.validate_checksum(code) and
                (code == cls.Checksum.generate_code(self.email, History.most_recent.filter(
                                        marketeer=self, state=MarketerState.Invited)[0].latest_timestamp)))

    def __str__(self) -> str:
        """Readable friendly name of this Craft Marketeer"""
        return f'{self.trading_name}'

    def __repr__(self) -> str:
        """Useful friendly name of this Craft Marketeer"""
        return f'{self.event.event_date.year} - {self.id} :{self.trading_name}'

    def update_state(self, new_state:MarketerState, request:HttpRequest|None=None, send_email=True) -> MarketerState:
        """Encapsulate state transition:
                * support only valid transition
                 * add a History entry
                 * send an email if requested

            :param request: The request object
            :param new_state: The new state to transition to
            :param send_email: Whether to send an email on transition
            :return: The new state after transition
        """
        valid_transitions: dict[MarketerState, StateTypes] = {
            MarketerState.New: [MarketerState.Invited],
            MarketerState.Invited: [MarketerState.Confirmed, MarketerState.Rejected], }

        if new_state not in valid_transitions.get(self.state, {}):
            raise ValueError(f"Invalid transition from {self.get_state_display()} {new_state.label}") from None

        # Keep the object state and the history state in sync
        try:
            with transaction.atomic():
                try:
                    inst = History.objects.create(marketeer=self, state=new_state)
                except Exception as e:
                    logging.error(f"Unable to create History entry for Marketeer {self!s} "
                                  f"{new_state.label} @ {timezone.now()} - {e}")
                    raise e from None
                logging.info(f'Changing state of {self!s} from {MarketerState(self.state).label} to {new_state.label}')
                self.state = new_state
                self.save()
        except Exception as e:
            logging.error(f"Transaction aborted on {self!s} transition to {new_state.label} - {e} ")

        if send_email:
            category = settings.APPS_SETTINGS.get("CraftMarket", {}).get('EmailTemplateCategory', 'CraftMarket')
            context = self.common_context(request)
            app_settings = settings.APPS_SETTINGS.get("CraftMarket", {})
            context['from'] = app_settings.get('EmailFrom', 'CraftMarket@BranthamGarageSale.org.uk')
            context['bcc'] = ["Trustees@branthamGarageSale.org.uk", ]

            template = CommunicationTemplate.objects.filter(category=category,
                                                            transition=new_state.label,
                                                            use_from__lte=timezone.now()).order_by("-use_from").first()
            if template:
                try:
                    template.send_email(request, context=context)
                except Exception as e:
                    logging.error(f'Unable to send email for {self!s}  {category} transition to {new_state.label} - {e}')
                    return new_state
            else:
                logging.error(f'Valid Template not found for {category=} for transition to {new_state.label}')

        # Always return the new state - regardless of email success/failure
        return new_state

    def url(self, request: HttpRequest = None):
        """Generate the URL for this Marketeer"""
        local = reverse('CraftMarket:RSVP',kwargs={'marketer_code': self.code})

        if request:
            url = (request.build_absolute_uri(local) if self.code else "")
        else :
            url = ("https://127.0.0.1:8080" + local) if self.code else ""

        return url

    def common_context(self, request:HttpRequest=None):
        """Generate a context dictionary for this Marketeer and this event"""
        from_ = settings.APPS_SETTINGS.get('CraftMarket',{}).get('EmailFrom','trustees@BranthamGarageSale.org.uk')
        bcc = ['trustees@BranthamGarageSale.org.uk']
        return {'event_date': str(self.event.get_event_date_display()),
                                                   'trading_name': self.trading_name,
                                                    'contact_name': self.contact_name,
                                                    'supporting':','.join(self.event.supporting_organisations.values_list('name', flat=True)),
                                                    'url': self.url(request),
                                                    'email': [self.email],
                                                    'from': from_,
                                                    'bcc': bcc,}

