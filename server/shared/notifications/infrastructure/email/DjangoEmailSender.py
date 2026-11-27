from datetime import date

from shared.notifications.infrastructure.email.envoi import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import formats
from shared.notifications.application.ports.NotificationSender import NotificationSender
from shared.language.api import t


class DjangoEmailSender(NotificationSender):

    def send_verification_email(self, to: str, first_name: str, code: str) -> None:
        message = render_to_string('emails/verification_code.txt', {
            'first_name': first_name,
            'code': code,
        })
        send_mail(
            subject=t('notifications.subject_verification'),
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
        )

    def send_welcome_email(self, to: str, first_name: str) -> None:
        message = render_to_string('emails/welcome_email.txt', {
            'first_name': first_name,
        })
        send_mail(
            subject=t('notifications.subject_welcome'),
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
        )

    def send_new_message_email(
        self, to: str, first_name: str, sender_first_name: str,
        hebergement_name: str, message_preview: str, conversation_url: str,
    ) -> None:
        message = render_to_string('emails/new_message.txt', {
            'first_name': first_name,
            'sender_first_name': sender_first_name,
            'hebergement_name': hebergement_name,
            'message_preview': message_preview,
            'conversation_url': conversation_url,
        })
        send_mail(
            subject=t('notifications.subject_new_message', sender=sender_first_name),
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
        )

    def send_password_reset_email(self, to: str, first_name: str, code: str) -> None:
        message = render_to_string('emails/password_reset.txt', {
            'first_name': first_name,
            'code': code,
        })
        send_mail(
            subject=t('notifications.subject_password_reset'),
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
        )

    def send_password_changed_email(self, to: str, first_name: str) -> None:
        message = render_to_string('emails/password_changed.txt', {
            'first_name': first_name,
            'reset_url': f"{settings.FRONTEND_URL.rstrip('/')}/mot-de-passe-oublie",
        })
        send_mail(
            subject=t('notifications.subject_password_changed'),
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
        )

    def send_account_deletion_code_email(self, to: str, first_name: str, code: str) -> None:
        message = render_to_string('emails/account_deletion_code.txt', {'first_name': first_name, 'code': code})
        send_mail(
            subject=t('notifications.subject_deletion_code'),
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
        )

    def send_account_deleted_email(self, to: str, first_name: str) -> None:
        message = render_to_string('emails/account_deleted.txt', {'first_name': first_name})
        send_mail(
            subject=t('notifications.subject_account_deleted'),
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
        )

    def send_booking_cancelled_listing_removed_email(
        self, to: str, first_name: str, hebergement_name: str, city: str, check_in: date, check_out: date,
    ) -> None:
        message = render_to_string('emails/booking_cancelled_listing_removed.txt', {
            'first_name': first_name,
            'hebergement_name': hebergement_name,
            'city': city,
            'check_in': formats.date_format(check_in, 'j F'),
            'check_out': formats.date_format(check_out, 'j F Y'),
            'search_url': f"{settings.FRONTEND_URL.rstrip('/')}/recherche",
        })
        send_mail(
            subject=t('notifications.subject_booking_cancelled_listing_removed'),
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
        )
