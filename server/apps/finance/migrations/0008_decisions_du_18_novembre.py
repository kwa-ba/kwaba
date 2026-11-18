# Decisions of the associates given on 18 November 2026 (documentation/modules/finance.md), written as parameters with
# their dated history (FIN-16.5): a value is never hard-coded.
# - double_validation_seuil: 250 000 F (H-4): a refund or a payout from this amount needs a second person (GL-10);
# - fonds_garantie_taux: 10 % (GL-17). No code reads it yet: the monthly allocation comes with GL-17, once the G
#   natures have their SYSCOHADA account;
# - capital_social: 500 000 F (GL-16, opening balance sheet), new row.
from django.db import migrations

MOTIF = 'Décision des associés du 18 novembre 2026'
CHANGEMENTS = [
    ('double_validation_seuil', 0, 250000, 'Seuil de double validation des remboursements et des versements (H-4)'),
    ('fonds_garantie_taux', 0, 10, 'Taux du fonds de garantie'),
]


def appliquer(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        for cle, avant, apres, libelle in CHANGEMENTS:
            c.execute('UPDATE finance_parametre SET valeur = %s, libelle = %s, actif = true, maj_le = now() '
                      'WHERE cle = %s', [apres, libelle, cle])
            c.execute('INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) '
                      'VALUES (%s, %s, %s, now(), %s)', [cle, avant, apres, MOTIF])
        c.execute("INSERT INTO finance_parametre (cle, valeur, unite, categorie, offre_code, libelle, source, actif, "
                  "maj_le) VALUES ('capital_social', 500000, 'fcfa', 'interne', 'STRUCTURE', 'Capital social', %s, "
                  "true, now()) ON CONFLICT (cle) DO NOTHING", [MOTIF])
        c.execute("INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) "
                  "VALUES ('capital_social', NULL, 500000, now(), %s)", [MOTIF])


def revenir(apps, schema_editor):
    # The history is append only: going back is a new dated change
    with schema_editor.connection.cursor() as c:
        for cle, avant, apres, _ in CHANGEMENTS:
            c.execute('UPDATE finance_parametre SET valeur = %s, maj_le = now() WHERE cle = %s', [avant, cle])
            c.execute('INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) '
                      'VALUES (%s, %s, %s, now(), %s)', [cle, apres, avant, 'Retour arrière de la migration 0008'])
        c.execute("UPDATE finance_parametre SET actif = false, maj_le = now() WHERE cle = 'capital_social'")


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0007_mois_verrouille_definitif'),
    ]

    operations = [
        migrations.RunPython(appliquer, revenir),
    ]
