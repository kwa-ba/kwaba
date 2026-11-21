"""Reads of the ledger for the finance officer's dashboard (GL-18), the partner statements (GL-21) and the inventory
of the financial year (GL-23). Every figure comes from finance_mouvement or its double entry (finance_ecriture)."""
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone

from apps.finance.application.ports import Pilotage
from apps.finance.infrastructure.persistence.models import RapportAssociesModel
from apps.finance.infrastructure.persistence.restitutions import _lignes

SIGNE = "CASE WHEN m.sens = 'entree' THEN m.montant ELSE -m.montant END"
# Kwa-Ba's commissions on a partner's work (host, hotel, vehicle and driver, experience)
COMMISSIONS = ('R02', 'R03', 'R04', 'R05', 'R15')


def _bornes(debut: date, fin: date) -> tuple[datetime, datetime]:
    return (datetime.combine(debut, time.min, tzinfo=dt_timezone.utc),
            datetime.combine(fin + timedelta(days=1), time.min, tzinfo=dt_timezone.utc))


class SqlPilotage(Pilotage):
    def resultat(self, debut, fin) -> dict:
        r = _lignes("""
            SELECT COALESCE(SUM(CASE WHEN compte_general LIKE '70%%' THEN credit - debit END), 0)::bigint AS ca,
                   COALESCE(SUM(CASE WHEN compte_general LIKE '7%%' THEN credit - debit END), 0)::bigint AS produits,
                   COALESCE(SUM(CASE WHEN compte_general LIKE '6%%' THEN debit - credit END), 0)::bigint AS charges,
                   COALESCE(SUM(CASE WHEN compte_general LIKE '8%%' THEN credit - debit END), 0)::bigint AS hao
            FROM finance_ecriture WHERE date_ecriture BETWEEN %s AND %s""", [debut, fin])[0]
        return {'chiffre_affaires': r['ca'], 'produits': r['produits'], 'charges': r['charges'], 'hao': r['hao'],
                'resultat': r['produits'] - r['charges'] + r['hao']}

    def activite(self, debut, fin) -> dict:
        a, b = _bornes(debut, fin)
        r = _lignes(f"""
            WITH p AS (SELECT * FROM finance_mouvement m WHERE m.date_evenement >= %s AND m.date_evenement < %s),
            annulees AS (SELECT DISTINCT reservation_id FROM p WHERE origine = 'annulation' AND reservation_id IS NOT NULL)
            SELECT
              (SELECT count(DISTINCT reservation_id) FROM p
               WHERE nature_code = 'R01' AND sens = 'entree' AND annule_mouvement_id IS NULL)::bigint AS payees,
              (SELECT COALESCE(SUM(montant), 0) FROM p WHERE sens = 'entree' AND annule_mouvement_id IS NULL
               AND nature_code IN (SELECT code FROM finance_nature WHERE famille IN ('R', 'T', 'C'))
               AND origine = 'paiement')::bigint AS volume,
              (SELECT count(*) FROM annulees)::bigint AS annulations,
              (SELECT COALESCE(SUM(montant), 0) FROM p m WHERE nature_code = 'T05' AND sens = 'sortie'
               AND annule_mouvement_id IS NULL)::bigint AS rembourse,
              (SELECT COALESCE(SUM({SIGNE}), 0) FROM p m WHERE nature_code = 'R08')::bigint AS conserve,
              (SELECT COALESCE(-SUM({SIGNE}), 0) FROM finance_mouvement m WHERE nature_code = 'D01'
               AND reservation_id IN (SELECT reservation_id FROM annulees))::bigint AS frais_perdus,
              (SELECT COALESCE(-SUM({SIGNE}), 0) FROM p m WHERE nature_code = 'D03')::bigint AS publicite,
              (SELECT COALESCE(-SUM({SIGNE}), 0) FROM p m WHERE nature_code = 'D01')::bigint AS frais_paiement
            """, [a, b])[0]
        return {'reservations_payees': r['payees'], 'volume_encaisse': r['volume'], 'annulations': r['annulations'],
                'rembourse': r['rembourse'], 'conserve': r['conserve'], 'frais_perdus': r['frais_perdus'],
                'publicite': r['publicite'], 'frais_paiement': r['frais_paiement']}

    def marge_par_offre(self, debut, fin) -> list[dict]:
        return _lignes("""
            SELECT offre_code, SUM(recettes)::bigint AS recettes, SUM(charges_variables)::bigint AS charges_variables,
                   SUM(marge)::bigint AS marge
            FROM finance_marge_par_offre WHERE mois_comptable BETWEEN %s AND %s
            GROUP BY offre_code HAVING SUM(recettes) <> 0 OR SUM(charges_variables) <> 0 ORDER BY offre_code""",
                       [debut.replace(day=1), fin])

    def jours_en_ecart(self, debut, fin) -> int:
        return _lignes("SELECT count(*)::bigint AS n FROM finance_rapprochement_jour "
                       "WHERE jour BETWEEN %s AND %s AND etat <> 'fait'", [debut, fin])[0]['n']

    def partenaires(self) -> list[dict]:
        return _lignes(f"""
            SELECT m.tiers_type, m.tiers_id, SUM({SIGNE})::bigint AS solde, max(m.date_evenement) AS derniere
            FROM finance_mouvement m JOIN finance_nature n ON n.code = m.nature_code
            WHERE n.famille = 'T' AND m.tiers_type IS NOT NULL AND m.tiers_type <> 'voyageur' AND m.tiers_id IS NOT NULL
            GROUP BY m.tiers_type, m.tiers_id ORDER BY max(m.date_evenement) DESC""")

    def releve_partenaire(self, tiers_type, tiers_id, debut, fin) -> dict:
        a, b = _bornes(debut, fin)
        tiers = "m.tiers_type = %s AND m.tiers_id = %s AND n.famille = 'T'"
        ouverture = _lignes(f"""SELECT COALESCE(SUM({SIGNE}), 0)::bigint AS s FROM finance_mouvement m
            JOIN finance_nature n ON n.code = m.nature_code WHERE {tiers} AND m.date_evenement < %s""",
                            [tiers_type, tiers_id, a])[0]['s']
        lignes = _lignes(f"""
            SELECT m.id, m.date_evenement AS date, m.piece_reference AS piece, m.nature_code AS nature,
                   n.libelle AS nature_libelle, COALESCE(m.motif, '') AS motif, ({SIGNE})::bigint AS montant_signe,
                   m.annule_mouvement_id
            FROM finance_mouvement m JOIN finance_nature n ON n.code = m.nature_code
            WHERE {tiers} AND m.date_evenement >= %s AND m.date_evenement < %s ORDER BY m.date_evenement, m.id""",
                         [tiers_type, tiers_id, a, b])
        commissions = _lignes(f"""
            WITH objets AS (
                SELECT DISTINCT m.reservation_id, m.transfert_id, m.location_id FROM finance_mouvement m
                JOIN finance_nature n ON n.code = m.nature_code WHERE {tiers})
            SELECT COALESCE(SUM({SIGNE}), 0)::bigint AS total FROM finance_mouvement m
            WHERE m.nature_code = ANY(%s) AND m.date_evenement >= %s AND m.date_evenement < %s
              AND (m.reservation_id IN (SELECT reservation_id FROM objets)
                   OR m.transfert_id IN (SELECT transfert_id FROM objets)
                   OR m.location_id IN (SELECT location_id FROM objets))""",
                              [tiers_type, tiers_id, list(COMMISSIONS), a, b])[0]['total']
        verse = -sum(x['montant_signe'] for x in lignes if x['nature'] == 'T09')
        du = sum(x['montant_signe'] for x in lignes if x['nature'] != 'T09')
        return {'solde_ouverture': ouverture, 'lignes': lignes, 'commissions': commissions, 'verse': verse, 'du': du,
                'solde_cloture': ouverture + sum(x['montant_signe'] for x in lignes)}

    def ecritures_inventaire(self, annee) -> list[dict]:
        return _lignes(f"""
            SELECT m.id, m.date_evenement AS date, m.piece_reference AS piece, m.nature_code AS nature,
                   n.libelle AS nature_libelle, n.compte_syscohada AS compte, c.compte_syscohada AS contrepartie,
                   COALESCE(m.motif, '') AS motif, ({SIGNE})::bigint AS montant_signe
            FROM finance_mouvement m JOIN finance_nature n ON n.code = m.nature_code
            JOIN finance_compte_argent c ON c.code = m.compte_argent_code
            WHERE c.type IN ('reserve', 'amortissement') AND m.mois_comptable BETWEEN %s AND %s
            ORDER BY m.date_evenement, m.id""", [date(annee, 1, 1), date(annee, 12, 1)])

    def amortissement_ecrit(self, annee) -> int:
        return _lignes(f"""SELECT COALESCE(-SUM({SIGNE}), 0)::bigint AS s FROM finance_mouvement m
            WHERE m.nature_code = 'D20' AND m.compte_argent_code = 'AMORTISSEMENTS'
              AND m.mois_comptable BETWEEN %s AND %s""", [date(annee, 1, 1), date(annee, 12, 1)])[0]['s']

    def amortissement_cumule_avant(self, annee) -> int:
        return _lignes(f"""SELECT COALESCE(-SUM({SIGNE}), 0)::bigint AS s FROM finance_mouvement m
            WHERE m.nature_code = 'D20' AND m.compte_argent_code = 'AMORTISSEMENTS' AND m.mois_comptable < %s""",
                       [date(annee, 1, 1)])[0]['s']

    def amortisation_written_until(self, month) -> int:
        return _lignes(f"""SELECT COALESCE(-SUM({SIGNE}), 0)::bigint AS s FROM finance_mouvement m
            WHERE m.nature_code = 'D20' AND m.compte_argent_code = 'AMORTISSEMENTS' AND m.mois_comptable <= %s""",
                       [month])[0]['s']

    def commentaire(self, mois) -> dict | None:
        return RapportAssociesModel.objects.filter(mois=mois).values('mois', 'commentaire', 'maj_par_id',
                                                                      'maj_le').first()

    def enregistrer_commentaire(self, mois, texte, par_id, quand) -> None:
        RapportAssociesModel.objects.update_or_create(mois=mois, defaults={'commentaire': texte, 'maj_par_id': par_id,
                                                                           'maj_le': quand})
