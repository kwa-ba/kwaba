# Payouts to the partners (GL-11): hours after its due date from which a payout still not sent is late, and the
# finance team is alerted (once a day). 24 h, the delay of the payouts themselves after the arrival.
from django.db import migrations

MOTIF = 'Gestion des versements aux partenaires (GL-11), 19 novembre 2026'


def appliquer(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("INSERT INTO finance_parametre (cle, valeur, unite, categorie, offre_code, libelle, source, actif, "
                  "maj_le) VALUES ('versement_alerte_retard_heures', 24, 'heures', 'delai', 'STRUCTURE', "
                  "'Retard d''un versement à un partenaire avant alerte', %s, true, now()) "
                  "ON CONFLICT (cle) DO NOTHING", [MOTIF])
        c.execute("INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) "
                  "VALUES ('versement_alerte_retard_heures', NULL, 24, now(), %s)", [MOTIF])


def revenir(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("UPDATE finance_parametre SET actif = false, maj_le = now() "
                  "WHERE cle = 'versement_alerte_retard_heures'")


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0013_associes_fonds_garantie'),
    ]

    operations = [
        migrations.RunPython(appliquer, revenir),
    ]
