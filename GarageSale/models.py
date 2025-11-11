#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.models.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
import datetime
from unicodedata import category

import weasyprint
import mimetypes
import io
import logging
import bs4
from django.apps import apps
from django.contrib.admin.utils import label_for_field

from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.db.models import Exists, Subquery
from django.http import HttpRequest
from django.template import Template
from django_quill.fields import QuillField
from django.contrib.auth.models import User

from django.contrib.auth.models import AbstractUser
from django.conf import settings

from GarageSale.svgaimagefield import SVGAndImageFormField

from calendar import day_name, month_name

class General(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("is_trustee", "Is a member of the Charity Trustee Team"),
           ("is_administrator", 'Is a administrator for the website'),
            ("is_manager", 'Is a manager of the website'),
        ]

class MOTD(models.Model):
    """"Holder for Message of the Day"""
    use_from = models.DateField()
    content = QuillField(default='')
    synopsis = models.CharField(max_length=256, null=True)

    @staticmethod
    def get_current():
        try:
            return MOTD.objects.filter(use_from__lte = datetime.date.today()).latest('use_from')
        except MOTD.DoesNotExist:
            return None

    class Meta:
        default_permissions = ()
        permissions = [
            ("can_create_motd", "Can create a new MotD"),
            ("can_edit_motd", "Can edit an existing MotD"),
            ("can_view_motd", "Can view an existing MotD"),
            ("can_delete_motd", "Can delete an existing MotD"),
        ]

def save_supported_logo_to(instance, filename):
    return f'supported_logo_{instance.name}/{filename}'


class Byindex(models.Manager):
    def get_queryset(self):
        return super(Byindex, self).get_queryset().order_by('index')

class Supporting(models.Model):
    objects = Byindex()
    name = models.CharField(max_length = 100)
    logo = models.FileField(upload_to=save_supported_logo_to, null=True, blank=True)
    website = models.URLField()
    index = models.IntegerField()
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
    event_logo = models.FileField(null=True, upload_to=save_event_logo_to)    # The specific logo for this years event
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

    class Meta:
        default_permissions = ()
        permissions = [
            ("can_create_event", "Can create a new Event"),
            ("can_edit_event", "Can edit an existing Event"),
            ("can_view_event", "Can view an existing Event"),
            ("can_delete_event", "Can delete an existing Event"),
            ("can_use_event", "Can use an existing Event")
        ]

    @staticmethod
    def get_current():
        try:
            e = (EventData.objects.filter(use_from__lte = datetime.date.today(),
                                             event_date__gte = datetime.date.today()).earliest('event_date') )
            return e
        except EventData.DoesNotExist:
            return None

def save_template_attachment_to(instance, filename):
    return f'template_attachments/{instance.template.category}/{instance.template.tranisition}/{instance.template.use_from.iso_format()}/{filename}'

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
        CommunicationTemplate:models.Model = apps.get_model('GarageSale', 'CommunicationTemplate')
        template_with_name = CommunicationTemplate.objects.filter(category=self.template.category, transition=self.template_name)
        template_in_date = CommunicationTemplate.objects.filter(category=self.template.category, transition=self.template_name,
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

class CommunicationTemplate(models.Model)   :
    class Meta:
        indexes = [
            models.Index(name='CategoryByDate', fields=['category', '-use_from']),
            models.Index(name='CategoryTransitionByDate', fields=['category', 'transition', '-use_from']),
            models.Index(name='CategorySummaryByDate', fields=['category', 'summary', '-use_from'])
        ]
    objects = models.Manager()
    current_active = CurrentActive()
    category = models.CharField(max_length=20)
    transition = models.CharField(max_length=20, null=True, blank=True)
    summary = models.CharField(max_length=180, null=True, blank=True, )
    subject = models.CharField(max_length=180, null=False, blank=False)
    html_content  = models.TextField( blank=False, null=False,)
    signature = models.TextField(max_length=500, null=True, blank=True)
    use_from = models.DateField(null=False, blank=False)
    fields = ['attachment_warnings',]

    def attachment_warnings(self) -> str|None:
        """Identify any warnings with regards the attachments"""
        named_templates = CommunicationTemplate.objects.filter(category=self.category).annotate(name=models.F('transition'))

        missing_names = (TemplateAttachment.objects.
                            filter(template=self.id, upload=False).
                            exclude(template_name__in = Subquery(named_templates.
                                                                 values('name')
                                                                 )
                                    )
                         )

        out_of_date = (TemplateAttachment.objects.
                         filter(template=self.id, upload=False).
                         exclude(template_name__in=Subquery(named_templates.
                                                       filter(use_from__lte=self.use_from).
                                                       values('name'))
                                 )
                       )

        match bool(missing_names), bool(out_of_date):
            case True, True:
                return 'Missing and out of date Attachments'
            case True, False:
               return 'Out of date Attachments'
            case False, True:
                return 'Named attachments missing'
            case _,_:
                return ""

    def warning_as_html_fragment(self):
        text = self.attachment_warnings()
        if text:
            return f'<span class="tooltip"><image style="width:24px;" id="warning{self.id}" src="/static/GarageSale/images/icons/warning-svgrepo-com.svg" /><label for="warning{self.id}"></label><span class="tooltiptext arrow right">{text}</label></span>'
        else:
            return ''

    def __str__(self):
        return f'{self.category} {self.transition} {self.use_from}'

    @staticmethod
    def html_to_text(html):
        def tag_to_text(children):
            segments = []
            for tag in children:
                match tag.name:
                    case 'p':
                        segments.append(tag_to_text(tag.children))
                        segments.append('\n')
                    case 'div':
                        segments.append('\n')
                        segments.append(tag_to_text(tag.children))
                        segments.append('\n')
                    case 'span':
                        segments.append(tag_to_text(tag.children))
                    case 'br':
                        segments.append('\n')
                    case 'a':
                        segments.append(tag.string + ': ')
                        segments.append('<' + tag['href'] + '>')
                    case 'img':
                        if tag.has_attr('alt'):
                            segments.append(tag['alt'])
                    case _:
                        if isinstance(tag, bs4.element.NavigableString):
                            segments.append( str(tag))
                        else:
                            segments.append(tag_to_text(tag.children))
            return ''.join(segments)

        """Convert HTML to text"""
        from bs4 import BeautifulSoup
        segments = []
        soup = BeautifulSoup(html, 'html.parser')
        return  tag_to_text(soup.contents)

    def render_template_as_email(self, request:HttpRequest, context):

        body_template = Template(str(self.html_content))

        html_body = body_template.render( context=context) + "<br>-- <br>" + self.signature
        msg = EmailMultiAlternatives(
            to=[to, ],
            from_email=from_,
            subject=Template(self.subject).render(context=context),
            body=self.html_to_text(html_body),
            bcc=bcc if bcc else []
        )
        html_body = body_template.render( context=context) + "<br>-- <br>" + self.signature

        msg.attach_alternative(html_body, "text/html")
        return msg

    def render_template_as_pdf(self,request:HttpRequest, context):
        server = request.get_host()
        header  = (f'@page {{size: A4; margin: 6rem 0.5cm; '
                           f'@bottom-right{{content: "Page " counter(page) " of " counter(pages); }}'
                           f'@top-center{{ border: none;width: 100%; height: 4rem; margin-top: 0.5cm; '
                           f'background-image: url("{server}/media/event_logo_2026-6/horse-Logo-01.png"),'
                           f'linear-gradient(to right, rgb(80 100 115 / 100%), transparent);'  
                           f'background-repeat: no-repeat, no-repeat;'
                           f'background-position: top left, left;'
                           f'background-size: 3.75rem, 100%;'
                           f'margin-bottom: 0.5cm;'
                           f'margin-top: 1cm;'            
                           '}}'
                           '@top-center{{font-size:22px; font-weight:bold;content: "Brantham Garage Sale Foundation"}}'
                           '}}')

        doc = bytes()
        html = io.StringIO(Template(self.html_content).render(context))
        pdf = weasyprint.HTML(html).write_pdf(stylesheets=[weasyprint.CSS(string=header)])
        return pdf

    def send_email(self, request:HttpRequest, to, from_, context, bcc=None):

        msg = self.render_template_as_email(request, context)

        try:
            attachments = self.attachments.all()
        except TemplateAttachment.DoesNotExist:
            attachments = []

        for attachment in attachments:
            match attachment.upload:
                case True:
                    mime_type = mimetypes.guess_type(attachment.file.name)[0]
                    msg.attach_file(attachment.file, mime_type)
                case False:
                    logging.debug(f'Generating PDF for {self}, {self.category}, {self.transition} {attachment.name}')
                    try:
                        content = CommunicationTemplate.current_active.filter(category=self.category).filter(transition=attachment.name).order_by("-use_from").latest('use_from')
                    except CommunicationTemplate.DoesNotExist:
                        logging.error(f'Could not find a valid {attachment.name} and in date template for {self}')
                        content = ''
                    logging.debug(f'Found named template {content.transition} PDF for {self.category}, {self.transition} {attachment.name}')

                    pdf = content.render_template_as_pdf(request, context)

                    msg.attach( attachment.name+'-'+datetime.datetime.now().isoformat(sep='-')+'.pdf', pdf, 'application/pdf')

        return msg.send()


