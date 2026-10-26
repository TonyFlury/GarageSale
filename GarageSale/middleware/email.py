import logging

from django.conf import settings
from django.core.mail.backends.base import  BaseEmailBackend
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends import smtp

logger = logging.getLogger(__name__)


class EmailExtended(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        credentials = {address.casefold(): details
                       for address, details in settings.EMAIL_CREDENTIALS.items()}
        for message in email_messages:
            # Strip out any 'fake users' - ie anyone with fakeuser in their email address
            message.to = [email for email in message.to if not 'fakeuser' in email.replace('.','')]
            sender = message.from_email
            connection_details = credentials.get(sender.casefold())
            if not connection_details:
                if self.fail_silently:
                    # Admin error notifications must not mask the request error.
                    # WARNING avoids triggering Django's ERROR-level mail handler.
                    logger.warning('Cannot send email: no credentials for sender %r', sender)
                    continue
                raise ImproperlyConfigured(f'No credentials for the email sender {sender}')
            else:
                with smtp.EmailBackend(**{**connection_details, 'fail_silently': self.fail_silently}) as connection:
                    sent += connection.send_messages([message]) or 0
        return sent
