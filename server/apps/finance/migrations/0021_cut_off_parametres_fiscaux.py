# Cut-off of the service fees (ADR-034, DEV-C2): a technical money account « PCA » (prepaid income, account 477),
# without a provider's statement. Tax parameters (DEV-C8, DEV-C9, rule 4 of doc 37): the VAT threshold becomes active
# so its alert works, the turnover minimum tax becomes inactive until the tax office confirms it.
from django.db import migrations

MOTIF = 'ADR-034 : cut-off 477, seuil de TVA actif, minimum forfaitaire inactif en attente de l''OTR'
PARAMETRES = [('tva_seuil', True), ('impot_minimum', False)]


def _activer(c, cle, actif, motif):
    c.execute('UPDATE finance_parametre SET actif = %s, maj_le = now() WHERE cle = %s RETURNING valeur', [actif, cle])
    valeur = c.fetchone()[0]
    c.execute('INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) '
              'VALUES (%s, %s, %s, now(), %s)', [cle, valeur, valeur, f'{motif} ({"activé" if actif else "désactivé"})'])


def appliquer(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("INSERT INTO finance_compte_argent (code, libelle, type, compte_syscohada, actif) VALUES "
                  "('PCA', 'Produits constatés d''avance', 'regularisation', '477', true) "
                  "ON CONFLICT (code) DO NOTHING")
        # Out of the result into 477 (D 7061 / C 477), and back (D 477 / C 7061): the service fees R01 never go out
        c.execute("INSERT INTO finance_nature (code, famille, libelle, compte_syscohada, sens_attendu, actif, "
                  "commentaire) VALUES "
                  "('R19', 'R', 'Frais de service constatés d''avance', '7061', 'sortie', true, %s), "
                  "('R20', 'R', 'Frais de service rendus au résultat', '7061', 'entree', true, %s) "
                  "ON CONFLICT (code) DO NOTHING",
                  ["Cut-off de fin de mois (ADR-034) : séjour pas encore commencé, sur le compte PCA (477)",
                   "Cut-off (ADR-034) : séjour commencé ou annulé, retour du compte PCA (477) au résultat"])
        for cle, actif in PARAMETRES:
            _activer(c, cle, actif, MOTIF)


def revenir(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("UPDATE finance_compte_argent SET actif = false WHERE code = 'PCA'")
        c.execute("UPDATE finance_nature SET actif = false WHERE code IN ('R19', 'R20')")
        for cle, actif in PARAMETRES:
            _activer(c, cle, not actif, 'Retour arrière de la migration 0021')


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0020_programme_fondateurs'),
    ]

    operations = [
        migrations.RunPython(appliquer, revenir),
    ]
