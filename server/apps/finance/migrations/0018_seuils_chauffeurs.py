# Thresholds of the drivers' levels (decision of 19 November 2026), over the last months of rides: Confirmé from
# 15 rides and an average rating of 4.3, Excellence from 40 rides and 4.7 without lateness nor no-show; a serious
# incident takes one level down. Steered parameters with their history (GL-20).
from django.db import migrations

MOTIF = 'Décision des associés du 19 novembre 2026 : niveaux des chauffeurs'
PARAMETRES = [
    ('chauffeur_confirme_courses', 15, 'code', 'seuil', 'Chauffeur Confirmé : courses sur la période'),
    ('chauffeur_confirme_note', 4.3, 'code', 'seuil', 'Chauffeur Confirmé : note moyenne des voyageurs'),
    ('chauffeur_excellence_courses', 40, 'code', 'seuil', 'Chauffeur Excellence : courses sur la période'),
    ('chauffeur_excellence_note', 4.7, 'code', 'seuil', 'Chauffeur Excellence : note moyenne des voyageurs'),
    ('chauffeur_niveau_periode_mois', 3, 'mois', 'delai', 'Période de la revue des niveaux des chauffeurs'),
]


def appliquer(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        for cle, valeur, unite, categorie, libelle in PARAMETRES:
            c.execute("INSERT INTO finance_parametre (cle, valeur, unite, categorie, offre_code, libelle, source, "
                      "actif, maj_le) VALUES (%s, %s, %s, %s, 'TRANSFERT', %s, %s, true, now()) "
                      "ON CONFLICT (cle) DO NOTHING", [cle, valeur, unite, categorie, libelle, MOTIF])
            c.execute("INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) "
                      "VALUES (%s, NULL, %s, now(), %s)", [cle, valeur, MOTIF])


def revenir(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("UPDATE finance_parametre SET actif = false WHERE cle = ANY(%s)", [[p[0] for p in PARAMETRES]])


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0017_pilotage_inventaire'),
    ]

    operations = [
        migrations.RunPython(appliquer, revenir),
    ]
