# Levels of the drivers aligned on the project book (driver charter B6, resolution 4; decision of 26 November 2026,
# ticket T-H24): the Confirmé level is removed, Excellence from 20 missions (10 for the Founders Programme) instead of
# 40. The part of the partner driver on a Grand Lomé transfer (3,000 F) is validated (decision 6, T-H14).
from django.db import migrations

MOTIF = 'Décision des associés du 26 novembre 2026 : niveaux des chauffeurs alignés sur le livre (T-H24)'
VALEURS = [('chauffeur_excellence_courses', 20, 40)]  # (key, new value, value set by 0018)
NOUVEAUX = [('chauffeur_excellence_courses_fondateur', 10, 'code', 'seuil',
             'Chauffeur Excellence, Programme Fondateurs (10 premiers chauffeurs, 6 mois) : courses sur la période')]
RETIRES = ['chauffeur_confirme_courses', 'chauffeur_confirme_note']
PART_TRANSFERT = ('transfert_part_chauffeur', 'Part du chauffeur partenaire, Grand Lome',
                  'Part du chauffeur partenaire, Grand Lome (a valider)')


def apply(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        for cle, valeur, _ in VALEURS:
            c.execute('SELECT valeur FROM finance_parametre WHERE cle = %s', [cle])
            ligne = c.fetchone()
            if ligne is None or ligne[0] == valeur:
                continue
            c.execute('UPDATE finance_parametre SET valeur = %s, maj_le = now() WHERE cle = %s', [valeur, cle])
            c.execute('INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) '
                      'VALUES (%s, %s, %s, now(), %s)', [cle, ligne[0], valeur, MOTIF])
        for cle, valeur, unite, categorie, libelle in NOUVEAUX:
            c.execute("INSERT INTO finance_parametre (cle, valeur, unite, categorie, offre_code, libelle, source, "
                      "actif, maj_le) VALUES (%s, %s, %s, %s, 'TRANSFERT', %s, %s, true, now()) "
                      "ON CONFLICT (cle) DO UPDATE SET actif = true", [cle, valeur, unite, categorie, libelle, MOTIF])
            c.execute('INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) '
                      'VALUES (%s, NULL, %s, now(), %s)', [cle, valeur, MOTIF])
        c.execute('UPDATE finance_parametre SET actif = false, maj_le = now() WHERE cle = ANY(%s)', [RETIRES])
        c.execute('UPDATE finance_parametre SET libelle = %s WHERE cle = %s', [PART_TRANSFERT[1], PART_TRANSFERT[0]])


def revert(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        for cle, valeur, avant in VALEURS:
            c.execute('UPDATE finance_parametre SET valeur = %s, maj_le = now() WHERE cle = %s AND valeur = %s',
                      [avant, cle, valeur])
            if c.rowcount:
                c.execute('INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) '
                          'VALUES (%s, %s, %s, now(), %s)', [cle, valeur, avant, f'Retour arrière : {MOTIF}'])
        c.execute('UPDATE finance_parametre SET actif = false WHERE cle = ANY(%s)', [[n[0] for n in NOUVEAUX]])
        c.execute('UPDATE finance_parametre SET actif = true WHERE cle = ANY(%s)', [RETIRES])
        c.execute('UPDATE finance_parametre SET libelle = %s WHERE cle = %s', [PART_TRANSFERT[2], PART_TRANSFERT[0]])


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0027_damage_procedure_delays'),
    ]

    operations = [
        migrations.RunPython(apply, revert),
    ]
