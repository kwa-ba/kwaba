# Harmonisation of the mobility (26 November 2026), lot 1. T-H1: the transfer categories become ranges of the shared
# referential (module mobilite): « SUV confort » is « SUV » (confort → suv), the van is the « Minibus » (van → minibus);
# the codes are checked against the referential, no longer fixed choices. T-H2: a driver record may be linked to a
# Kwa-Ba account (the same account may be an owner) and to the vehicle record they drive.
from django.db import migrations, models

CORRESPONDANCE = {'confort': 'suv', 'van': 'minibus'}
MODELES = ('TarifTransfertModel', 'ChauffeurModel', 'TransfertModel')


def _renommer(apps, correspondance):
    for nom in MODELES:
        modele = apps.get_model('transferts', nom)
        for avant, apres in correspondance.items():
            modele.objects.filter(categorie=avant).update(categorie=apres)


def vers_gammes(apps, schema_editor):
    _renommer(apps, CORRESPONDANCE)


def vers_categories(apps, schema_editor):
    _renommer(apps, {apres: avant for avant, apres in CORRESPONDANCE.items()})


class Migration(migrations.Migration):

    dependencies = [
        ('transferts', '0008_niveaux_livre_fondateurs'),
        ('mobilite', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='chauffeurmodel',
            name='compte_id',
            field=models.UUIDField(blank=True, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='chauffeurmodel',
            name='vehicule_id',
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name='chauffeurmodel',
            name='categorie',
            field=models.CharField(help_text='Gamme du référentiel mobilité (code)', max_length=20),
        ),
        migrations.AlterField(
            model_name='tariftransfertmodel',
            name='categorie',
            field=models.CharField(help_text='Gamme du référentiel mobilité (code)', max_length=20),
        ),
        migrations.AlterField(
            model_name='transfertmodel',
            name='categorie',
            field=models.CharField(help_text='Gamme du référentiel mobilité (code)', max_length=20),
        ),
        migrations.RunPython(vers_gammes, vers_categories),
    ]
