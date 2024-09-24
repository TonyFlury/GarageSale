"""
A shell around the Django email system to allow simple selection of email sending

"""
from django.conf import settings
import django.core.mail as django_mail
from django.core import mail
from django.core.exceptions import ImproperlyConfigured

if not settings.EMAIL_DEFAULT:
    raise ImproperlyConfigured('No EMAIL_DEFAULT setting -'
                               'Ensure this parameter is set to one of the entries in the EMAIL_CREDENTIALS')

default_connection: dict = settings.EMAIL_CREDENTIALS.get(settings.EMAIL_DEFAULT, None)

if not default_connection:
    raise ImproperlyConfigured(
        'An entry for \'{settings.EMAIL_DEFAULT}\' does not exist within the EMAIL_CREDENTIALS')


def _get_connection_params(email_from: str) -> dict:
    """"Return connection parameters dictionary"""
    return settings.EMAIL_CREDENTIALS.get(email_from, default_connection)


def send_email(subject, message, from_email, recipient_list,
               fail_silently=False, auth_user=None, auth_password=None, connection=None, html_message=None):
    """ Shell around ajango.core.mail.send_email
        Allows switching of connections details based on from_emails.
    """
    with django_mail.get_connection(**_get_connection_params(from_email)) as conn:
        django_mail.send_mail(subject, message, from_email, recipient_list, fail_silently,
                              auth_user, auth_password,
                              conn,
                              html_message)
