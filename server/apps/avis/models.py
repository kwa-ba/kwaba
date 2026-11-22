import uuid
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


NOTE = [MinValueValidator(1), MaxValueValidator(5)]

# Criteria rated by the traveller, in display order
CRITERES = {
    'proprete': 'Propreté',
    'conformite': 'Conforme aux photos',
    'communication': 'Communication',
    'emplacement': 'Emplacement',
    'qualite_prix': 'Rapport qualité/prix',
}


class AvisModel(models.Model):
    """Verified review: attached to a real, finished booking, only one per stay."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reservation_id = models.UUIDField(unique=True)
    hebergement_id = models.UUIDField(db_index=True)
    auteur_id = models.UUIDField(db_index=True)

    note = models.PositiveSmallIntegerField(validators=NOTE)
    proprete = models.PositiveSmallIntegerField(validators=NOTE)
    conformite = models.PositiveSmallIntegerField(validators=NOTE)
    communication = models.PositiveSmallIntegerField(validators=NOTE)
    emplacement = models.PositiveSmallIntegerField(validators=NOTE)
    qualite_prix = models.PositiveSmallIntegerField(validators=NOTE)
    commentaire = models.TextField()

    reponse_hote = models.TextField(blank=True)
    reponse_le = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'avis'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(condition=models.Q(note__gte=1, note__lte=5), name='avis_note_1_a_5'),
        ]

    def __str__(self):
        return f"{self.note}/5 · {self.hebergement_id} par {self.auteur_id}"


class ReviewReportModel(models.Model):
    """A review reported by an account (ADR-040): kept until the team deletes the review or dismisses the reports."""

    REASONS = [
        ('offensive', 'Injurieux'),
        ('fake', 'Faux avis'),
        ('personal_data', 'Données personnelles'),
        ('off_topic', 'Hors sujet'),
        ('other', 'Autre'),
    ]
    DETAILS_MAX_LENGTH = 1000

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Deleting the review deletes its reports: the deletion itself is in the journal (avis_supprime)
    avis = models.ForeignKey(AvisModel, on_delete=models.CASCADE, related_name='reports')
    reporter_id = models.UUIDField(db_index=True)
    reason = models.CharField(max_length=20, choices=REASONS)
    details = models.TextField(blank=True, max_length=DETAILS_MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    # Set when the team keeps the review and dismisses its reports
    dismissed_at = models.DateTimeField(null=True, blank=True)
    dismissed_by_id = models.UUIDField(null=True, blank=True)

    class Meta:
        app_label = 'avis'
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['avis', 'reporter_id'], name='avis_one_report_per_account'),
        ]

    def __str__(self):
        return f"{self.get_reason_display()} · avis {self.avis_id}"
