#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.models.py : 

Summary :
    
    
Use Case :

"""
import datetime

import weasyprint
import mimetypes
import io
import logging
import bs4
from django.contrib.staticfiles import finders

from django.core.mail import EmailMultiAlternatives
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models import Subquery
from django.http import HttpRequest
from django.utils import timezone
from django.utils.html import format_html
from django.template import Template, Context, Engine
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django_quill.fields import QuillField
from django.contrib.auth.models import User
from django.contrib.auth.models import AbstractUser

from calendar import day_name, month_name
import logging

logger = logging.getLogger('GarageSale.models')
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.WARNING)

logging.getLogger('ttFont').addHandler(logging.NullHandler())
logging.getLogger('loggingTools').addHandler(logging.NullHandler())

# ToDo - convert QuillField to Summernote
class MOTD(models.Model):
    """Holder for Message of the Day"""
    use_from = models.DateField()
    content = models.TextField(default='')
    synopsis = models.CharField(max_length=256, null=True)

    @staticmethod
    def get_current():
        try:
            return MOTD.objects.filter(use_from__lte = datetime.date.today()).latest('use_from')
        except MOTD.DoesNotExist:
            return None

def save_supported_logo_to(instance, filename):
    return f'supported_logo_{instance.name}/{filename}'


class ByIndex(models.Manager):
    def get_queryset(self):
        return super().get_queryset().order_by('index')

class Supporting(models.Model):
    objects = ByIndex()
    name = models.CharField(max_length = 100)
    logo = models.FileField(upload_to=save_supported_logo_to, null=True, blank=True)
    website = models.URLField()
    index = models.IntegerField(default=100)
    def __str__(self):
        return self.name


class CurrentFuture(models.Manager):
    def get_queryset(self):
        return (super().get_queryset().filter(event_date__gte=datetime.date.today())
                                      .order_by('event_date'))


def save_event_logo_to(instance, filename):
    return f'event_logo_{instance.event_date.year}-{instance.event_date.month}/{filename}'


class EventData(models.Model):
    """Various Event settings - critical data
    """
    objects = models.Manager()
    CurrentFuture = CurrentFuture()
    event_logo = models.FileField(null=True, upload_to=save_event_logo_to)    # The specific logo for this event
    event_date = models.DateField()                                             # The date of the actual sale event
    open_billboard_bookings = models.DateField(null=True)                                # When Billboard bookings open
    close_billboard_bookings = models.DateField(null=True)                               # When Billboard bookings close
    open_sales_bookings = models.DateField(null=True)                                    # When Sales bookings open
    close_sales_bookings = models.DateField(null=True)                                   # When Sales bookings open
    use_from = models.DateField()
    supporting_organisations = models.ManyToManyField(Supporting, related_name='by_event', blank=True)
    myGoogleMapURL = models.URLField(null=True, blank=True)

    def allow_ad_board_bookings(self):
        """Whether to allow ad-board bookings
           returns True/False depending on whether today is in the booking window
        """
        return self.open_billboard_bookings <= datetime.date.today() <= self.close_billboard_bookings

    def allow_sale_bookings(self):
        """Whether to allow ad-board bookings
           returns True/False depending on whether today is in the booking window
        """
        return self.open_sales_bookings <= datetime.date.today() <= self.close_sales_bookings

    def get_event_date_display(self):
        return f'{day_name[self.event_date.weekday()]} {self.event_date.day} {month_name[self.event_date.month]}, {self.event_date.year}'

    def __str__(self):
            return f'{self.get_event_date_display()}'


    @staticmethod
    def get_current():
        try:
            e = (EventData.objects.filter(use_from__lte = datetime.date.today(),
                                             event_date__gte = datetime.date.today()).earliest('event_date') )
            return e
        except EventData.DoesNotExist:
            return None


class PrizeDrawWinner(models.Model):
    """Winner and optional contact details for a single donated Prize Draw item."""

    contribution = models.OneToOneField(
        "Contributors.Contributions", on_delete=models.CASCADE, related_name="prize_draw_winner",
        limit_choices_to={"cash": False, "classification": "prize_draw"},
    )
    name = models.CharField(max_length=200, blank=True)
    ticket_number = models.CharField(max_length=50)
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} — ticket {self.ticket_number}"

    def clean(self):
        super().clean()
        if not self.contribution_id:
            return
        try:
            contribution = self.contribution
        except ObjectDoesNotExist:
            return  # Foreign-key validation reports a missing contribution.
        if contribution.cash or contribution.classification != "prize_draw":
            raise ValidationError({"contribution": "Only non-cash Prize Draw items can have a winner."})

def save_template_attachment_to(instance, filename):
    return f'template_attachments/{instance.template.category}/{instance.template.sub_category or "general"}/{instance.template.use_from.isoformat()}/{filename}'

class TemplateAttachment(models.Model):
    template = models.ForeignKey("CommunicationTemplate", on_delete=models.CASCADE, related_name='attachments')
    upload = models.BooleanField(default=False)
    template_name = models.CharField(max_length=100, verbose_name='Name')
    attached_file = models.FileField(upload_to=save_template_attachment_to, blank=True, null=True)


    def __str__(self):
        return f'{self.id} {self.upload} {self.template_name if not self.upload else self.attached_file}'

    def warning_text(self):
        if self.upload:
            return ''
        template_with_name = CommunicationTemplate.objects.filter(category=self.template.category,
                                                                  sub_category=self.template_name)
        template_in_date = CommunicationTemplate.objects.filter(category=self.template.category,
                                                                sub_category=self.template_name,
                                                                use_from__lte=self.template.use_from)

        match template_with_name.exists(), template_in_date.exists():
            case False, _:
                return 'Named template is missing'
            case True, False:
                return 'Template is out of date'
            case _,_:
                return ""

    def warning_as_html_fragment(self):
        text = self.warning_text()
        if text:
            return f'<span class="tooltip"><image style="width:20px;vertical-align:middle;" id="warning{self.id}" src="/static/GarageSale/images/icons/warning-svgrepo-com.svg" /><label for="warning{self.id}"></label><span class="tooltiptext arrow right">{text}</label></span></span>'
        else:
            return '<span style="display:inline-block;height:20px;width:24px;"> </span>'


class CurrentActive(models.Manager):
    def get_queryset(self):
       return super().get_queryset().filter(use_from__lte=datetime.date.today()).order_by('-use_from')

class CommunicationTemplate(models.Model):
    """A template for building emails with attachments - not a generalized CMS."""
    class Meta:
        indexes = [
            models.Index(name='CategoryByDate', fields=['category', '-use_from']),
            models.Index(name='CategorySubCategoryByDate', fields=['category', 'sub_category', '-use_from']),
            models.Index(name='CategorySummaryByDate', fields=['category', 'summary', '-use_from'])
        ]
    objects = models.Manager()
    current_active = CurrentActive()
    category = models.CharField(max_length=20)
    sub_category = models.CharField(max_length=20, null=True, blank=True)
    summary = models.CharField(max_length=180, null=True, blank=True, )
    subject = models.CharField(max_length=180, null=False, blank=False)
    html_content  = models.TextField( blank=False, null=False,)
    signature = models.TextField(max_length=500, null=True, blank=True)
    use_from = models.DateField(null=False, blank=False)
    fields = ['attachment_warnings',]

    @classmethod
    def get_template_for_category(cls, category:str, sub_category:str=None):
        """Get the latest valid template for a given category and sub_category"""
        try:
            return CommunicationTemplate.objects.filter(category=category, sub_category=sub_category, use_from__lte=timezone.now() ).order_by('-use_from').first()
        except CommunicationTemplate.DoesNotExist:
            return None

    def get_use_from_display(self):
        return f'{day_name[self.use_from.weekday()]} {self.use_from.day} {month_name[self.use_from.month]} {self.use_from.year}'

    def deletion_errors(self):
        """Explain why deleting this version would leave templates without a replacement."""
        today = timezone.localdate()
        remaining = CommunicationTemplate.objects.filter(category=self.category).exclude(pk=self.pk)
        errors = []

        # Keep an in-date version with the same summary within this category.
        if not remaining.filter(summary=self.summary, use_from__lte=today).exists():
            errors.append("Another template in this category with the same summary and a Use from date on or before today must remain.")

        # Named attachments resolve by summary within the same category and sub-category.
        if self.summary:
            earliest_use = TemplateAttachment.objects.filter(
                upload=False, template__category=self.category,
                template__sub_category=self.sub_category, template_name=self.summary,
            ).exclude(template_id=self.pk).aggregate(date=models.Min("template__use_from"))["date"]

            # A replacement must be usable by the earliest referencing template and be in date.
            if earliest_use is not None and not remaining.filter(
                sub_category=self.sub_category, summary=self.summary, use_from__lte=min(today, earliest_use),
            ).exists():
                errors.append(
                    f'This template is used as the named attachment "{self.summary}". '
                    f'A remaining template with the same summary, category and sub-category must be in date and have a Use from date '
                    f'on or before {earliest_use:%d/%m/%Y}.'
                )
        return errors

    def attachment_warnings(self) -> str|None:
        """Identify missing or late named attachments for this template."""
        return self.attachment_warnings_for([self])[self.pk]

    @classmethod
    def attachment_warnings_for(cls, templates):
        """Check a list of templates together, avoiding queries for each table row."""
        templates = {template.pk: template for template in templates}
        warnings = {pk: "" for pk in templates}
        if not templates:
            return warnings

        # Uploaded files are not named-template dependencies.
        attachments = list(TemplateAttachment.objects.filter(
            template_id__in=templates, upload=False,
        ).values_list("template_id", "template_name"))
        if not attachments:
            return warnings

        # A named attachment is usable when any same-category version is dated early enough.
        earliest_dates = {}
        for category, sub_category, summary, use_from in cls.objects.filter(
            category__in={template.category for template in templates.values()},
        ).values_list("category", "sub_category", "summary", "use_from"):
            key = (category, sub_category, summary)
            earliest_dates[key] = min(use_from, earliest_dates.get(key, use_from))

        missing = {pk: set() for pk in templates}
        late = {pk: set() for pk in templates}
        for pk, name in attachments:
            template = templates[pk]
            first_date = earliest_dates.get((template.category, template.sub_category, name))
            if first_date is None:
                missing[pk].add(name)
            elif first_date > template.use_from:
                late[pk].add(name)

        for pk in templates:
            messages = []
            if missing[pk]:
                messages.append("Missing named attachment templates: " + ", ".join(sorted(missing[pk])) + ".")
            if late[pk]:
                messages.append("Named attachments become usable after this template: " + ", ".join(sorted(late[pk])) + ".")
            warnings[pk] = " ".join(messages)
        return warnings

    def warning_as_html_fragment(self):
        text = self.attachment_warnings()
        if text:
            return format_html(
                '<span class="tooltip"><img style="width:24px;" id="warning{}" '
                'src="/static/GarageSale/images/icons/warning-svgrepo-com.svg" />'
                '<span class="tooltiptext arrow right">{}</span></span>', self.pk, text,
            )
        else:
            return ''

    def __str__(self):
        return f'"{self.category}" "{self.sub_category}" "{self.get_use_from_display()}"'

    @staticmethod
    def html_to_text(html):
        """Simplistic conversion of HTML to text:
            1) a p is converted to text with a newline after
            2) a div is converted to text with a newline before and after
            3) a span is converted to text (no new lines)
            3) an <a> tag is converted to text and link
            4) a <br> tag is simply a newline
            5) Anything else is converted to text
        """
        def tag_to_text(children):
            text_segments = []
            for tag in children:
                match tag.name:
                    case 'p':
                        text_segments.append(tag_to_text(tag.children))
                        text_segments.append('\n')
                    case 'div':
                        text_segments.append('\n')
                        text_segments.append(tag_to_text(tag.children))
                        text_segments.append('\n')
                    case 'span':
                        text_segments.append(tag_to_text(tag.children))
                    case 'br':
                        text_segments.append('\n')
                    case 'a':
                        text_segments.append(tag.string + ': ')
                        text_segments.append('<' + tag['href'] + '>')
                    case 'img':
                        if tag.has_attr('alt'):
                            text_segments.append(tag['alt'])
                    case _:
                        if isinstance(tag, bs4.element.NavigableString):
                            text_segments.append( str(tag))
                        else:
                            text_segments.append(tag_to_text(tag.children))
            return ''.join(text_segments)

        """Convert HTML to text"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        return  tag_to_text(soup.contents)

    @classmethod
    def default_context(cls, request=None, context=None):
        """Event and request defaults shared by all communication templates."""
        context = context or {}
        if "current_event" in context or "event" in context:
            event = context.get("current_event", context.get("event"))
        elif request is not None and hasattr(request, "current_event"):
            event = request.current_event
        elif request is not None:
            event = EventData.objects.filter(use_from__lt=timezone.localdate()).order_by(
                "-use_from", "-event_date", "-pk",
            ).first()
        else:
            event = None
        organisations = list(event.supporting_organisations.order_by("index", "pk")) if event else []
        names = [organisation.name for organisation in organisations]
        supporting = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names)
        def absolute_url(url):
            return request.build_absolute_uri(url) if request else url
        icons = [{"url": absolute_url(organisation.logo.url), "name": organisation.name}
                 for organisation in organisations if organisation.logo]
        return {
            "current_event": event, "event": event,
            "event_date": event.get_event_date_display() if event else "",
            "event_logo": absolute_url(event.event_logo.url) if event and event.event_logo else "",
            "year": f"{event.event_date.year:04d}" if event else "",
            "current_date": timezone.localdate(),
            "supporting": supporting,
            "supporting_icons": mark_safe(render_to_string("email/icon_set.html", {"icons": icons}).strip()),
            "base_url": request.build_absolute_uri("/") if request else "",
        }

    @classmethod
    def apply_context_defaults(cls, request, context):
        for name, value in cls.default_context(request, context).items():
            context.setdefault(name, value)

    def render_template_as_email(self, request:HttpRequest, context):
        """Convert the template to an email message - with attachments"""

        self.apply_context_defaults(request, context)
        logger.debug(f'Rendering template as email {self=} for {context=} ')
        to = context.pop('email', [])
        from_ = context.pop('from', '')
        bcc = context.pop('bcc', [])

        logger.debug(f'Rendering body  {self=} for {context=} ')
        body_template = Template(str(self.html_content))
        html_body = body_template.render( context=Context(context)) + "<br>-- <br>" + self.signature

        msg = EmailMultiAlternatives(
            to=to,
            from_email=from_,
            subject=Template(self.subject).render(context=Context(context)),
            body=self.html_to_text(html_body),
            bcc=bcc if bcc else []
        )

        msg.attach_alternative(html_body, "text/html")
        logger.debug(f'Msg built {msg.to=},  {msg.from_email=}, {msg.subject}')

        return msg

    @classmethod
    def pdf_header_template(cls, context:dict):
        result = finders.find('GarageSale/styles/pdf_header.css')
        if not result:
            return ''

        with open(result) as f:
            template = Template(f.read())
        return template.render( context=Context(context))

    def get_header_text(self, request:HttpRequest, context):
        """Get the header text for the email"""
        self.apply_context_defaults(request, context)
        if request:
            host,scheme  = request.get_host(), request.scheme
        else:
            host, scheme = 'localhost', 'http'
        context['host'] = host
        context['scheme'] = scheme
        # PDF headers and attachment bodies share the request-derived website root.
        context.setdefault('base_url', request.build_absolute_uri('/') if request else '')
        context['summary'] = self.summary
        return CommunicationTemplate.pdf_header_template(context)

    @classmethod
    def pdf_from_template_str(cls, context:dict, template_str:str, header:str = ""):
        html = io.StringIO(Template(template_str).render(Context(context)))
        pdf = weasyprint.HTML(html).write_pdf(stylesheets=[weasyprint.CSS(string=header)])
        return pdf

    def render_template_as_pdf(self,request:HttpRequest, context):
        """Convert a given template to a PDF - with headers etc."""
        logger.info(f'Rendering template {self} for {context} as a PDF')

        header = self.get_header_text(request, context)
        return CommunicationTemplate.pdf_from_template_str(context, self.html_content, header)

    def send_email(self, request:HttpRequest, context):

        logger.info(f'Sending email for {self} for {context}')

        msg = self.render_template_as_email(request, context)

        attachments = self.attachments.all()
        logger.info(f'Rendering template {self} - {len(attachments)} attachments')

        for attachment in attachments:
            match attachment.upload:
                case True:
                    mime_type = mimetypes.guess_type(attachment.attached_file.name)[0]
                    msg.attach_file(attachment.attached_file.path, mime_type)
                case False:
                    logger.debug(f'Generating PDF for {self}, {self.category}, {self.sub_category} {attachment.template_name}')
                    content = CommunicationTemplate.current_active.filter(
                        category=self.category, sub_category=self.sub_category, summary=attachment.template_name,
                    ).order_by("-use_from", "-pk").first()
                    if content is None:
                        logger.error(f'Could not find a valid {attachment.template_name} and in date template for {self}')

                    if content:
                        logger.debug(
                            f'Found named template {content.sub_category} PDF for {self.category}, {self.sub_category} {attachment.template_name}')
                        pdf = content.render_template_as_pdf(request, context)
                        msg.attach( attachment.template_name+'-'+datetime.datetime.now().isoformat(sep='-')+'.pdf', pdf, 'application/pdf')

        try:
            ret = msg.send()
            return ret
        except Exception as e:
            logger.error(f'Could not send email for {self} for {context} - {e}')
            return None


from GarageSale.access_policy import CUSTOM_PERMISSIONS


class ApplicationAccess(models.Model):
    """Permission anchor only; no table or broad role flags are required."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = CUSTOM_PERMISSIONS
