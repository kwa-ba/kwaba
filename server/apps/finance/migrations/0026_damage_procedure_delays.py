# Delays of the damage procedure on a stay deposit (terms of sale 13.6, decision D-CGV-2 of 22 November 2026,
# ADR-048): the host reports within 48 h of the departure, the traveller answers within 48 h, and may contest the
# team's decision within 7 days.
from django.db import migrations

MOTIF = 'Décision D-CGV-2 du 22 novembre 2026 : délais de la procédure de dommage (ADR-048)'
PARAMETRES = [
    ('dommage_delai_hote_h', 48, 'heures', "Dommage : délai de l'hôte pour le signaler, après le départ"),
    ('dommage_delai_client_h', 48, 'heures', 'Dommage : délai du voyageur pour répondre au signalement'),
    ('dommage_contestation_j', 7, 'jours', 'Dommage : délai du voyageur pour contester la décision'),
]


def apply(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        for cle, valeur, unite, libelle in PARAMETRES:
            c.execute("INSERT INTO finance_parametre (cle, valeur, unite, categorie, offre_code, libelle, source, "
                      "actif, maj_le) VALUES (%s, %s, %s, 'delai', 'COURTE_DUREE', %s, %s, true, now()) "
                      "ON CONFLICT (cle) DO NOTHING", [cle, valeur, unite, libelle, MOTIF])
            c.execute('INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) '
                      'VALUES (%s, NULL, %s, now(), %s)', [cle, valeur, MOTIF])


def revert(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute('UPDATE finance_parametre SET actif = false WHERE cle = ANY(%s)', [[p[0] for p in PARAMETRES]])


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0025_deposit_dispute'),
    ]

    operations = [
        migrations.RunPython(apply, revert),
    ]
