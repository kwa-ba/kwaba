# Levels of the drivers aligned on the project book (driver charter B6, resolution 4; decision of 26 November 2026,
# T-H24): Standard and Excellence only. The Confirmé drivers go back to Standard (their pay does not change: only
# Excellence pays 6,500 F), each change written in the level history so that it can be undone. Founders Programme:
# the 10 first drivers, 6 months from their registration (dates the team can correct). New incident types: founded
# complaint, accident at fault; a lateness counts from 15 min.
import calendar
from datetime import timedelta

from django.db import migrations, models

MOTIF_CONFIRME = 'Niveau Confirmé retiré (décision des associés du 26 novembre 2026, charte B6) : Standard'
FONDATEURS, MOIS_FONDATEUR = 10, 6
HISTORIQUE = [('standard', 'Standard'), ('excellence', 'Excellence'), ('confirme', 'Confirmé (retiré)')]


def _plus_mois(jour, mois):
    m = jour.month - 1 + mois
    annee, mois = jour.year + m // 12, m % 12 + 1
    return jour.replace(year=annee, month=mois, day=min(jour.day, calendar.monthrange(annee, mois)[1]))


def appliquer(apps, schema_editor):
    from django.utils import timezone

    Chauffeur = apps.get_model('transferts', 'ChauffeurModel')
    Niveau = apps.get_model('transferts', 'NiveauChauffeurModel')
    for c in Chauffeur.objects.filter(niveau='confirme'):
        Niveau.objects.create(chauffeur=c, avant='confirme', apres='standard', propose='standard', motif=MOTIF_CONFIRME,
                              chiffres={})
        c.niveau, c.excellence, c.niveau_depuis = 'standard', False, timezone.now()
        c.save(update_fields=['niveau', 'excellence', 'niveau_depuis'])
    for c in Chauffeur.objects.filter(fondateur_debut__isnull=True).order_by('cree_le', 'id')[:FONDATEURS]:
        debut = timezone.localtime(c.cree_le).date()
        c.fondateur_debut, c.fondateur_fin = debut, _plus_mois(debut, MOIS_FONDATEUR) - timedelta(days=1)
        c.save(update_fields=['fondateur_debut', 'fondateur_fin'])


def revenir(apps, schema_editor):
    Chauffeur = apps.get_model('transferts', 'ChauffeurModel')
    Niveau = apps.get_model('transferts', 'NiveauChauffeurModel')
    lignes = Niveau.objects.filter(motif=MOTIF_CONFIRME)
    Chauffeur.objects.filter(pk__in=lignes.values('chauffeur_id'), niveau='standard').update(niveau='confirme')
    lignes.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('transferts', '0007_chauffeurs_niveaux_photo_avis'),
    ]

    operations = [
        migrations.AddField(
            model_name='chauffeurmodel',
            name='fondateur_debut',
            field=models.DateField(blank=True, help_text='Programme Fondateurs : premier jour', null=True),
        ),
        migrations.AddField(
            model_name='chauffeurmodel',
            name='fondateur_fin',
            field=models.DateField(blank=True, help_text='Programme Fondateurs : dernier jour (6 mois)', null=True),
        ),
        migrations.AlterField(
            model_name='incidentchauffeurmodel',
            name='type',
            field=models.CharField(choices=[('grave', 'Incident grave'), ('retard', 'Retard de plus de 15 min'), ('absence', 'Absence'), ('plainte', 'Plainte fondée'), ('accident', 'Accident responsable'), ('autre', 'Autre')], max_length=10),
        ),
        migrations.AlterField(
            model_name='niveauchauffeurmodel',
            name='apres',
            field=models.CharField(choices=HISTORIQUE, max_length=12),
        ),
        migrations.AlterField(
            model_name='niveauchauffeurmodel',
            name='avant',
            field=models.CharField(choices=HISTORIQUE, max_length=12),
        ),
        migrations.AlterField(
            model_name='niveauchauffeurmodel',
            name='propose',
            field=models.CharField(choices=HISTORIQUE, max_length=12),
        ),
        # Data first, while the Confirmé value is still allowed; then the field loses it
        migrations.RunPython(appliquer, revenir),
        migrations.AlterField(
            model_name='chauffeurmodel',
            name='niveau',
            field=models.CharField(choices=[('standard', 'Standard'), ('excellence', 'Excellence')], db_default='standard', default='standard', max_length=12),
        ),
    ]
