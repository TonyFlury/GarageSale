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
from django.db import models
from django.db.models import Subquery
from django.http import HttpRequest
from django.template import Template, Context, loader
from django.template.loader import get_template
from django.template import Template, Context, Engine
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
    content = QuillField(default='')
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
    index = models.IntegerField()
    def __str__(self):
        return self.name

    class Meta:
        permissions = [('can_create_supporting', 'Can create a record for a supporting organisation'),]

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
        template_with_name = CommunicationTemplate.objects.filter(category=self.template.category,
                                                                  transition=self.template_name)
        template_in_date = CommunicationTemplate.objects.filter(category=self.template.category,
                                                                transition=self.template_name,
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


    def get_use_from_display(self):
        return f'{day_name[self.use_from.weekday()]} {self.use_from.day} {month_name[self.use_from.month]} {self.use_from.year}'

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
        return f'"{self.category}" "{self.transition}" "{self.get_use_from_display()}"'

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

    def render_template_as_email(self, request:HttpRequest, context):
        """Convert the template to an email message - with attachments"""

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
        if request:
            host,scheme  = request.get_host(), request.scheme
        else:
            host, scheme = 'localhost', 'http'
        context['host'] = host
        context['scheme'] = scheme
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
                    logger.debug(f'Generating PDF for {self}, {self.category}, {self.transition} {attachment.template_name}')
                    try:
                        content = CommunicationTemplate.current_active.filter(category=self.category).filter(transition=attachment.template_name).order_by("-use_from").latest('use_from')
                    except CommunicationTemplate.DoesNotExist:
                        logger.error(f'Could not find a valid {attachment.template_name} and in date template for {self}')
                        content = None

                    if content:
                        logger.debug(
                            f'Found named template {content.transition} PDF for {self.category}, {self.transition} {attachment.template_name}')
                        pdf = content.render_template_as_pdf(request, context)
                        msg.attach( attachment.template_name+'-'+datetime.datetime.now().isoformat(sep='-')+'.pdf', pdf, 'application/pdf')

        try:
            ret = msg.send()
            return ret
        except Exception as e:
            logger.error(f'Could not send email for {self} for {context} - {e}')
            return None


