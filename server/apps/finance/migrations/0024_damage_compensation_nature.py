# Damage compensation owed to the host (ADR-038): the part of a stay's escrowed deposit withheld for a damage, on a
# motivated decision, is the host's money until its dedicated payout leaves (T09). Partner money: both directions,
# like T01 to T04.
from django.db import migrations

LIBELLE = "Indemnité de dommage due à l'hôte"
COMMENTAIRE = "Retenue sur la caution d'un séjour, versée à l'hôte par un versement dédié (ADR-038)"


def add_nature(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("INSERT INTO finance_nature (code, famille, libelle, compte_syscohada, sens_attendu, actif, commentaire) "
                  "VALUES ('T10', 'T', %s, '47121', NULL, true, %s) ON CONFLICT (code) DO NOTHING",
                  [LIBELLE, COMMENTAIRE])


def deactivate_nature(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        # A nature with lines is never deleted: it is closed
        c.execute("UPDATE finance_nature SET actif = false WHERE code = 'T10'")


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0023_caution_sejours_v3'),
    ]

    operations = [
        migrations.RunPython(add_nature, deactivate_nature),
    ]
