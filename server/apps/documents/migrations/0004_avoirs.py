import uuid

import django.db.models.deletion
from django.db import migrations, models

import apps.documents.models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0003_comptes_par_identifiant'),
    ]

    operations = [
        migrations.CreateModel(
            name='SequencePieceModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('serie', models.CharField(max_length=5)),
                ('annee', models.PositiveSmallIntegerField()),
                ('dernier', models.PositiveIntegerField(default=0)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('serie', 'annee'),
                                                        name='une_sequence_par_serie_et_annee')],
            },
        ),
        migrations.CreateModel(
            name='AvoirModel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('numero', models.CharField(max_length=20, unique=True)),
                ('emis_le', models.DateTimeField(auto_now_add=True)),
                ('emis_par_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('motif', models.CharField(max_length=300)),
                ('lignes', models.JSONField(default=list,
                                            help_text='[{libelle, quantite, prix_unitaire}] en FCFA TTC, à déduire')),
                ('total_ht', models.PositiveIntegerField()),
                ('tva', models.PositiveIntegerField(default=0)),
                ('total_ttc', models.PositiveIntegerField()),
                ('taux_tva', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('pdf', models.FileField(blank=True, storage=apps.documents.models.stockage_prive, upload_to='avoirs/')),
                ('facture', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='avoirs',
                                              to='documents.facturemodel')),
            ],
            options={
                'verbose_name': 'Avoir',
                'ordering': ['-emis_le'],
                'constraints': [models.CheckConstraint(condition=models.Q(total_ttc__gt=0),
                                                       name='avoir_montant_positif')],
            },
        ),
    ]
