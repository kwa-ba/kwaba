# The guarantee fund is a reserve, not a provision (ADR-031, DEV-C1, doc 32 Q6): its allocation leaves the classes 6
# to 8, so the result of the month does not change; only the loss paid stays a charge.
# - G01 (allocation): 1301 / 118 instead of 6911 / 192. G02 (use): 118 / 1301 instead of 192 / 7911.
# - D04 (loss paid under the guarantee): 658 instead of 659 (DEV-C4).
# - Money account GARANTIE: a reserve on 118 (type « reserve »), still without a provider's statement.
# Every change of account is kept in finance_correspondance_histo; the numbers are to be confirmed by the chartered
# accountant, and another number is a new migration, never a change of code.
from django.db import migrations

MOTIF = 'ADR-031 : fonds de garantie en réserve, et non en provision (DEV-C1, DEV-C4, doc 32 Q6)'
NATURES = [
    ('G01', '6911', '1301', "Affectation au fonds de garantie (réserve 118) : 10 % du revenu net du mois "
                            "(finance_parametre fonds_garantie_taux), hors résultat ; comptes à confirmer par "
                            "l'expert-comptable"),
    ('G02', '7911', '1301', "Reprise de la réserve du fonds de garantie (118) pour le sinistre couvert, hors résultat, "
                            "avec la référence de la décision"),
    ('D04', '659', '658', "Sinistre payé au titre de la Garantie Kwa-Ba : seule charge liée au fonds de garantie"),
]


def _changer(c, code, avant, apres, commentaire, motif):
    c.execute('UPDATE finance_nature SET compte_syscohada = %s, commentaire = COALESCE(%s, commentaire) '
              'WHERE code = %s', [apres, commentaire, code])
    c.execute('INSERT INTO finance_correspondance_histo (nature_code, compte_avant, compte_apres, date_effet, motif) '
              'VALUES (%s, %s, %s, current_date, %s)', [code, avant, apres, motif])


def appliquer(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        for code, avant, apres, commentaire in NATURES:
            _changer(c, code, avant, apres, commentaire, MOTIF)
        c.execute("UPDATE finance_compte_argent SET libelle = 'Fonds de garantie (réserve)', type = 'reserve', "
                  "compte_syscohada = '118' WHERE code = 'GARANTIE'")


def revenir(apps, schema_editor):
    # Histories are append only: going back is a new dated change
    with schema_editor.connection.cursor() as c:
        for code, avant, apres, _ in NATURES:
            _changer(c, code, apres, avant, None, 'Retour arrière de la migration 0019')
        c.execute("UPDATE finance_compte_argent SET libelle = 'Fonds de garantie (provision)', type = 'provision', "
                  "compte_syscohada = '192' WHERE code = 'GARANTIE'")


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0018_seuils_chauffeurs'),
    ]

    operations = [
        migrations.RunPython(appliquer, revenir),
    ]
