# Decision of the associates, 19 November 2026: a host is paid 48 h after the traveller's arrival (instead of 24 h),
# for the bookings made from now on (CGV version 2.5). A booking keeps the delay in force when it was made: the site
# reads the value of versement_hote_heures at the booking's date, from this history (GL-20).
# Also the rate of the airport transfers kept by Kwa-Ba, set on the Tarifs page, gets its parameter (15 %).
from django.db import migrations

MOTIF = 'Décision des associés du 19 novembre 2026 : versement à l\'hôte 48 h après l\'arrivée (CGV 2.5)'


def appliquer(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("SELECT valeur FROM finance_parametre WHERE cle = 'versement_hote_heures'")
        avant = c.fetchone()[0]
        c.execute("UPDATE finance_parametre SET valeur = 48, source = 'CGV art. 8.1 (version 2.5)', maj_le = now() "
                  "WHERE cle = 'versement_hote_heures'")
        c.execute("INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) "
                  "VALUES ('versement_hote_heures', %s, 48, now(), %s)", [avant, MOTIF])
        # The accounts of the guarantee fund are decided (19 November 2026): no longer « to be confirmed »
        c.execute("UPDATE finance_nature SET commentaire = %s WHERE code = 'G01'",
                  ["Dotation aux provisions pour garanties données aux clients (6911 / 192) : 10 % du revenu net du "
                   "mois ; réintégrée au résultat fiscal, provision ajustée au risque probable à la clôture annuelle"])
        c.execute("UPDATE finance_nature SET commentaire = %s WHERE code = 'G02'",
                  ["Reprise de la provision (192 / 7911) pour le sinistre couvert, avec la référence de la décision"])
        c.execute("INSERT INTO finance_parametre (cle, valeur, unite, categorie, offre_code, libelle, source, actif, "
                  "maj_le) VALUES ('commission_transfert', 15, 'pourcentage', 'tarif', 'TRANSFERT', "
                  "'Part du prix d''un transfert gardée par Kwa-Ba', 'Page Tarifs', true, now()) "
                  "ON CONFLICT (cle) DO NOTHING")
        c.execute("INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) "
                  "VALUES ('commission_transfert', NULL, 15, now(), 'Taux de la page Tarifs, repris au référentiel')")


def revenir(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("UPDATE finance_parametre SET valeur = 24, maj_le = now() WHERE cle = 'versement_hote_heures'")
        c.execute("INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) "
                  "VALUES ('versement_hote_heures', 48, 24, now(), 'Retour arrière de la migration 0015')")
        c.execute("UPDATE finance_parametre SET actif = false WHERE cle = 'commission_transfert'")


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0014_alerte_versements'),
    ]

    operations = [
        migrations.RunPython(appliquer, revenir),
    ]
