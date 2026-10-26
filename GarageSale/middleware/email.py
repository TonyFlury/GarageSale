import logging
from email.utils import make_msgid
from smtplib import SMTPException

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
                logger.warning('Cannot send email: no credentials for sender %r', sender)
                if self.fail_silently:
                    # Admin error notifications must not mask the request error.
                    # WARNING avoids triggering Django's ERROR-level mail handler.
                    continue
                raise ImproperlyConfigured(f'No credentials for the email sender {sender}')

            message_id = next((value for key, value in message.extra_headers.items()
                               if key.casefold() == 'message-id'), None)
            if not message_id:
                message_id = make_msgid()
                message.extra_headers['Message-ID'] = message_id
            recipient_count = len(message.recipients())
            logger.info('SMTP submission started: host=%r port=%s sender=%r recipients=%d message_id=%s',
                        connection_details.get('host', settings.EMAIL_HOST),
                        connection_details.get('port', settings.EMAIL_PORT), sender, recipient_count, message_id)
            try:
                with smtp.EmailBackend(**{**connection_details, 'fail_silently': self.fail_silently}) as connection:
                    count = connection.send_messages([message]) or 0
                    if count:
                        logger.info('SMTP accepted message: sender=%r recipients=%d message_id=%s',
                                    sender, recipient_count, message_id)
                    else:
                        logger.warning('SMTP accepted no messages: sender=%r recipients=%d message_id=%s',
                                       sender, recipient_count, message_id)
                sent += count
            except (OSError, SMTPException) as error:
                # Do not log message bodies, invitation tokens or SMTP credentials.
                logger.warning('SMTP operation failed: sender=%r message_id=%s error_type=%s smtp_code=%s',
                               sender, message_id, type(error).__name__, getattr(error, 'smtp_code', None))
                raise
        return sent
