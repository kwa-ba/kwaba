# Share capital subscribed on the day of the articles of association (ADR-035, DEV-F6): a technical money account
# « APPORTS » (capital subscribed not paid, 4611), without a provider's statement. The lines are written by the command
# subscribe_capital, once per environment, since the associates differ between the preprod and the production.
from django.db import migrations


def appliquer(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("INSERT INTO finance_compte_argent (code, libelle, type, compte_syscohada, actif) VALUES "
                  "('APPORTS', 'Associés, capital souscrit non versé', 'apport', '4611', true) "
                  "ON CONFLICT (code) DO NOTHING")
        c.execute("UPDATE finance_nature SET commentaire = %s WHERE code = 'F01'",
                  ["Capital social (500 000 F, décision D4) : souscrit le 16 novembre 2026 sur le compte APPORTS, "
                   "libéré par virement interne quand l'argent arrive (ADR-035)"])


def revenir(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("UPDATE finance_compte_argent SET actif = false WHERE code = 'APPORTS'")


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0021_cut_off_parametres_fiscaux'),
    ]

    operations = [
        migrations.RunPython(appliquer, revenir),
    ]
