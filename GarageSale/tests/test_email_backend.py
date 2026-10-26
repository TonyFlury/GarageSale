"""Credential lookup must ignore casing on both sides of the address match."""
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from GarageSale.middleware.email import EmailExtended


class EmailCredentialLookupTests(SimpleTestCase):
    def test_sender_and_credential_keys_match_regardless_of_case(self):
        for sender in ('website@example.com', 'website@Example.COM'):
            for key in ('website@example.com', 'Website@Example.COM'):
                with self.subTest(sender=sender, key=key), override_settings(
                    EMAIL_CREDENTIALS={key: {'host': 'smtp.example.com'}},
                ), patch('GarageSale.middleware.email.smtp.EmailBackend') as backend:
                    connection = backend.return_value.__enter__.return_value
                    connection.send_messages.return_value = 1
                    message = EmailMessage('Invitation', 'Test', sender, ['invitee@example.com'])
                    self.assertEqual(EmailExtended().send_messages([message]), 1)
                    backend.assert_called_once_with(host='smtp.example.com', fail_silently=False)
                    connection.send_messages.assert_called_once_with([message])

    @override_settings(EMAIL_CREDENTIALS={'other@example.com': {'host': 'smtp.example.com'}})
    def test_missing_address_still_reports_original_sender(self):
        sender = 'website@Example.COM'
        with patch('GarageSale.middleware.email.smtp.EmailBackend') as backend:
            with self.assertRaisesMessage(ImproperlyConfigured, f'No credentials for the email sender {sender}'):
                EmailExtended().send_messages([
                    EmailMessage('Invitation', 'Test', sender, ['invitee@example.com']),
                ])
            backend.assert_not_called()

    @override_settings(EMAIL_CREDENTIALS={})
    def test_silent_missing_credentials_returns_zero_and_logs_without_sending(self):
        message = EmailMessage('Error notification', 'Test', 'website@example.com', ['admin@example.com'])
        with self.assertLogs('GarageSale.middleware.email', level='WARNING'), patch(
            'GarageSale.middleware.email.smtp.EmailBackend',
        ) as backend:
            self.assertEqual(EmailExtended(fail_silently=True).send_messages([message]), 0)
            backend.assert_not_called()

    @override_settings(EMAIL_CREDENTIALS={'website@example.com': {'host': 'smtp.example.com'}})
    def test_silent_mode_is_forwarded_to_smtp_backend(self):
        with patch('GarageSale.middleware.email.smtp.EmailBackend') as backend:
            backend.return_value.__enter__.return_value.send_messages.return_value = 0
            message = EmailMessage('Error notification', 'Test', 'website@example.com', ['admin@example.com'])
            self.assertEqual(EmailExtended(fail_silently=True).send_messages([message]), 0)
            backend.assert_called_once_with(host='smtp.example.com', fail_silently=True)

    @override_settings(
        EMAIL_CREDENTIALS={}, EMAIL_BACKEND='GarageSale.middleware.email.EmailExtended',
        SERVER_EMAIL='website@Example.COM', ADMINS=[('Admin', 'admin@example.com')],
    )
    def test_django_admin_notification_does_not_replace_original_exception(self):
        import logging
        import sys
        from django.utils.log import AdminEmailHandler

        try:
            raise ValueError('Original request failure')
        except ValueError:
            record = logging.LogRecord('django.request', logging.ERROR, __file__, 1,
                                       'Internal Server Error', (), sys.exc_info())
        with self.assertLogs('GarageSale.middleware.email', level='WARNING'):
            AdminEmailHandler().handle(record)

    @override_settings(EMAIL_CREDENTIALS={
        'website@example.com': {'host': 'smtp.example.com', 'password': 'private-smtp-password'},
    })
    def test_smtp_acceptance_is_logged_with_a_stable_message_id_without_secrets(self):
        message = EmailMessage('Private subject', 'Private invitation token',
                               'website@example.com', ['private-recipient@example.com'])
        with patch('GarageSale.middleware.email.smtp.EmailBackend') as backend, self.assertLogs(
            'GarageSale.middleware.email', level='INFO',
        ) as logs:
            backend.return_value.__enter__.return_value.send_messages.return_value = 1
            self.assertEqual(EmailExtended().send_messages([message]), 1)
        output = '\n'.join(logs.output)
        self.assertIn('SMTP accepted message', output)
        self.assertIn("host='smtp.example.com'", output)
        self.assertIn(message.extra_headers['Message-ID'], output)
        for private in ('private-smtp-password', 'Private subject', 'Private invitation token',
                        'private-recipient@example.com'):
            self.assertNotIn(private, output)

    @override_settings(EMAIL_CREDENTIALS={'website@example.com': {'host': 'smtp.example.com'}})
    def test_smtp_failure_is_logged_and_still_raises(self):
        from smtplib import SMTPAuthenticationError
        message = EmailMessage('Invitation', 'Private token', 'website@example.com', ['invitee@example.com'])
        with patch('GarageSale.middleware.email.smtp.EmailBackend') as backend, self.assertLogs(
            'GarageSale.middleware.email', level='WARNING',
        ) as logs:
            backend.return_value.__enter__.return_value.send_messages.side_effect = SMTPAuthenticationError(
                535, b'Authentication failed',
            )
            with self.assertRaises(SMTPAuthenticationError):
                EmailExtended().send_messages([message])
        self.assertIn('error_type=SMTPAuthenticationError smtp_code=535', logs.output[0])

    @override_settings(EMAIL_CREDENTIALS={'website@example.com': {'host': 'smtp.example.com'}})
    def test_zero_send_count_is_logged_and_stays_zero(self):
        message = EmailMessage('Invitation', 'Test', 'website@example.com', ['invitee@example.com'],
                               headers={'Message-ID': '<existing@example.com>'})
        with patch('GarageSale.middleware.email.smtp.EmailBackend') as backend, self.assertLogs(
            'GarageSale.middleware.email', level='WARNING',
        ) as logs:
            backend.return_value.__enter__.return_value.send_messages.return_value = 0
            self.assertEqual(EmailExtended().send_messages([message]), 0)
        self.assertIn('SMTP accepted no messages', logs.output[0])
        self.assertEqual(message.extra_headers['Message-ID'], '<existing@example.com>')
