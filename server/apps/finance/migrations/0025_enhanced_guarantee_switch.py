# Enhanced guarantee (option b) kept open by the decision of 22 November 2026 (D-CGV-1), with a switch to close it
# quickly if the CIMA lawyer asks: `garantie_renforcee_active` (1 = open).
from django.db import migrations

MOTIF = 'Décision D-CGV-1 du 22 novembre 2026 : garantie renforcée ouverte, interrupteur de fermeture rapide'
CLE = 'garantie_renforcee_active'


def apply(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("INSERT INTO finance_parametre (cle, valeur, unite, categorie, offre_code, libelle, source, actif, "
                  "maj_le) VALUES (%s, 1, 'code', 'interne', 'COURTE_DUREE', %s, %s, true, now()) "
                  "ON CONFLICT (cle) DO NOTHING",
                  [CLE, 'Option b (garantie renforcée) ouverte aux hôtes : 0 la ferme (avis avocat CIMA)', MOTIF])
        c.execute('INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) '
                  'VALUES (%s, NULL, 1, now(), %s)', [CLE, MOTIF])


def revert(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute('UPDATE finance_parametre SET actif = false WHERE cle = %s', [CLE])


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0024_damage_compensation_nature'),
    ]

    operations = [
        migrations.RunPython(apply, revert),
    ]
