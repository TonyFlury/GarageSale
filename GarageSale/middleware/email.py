from django.conf import settings
from django.core.mail.backends.base import  BaseEmailBackend
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends import smtp


class EmailExtended(BaseEmailBackend):
    def send_messages(self, email_messages):
        for message in email_messages:
            sender = message.from_email
            connection_details = settings.EMAIL_CREDENTIALS.get(sender)
            if not connection_details:
                raise ImproperlyConfigured(f'No credentials for the email sender {sender}')
            else:
                with smtp.EmailBackend(**connection_details) as sender:
                    sender.send_messages([message])
