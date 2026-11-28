# Single referential of the vehicle ranges, shared by transfers and rentals (harmonisation of 26 November 2026, T-H1).
# The transfer categories berline / confort (« SUV confort ») / van become the ranges berline / suv / minibus.

import django.core.validators
from django.db import migrations, models

GAMMES = [
    # code, libellé, en, description, en, places, bagages, transfert, location
    ('citadine', 'Citadine', 'City car', 'Toyota Yaris ou similaire', 'Toyota Yaris or similar', 4, 2, False, True),
    ('berline', 'Berline', 'Sedan', 'Toyota Corolla ou similaire, climatisée', 'Toyota Corolla or similar, air-conditioned',
     3, 3, True, True),
    ('suv', 'SUV', 'SUV', "Toyota RAV4 ou similaire, plus d'espace", 'Toyota RAV4 or similar, more room', 4, 4, True,
     True),
    ('4x4', '4×4 tout-terrain', '4×4 off-road', 'Toyota Land Cruiser ou similaire', 'Toyota Land Cruiser or similar',
     4, 4, False, True),
    ('minibus', 'Minibus', 'Minibus', 'Toyota Hiace ou similaire, pour les groupes', 'Toyota Hiace or similar, for groups',
     7, 8, True, True),
    ('utilitaire', 'Utilitaire', 'Utility van', 'Pour les déménagements et les livraisons', 'For moves and deliveries',
     2, 2, False, True),
]


def creer(apps, schema_editor):
    Gamme = apps.get_model('mobilite', 'GammeVehiculeModel')
    for ordre, (code, libelle, libelle_en, description, description_en, places, bagages, transfert, location) in \
            enumerate(GAMMES, start=1):
        Gamme.objects.update_or_create(code=code, defaults={
            'libelle': libelle, 'libelle_en': libelle_en, 'description': description, 'description_en': description_en,
            'places': places, 'bagages': bagages, 'propose_transfert': transfert, 'propose_location': location,
            'ordre': ordre})


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='GammeVehiculeModel',
            fields=[
                ('code', models.SlugField(max_length=20, primary_key=True, serialize=False)),
                ('libelle', models.CharField(max_length=60)),
                ('libelle_en', models.CharField(max_length=60)),
                ('description', models.CharField(blank=True, default='', help_text='Par ex. « Toyota Corolla ou similaire »', max_length=160)),
                ('description_en', models.CharField(blank=True, default='', max_length=160)),
                ('places', models.PositiveSmallIntegerField(help_text='Passagers en transfert', validators=[django.core.validators.MinValueValidator(1)])),
                ('bagages', models.PositiveSmallIntegerField(help_text='Grandes valises en transfert')),
                ('propose_transfert', models.BooleanField(default=False, help_text='Proposée en transfert aéroport')),
                ('propose_location', models.BooleanField(default=True, help_text='Proposée en location')),
                ('ordre', models.PositiveSmallIntegerField(default=0)),
                ('actif', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Gamme de véhicule',
                'verbose_name_plural': 'Gammes de véhicules',
                'db_table': 'mobilite_gamme_vehicule',
                'ordering': ['ordre', 'code'],
            },
        ),
        migrations.RunPython(creer, migrations.RunPython.noop),
    ]
