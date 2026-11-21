# Deposit of the short stays, decision v3 of 18 November 2026 (ADR-036, DEV-F1): the deposit is a rate of the nights'
# price chosen by the host (10 % proposed, 40 % at most, warning above 20 %), rounded to 500 F, between 5 000 F and the
# absolute net of 150 000 F; the cap in nights is dropped. The enhanced guarantee (option b) is back: its fee is
# Kwa-Ba's revenue (R07). The escrowed deposit (option c) stays off until FedaPay confirms it costs no fee.
from django.db import migrations

MOTIF = 'Décision caution v3 du 18 novembre 2026 (ADR-036)'
NOUVEAUX = [
    ('caution_pct_plafond', 40, 'pourcentage', 'plafond', 'Caution séquestrée : taux maximal du prix des nuitées'),
    ('caution_pct_reco', 10, 'pourcentage', 'tarif', 'Caution séquestrée : taux proposé à l''hôte'),
    ('caution_pct_alerte', 20, 'pourcentage', 'seuil', 'Caution séquestrée : avertissement à l''hôte au-delà'),
    ('caution_min_fcfa', 5000, 'fcfa', 'plafond', 'Caution séquestrée : montant minimum (en dessous, pas de caution)'),
    ('caution_arrondi_fcfa', 500, 'fcfa', 'interne', 'Caution séquestrée : arrondi du montant'),
    ('caution_assiette', 1, 'code', 'interne', 'Assiette de la caution : 1 = prix des nuitées seules'),
    ('caution_sequestre_active', 0, 'code', 'interne',
     'Option c (caution séquestrée) ouverte aux hôtes : 0 tant que FedaPay n''a pas confirmé le séquestre sans frais'),
]
CHANGES = [('garantie_renforcee_beneficiaire', 1, True), ('caution_plafond_nuits', None, False)]


def _historiser(c, cle, avant, apres, motif):
    c.execute('INSERT INTO finance_parametre_histo (cle, valeur_avant, valeur_apres, date_effet, motif) '
              'VALUES (%s, %s, %s, now(), %s)', [cle, avant, apres, motif])


def appliquer(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        for cle, valeur, unite, categorie, libelle in NOUVEAUX:
            c.execute("INSERT INTO finance_parametre (cle, valeur, unite, categorie, offre_code, libelle, source, "
                      "actif, maj_le) VALUES (%s, %s, %s, %s, 'COURTE_DUREE', %s, %s, true, now()) "
                      "ON CONFLICT (cle) DO NOTHING", [cle, valeur, unite, categorie, libelle, MOTIF])
            _historiser(c, cle, None, valeur, MOTIF)
        for cle, valeur, actif in CHANGES:
            c.execute('SELECT valeur FROM finance_parametre WHERE cle = %s', [cle])
            avant = c.fetchone()[0]
            apres = avant if valeur is None else valeur
            c.execute('UPDATE finance_parametre SET valeur = %s, actif = %s, maj_le = now() WHERE cle = %s',
                      [apres, actif, cle])
            _historiser(c, cle, avant, apres, f'{MOTIF}{"" if actif else " (désactivé)"}')
        c.execute("UPDATE finance_nature SET actif = true, commentaire = %s WHERE code = 'R07'",
                  ["Forfait de la Garantie Kwa-Ba renforcée (option b) : recette de Kwa-Ba, qui porte la garantie "
                   "(décision caution v3, ADR-036)"])


def revenir(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute('UPDATE finance_parametre SET actif = false WHERE cle = ANY(%s)', [[p[0] for p in NOUVEAUX]])
        c.execute("UPDATE finance_parametre SET valeur = 0 WHERE cle = 'garantie_renforcee_beneficiaire'")
        c.execute("UPDATE finance_parametre SET actif = true WHERE cle = 'caution_plafond_nuits'")
        c.execute("UPDATE finance_nature SET actif = false WHERE code = 'R07'")


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0022_capital_souscrit'),
    ]

    operations = [
        migrations.RunPython(appliquer, revenir),
    ]
