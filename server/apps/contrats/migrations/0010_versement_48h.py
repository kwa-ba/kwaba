# Host and hotel contracts, 19 November 2026: payout 48 h after the arrival (decision of the associates, CGV 2.5), and
# the offset of a stay cancelled and refunded after its payout (GL-23). Only these sentences change, in the templates
# as the back-office may have edited them; a template that changes gets a new version, the contracts already issued
# keep the text of theirs.
from django.db import migrations

ANCIEN_HOTE = ("– Versement : 24 heures après l'arrivée du client, par Mobile Money, commission déduite, sur le compte "
               "au nom de l'Hôte indiqué dans son espace hôte.")
ANCIEN_HOTEL = ("– Versement : 24 heures après l'arrivée du client, commission déduite, sur le compte de "
                "l'Établissement indiqué dans son espace ; relevé et facture de commission mensuels.")


def _nouveau(ancien: str) -> str:
    from apps.contrats.modeles_defaut import HOTE, HOTEL

    for corps in (HOTE, HOTEL):
        debut = ancien.replace('24 heures', '48 heures')
        for paragraphe in corps.split('\n'):
            if paragraphe.startswith(debut):
                suite = corps.split('\n')[corps.split('\n').index(paragraphe) + 1]
                return paragraphe + '\n' + suite
    raise LookupError(ancien)


def appliquer(apps, schema_editor):
    Modele = apps.get_model('contrats', 'ModeleContratModel')
    for type_contrat, ancien in (('hote', ANCIEN_HOTE), ('hotel', ANCIEN_HOTEL)):
        modele = Modele.objects.filter(type=type_contrat).first()
        if modele is None:
            continue
        corps = modele.corps.replace('\r\n', '\n')
        if ancien in corps:
            modele.corps, modele.version = corps.replace(ancien, _nouveau(ancien), 1), modele.version + 1
            modele.save(update_fields=['corps', 'version'])


class Migration(migrations.Migration):
    dependencies = [('contrats', '0009_tarifs_en_variables')]
    operations = [migrations.RunPython(appliquer, migrations.RunPython.noop)]
