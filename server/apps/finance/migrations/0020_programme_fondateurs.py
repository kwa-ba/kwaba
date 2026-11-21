# Perimeter of the 5 % commission in the referential (DEV-F3, decision D3 / L12): only the hosts of the Founders
# Programme, individuals, for a limited number of places and months. Both limits were written in the code (50) or only
# in help texts (6 months): they become steered parameters with their history (GL-20).
from django.db import migrations

MOTIF = 'DEV-F3 : périmètre de la commission fondateur écrit au référentiel (décision D3)'
PARAMETRES = [
    ('fondateurs_places', 50, 'code', 'seuil', 'Programme Fondateurs : nombre de places (hôtes particuliers)'),
    ('fondateurs_duree_mois', 6, 'mois', 'delai', 'Programme Fondateurs : durée maximale de la commission réduite'),
]
LIBELLE_COMMISSION = ("Commission des hôtes fondateurs UNIQUEMENT : particuliers inscrits au Programme Fondateurs, "
                      "dans la limite de fondateurs_places et pendant fondateurs_duree_mois ; sinon commission_hote "
                      "(particulier) ou commission_hotel (hôtel)")


def appliquer(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        for cle, valeur, unite, categorie, libelle in PARAMETRES:
            c.execute("INSERT INTO finance_parametre (cle, valeur, unite, categorie, offre_code, libelle, source, "
                      "actif, maj_le) VALUES (%s, %s, %s, %s, 'COURTE_DUREE', %s, %s, true, now()) "
                      "ON CONFLICT (cle) DO NOTHING", [cle, valeur, unite, categorie, libelle, MOTIF])
            c.execute("INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) "
                      "VALUES (%s, NULL, %s, now(), %s)", [cle, valeur, MOTIF])
        c.execute("UPDATE finance_parametre SET libelle = %s WHERE cle = 'commission_hote_fondateur'",
                  [LIBELLE_COMMISSION])


def revenir(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("UPDATE finance_parametre SET actif = false WHERE cle = ANY(%s)", [[p[0] for p in PARAMETRES]])
        c.execute("UPDATE finance_parametre SET libelle = 'Commission des 50 hotes fondateurs, 6 mois' "
                  "WHERE cle = 'commission_hote_fondateur'")


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0019_fonds_garantie_reserve'),
    ]

    operations = [
        migrations.RunPython(appliquer, revenir),
    ]
