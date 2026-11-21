import uuid

from django.db import migrations, models

import apps.documents.models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0004_avoirs'),
    ]

    operations = [
        migrations.CreateModel(
            name='JustificatifCautionModel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('objet_type', models.CharField(max_length=20)),
                ('objet_id', models.UUIDField(db_index=True)),
                ('fichier', models.FileField(storage=apps.documents.models.stockage_prive, upload_to='justificatifs/')),
                ('nom', models.CharField(max_length=150)),
                ('taille', models.PositiveIntegerField()),
                ('ajoute_le', models.DateTimeField(auto_now_add=True)),
                ('ajoute_par_id', models.UUIDField(blank=True, null=True)),
            ],
            options={'verbose_name': 'Justificatif de retenue', 'ordering': ['ajoute_le']},
        ),
        migrations.CreateModel(
            name='DocumentCautionModel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('numero', models.CharField(max_length=20, unique=True)),
                ('type', models.CharField(choices=[('REC', 'Reçu de restitution'), ('RET', 'Avis de retenue')],
                                          max_length=3)),
                ('emis_le', models.DateTimeField(auto_now_add=True)),
                ('objet_type', models.CharField(max_length=20)),
                ('objet_id', models.UUIDField(db_index=True)),
                ('reference', models.CharField(max_length=40)),
                ('client_nom', models.CharField(max_length=150)),
                ('client_email', models.EmailField(blank=True, max_length=254)),
                ('montant_caution', models.PositiveIntegerField()),
                ('montant_rendu', models.PositiveIntegerField()),
                ('montant_retenu', models.PositiveIntegerField(default=0)),
                ('mode_restitution', models.CharField(max_length=120)),
                ('motif', models.TextField(blank=True)),
                ('cgv_article', models.CharField(blank=True, max_length=30)),
                ('decision', models.CharField(blank=True, help_text='Qui a décidé la retenue, et quand',
                                              max_length=200)),
                ('justificatifs', models.JSONField(blank=True, default=list,
                                                   help_text='Noms des pièces justificatives citées')),
                ('pdf', models.FileField(blank=True, storage=apps.documents.models.stockage_prive,
                                         upload_to='cautions/')),
            ],
            options={
                'verbose_name': 'Document de caution',
                'ordering': ['-emis_le'],
                'constraints': [
                    models.UniqueConstraint(fields=('objet_type', 'objet_id'), name='un_document_par_caution'),
                    models.CheckConstraint(condition=models.Q(montant_rendu__lte=models.F('montant_caution')),
                                           name='document_caution_rendu_borne'),
                    models.CheckConstraint(condition=models.Q(type='REC', montant_retenu=0) | (
                        models.Q(type='RET', montant_retenu__gt=0) & ~models.Q(motif='') & ~models.Q(cgv_article='')),
                        name='document_caution_type_coherent'),
                ],
            },
        ),
    ]
