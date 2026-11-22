"""Reports of the reviews (ADR-040): an account reports a review once, the team is alerted at the first pending report,
then deletes the review or dismisses its reports."""
import logging
import uuid

from django.conf import settings
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.hebergements import api as hebergements
from apps.users import api as users
from shared.notifications.api import send_mail

from .models import AvisModel, ReviewReportModel

logger = logging.getLogger('apps.avis')

ADMIN_SECTION = 'avis'


class ReportRefused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def report(review: AvisModel, reporter_id: uuid.UUID, reason: str, details: str) -> ReviewReportModel:
    if review.auteur_id == reporter_id:
        raise ReportRefused('own_review', 'Vous ne pouvez pas signaler votre propre avis.')
    try:
        with transaction.atomic():
            first_pending = not pending(review).exists()
            created = ReviewReportModel.objects.create(avis=review, reporter_id=reporter_id, reason=reason,
                                                       details=details)
    except IntegrityError:
        raise ReportRefused('already_reported', 'Vous avez déjà signalé cet avis.') from None
    if first_pending:
        transaction.on_commit(lambda: _alert_the_team(created))
    return created


def pending(review: AvisModel):
    return review.reports.filter(dismissed_at__isnull=True)


def pending_by_review(review_ids) -> dict[uuid.UUID, list[ReviewReportModel]]:
    found: dict[uuid.UUID, list[ReviewReportModel]] = {}
    for item in ReviewReportModel.objects.filter(avis_id__in=list(review_ids), dismissed_at__isnull=True):
        found.setdefault(item.avis_id, []).append(item)
    return found


def dismiss(review: AvisModel, by_id: uuid.UUID) -> int:
    """The team keeps the review: its pending reports are marked handled. Returns how many."""
    return pending(review).update(dismissed_at=timezone.now(), dismissed_by_id=by_id)


def _alert_the_team(created: ReviewReportModel) -> None:
    recipients = users.emails_admins_section(ADMIN_SECTION)
    if not recipients:
        logger.error('Avis %s signalé, aucun administrateur à prévenir', created.avis_id)
        return
    listing = hebergements.resumes([created.avis.hebergement_id]).get(created.avis.hebergement_id)
    send_mail(
        subject='[Kwa-Ba] Avis signalé',
        message=render_to_string('emails/avis/review_reported.txt', {
            'listing': listing['name'] if listing else '',
            'reason': created.get_reason_display(),
            'details': created.details,
            'comment': created.avis.commentaire,
            'url': f"{settings.FRONTEND_URL}/backoffice/avis?reported=1",
        }),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
    )
