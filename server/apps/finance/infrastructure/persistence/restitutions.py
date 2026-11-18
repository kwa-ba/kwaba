"""Reads of the reporting views and functions (sql_restitutions.py). Amounts come out as whole FCFA (int)."""
from datetime import date, timedelta

from django.db import DatabaseError, connection, transaction

from apps.finance.application.ports import Restitutions
from apps.finance.domain.entities import FiltresMouvements, Page
from apps.finance.domain.exceptions import RestitutionRefusee
from apps.finance.domain.rules import debut_exercice
from apps.finance.infrastructure.persistence.models import NatureModel, OffreModel, RapportModel
from apps.finance.infrastructure.persistence.repositories import REFUS_BASE, diagnostic


def _lignes(sql: str, params=()) -> list[dict]:
    # A savepoint: a refusal of the database (unknown axis…) leaves the caller's transaction usable
    with transaction.atomic(), connection.cursor() as curseur:
        curseur.execute(sql, params)
        noms = [colonne.name for colonne in curseur.description]
        return [dict(zip(noms, ligne)) for ligne in curseur.fetchall()]


def _page(colonnes: str, depuis: str, conditions: list[str], params: list, ordre: str, decalage: int,
          limite: int) -> Page:
    """One page of a query and the total number of rows after filters."""
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ''
    total = _lignes(f'SELECT count(*)::bigint AS n FROM {depuis}{where}', params)[0]['n']
    lignes = _lignes(f'SELECT {colonnes} FROM {depuis}{where} ORDER BY {ordre} LIMIT %s OFFSET %s',
                     [*params, limite, decalage])
    return Page(lignes=lignes, total=total)


def _echapper_like(texte: str) -> str:
    return texte.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


# Filters of the ledger lines (GL-2): field → column of finance_pivot (p) or finance_mouvement (m). Fixed list: a
# filter value is always a parameter, never SQL
COLONNES_FILTRES = {
    'nature': 'p.nature_code', 'famille': 'p.famille', 'offre': 'p.offre_code', 'tiers_type': 'p.tiers_type',
    'tiers_id': 'p.tiers_id', 'compte_argent': 'p.compte_argent_code', 'sens': 'm.sens',
}
MOUVEMENTS = 'finance_pivot p JOIN finance_mouvement m ON m.id = p.id'
COLONNES_MOUVEMENT = ('p.id, p.date_evenement, p.famille, p.nature_code, p.nature_libelle, p.offre_code, '
                      'p.tiers_type, p.tiers_id, p.compte_argent_code, p.moyen_paiement_code, p.piece_reference, '
                      'p.montant, p.montant_signe, m.origine, m.annule_mouvement_id, m.motif')

# Label of a general account: its money account, else its kind of third party, else its first nature
LIBELLES_COMPTES = """
    SELECT DISTINCT ON (compte) compte, libelle FROM (
        SELECT compte_syscohada AS compte, libelle, 1 AS rang FROM finance_compte_argent
        UNION ALL SELECT compte_syscohada, libelle, 2 FROM finance_tiers_type
        UNION ALL SELECT compte_syscohada, libelle, 3 FROM finance_nature
    ) l WHERE compte IS NOT NULL ORDER BY compte, rang, libelle
"""
# Result accounts (SYSCOHADA classes 6, 7, 8) start each financial year at zero
RESULTAT = "left(compte_general, 1) IN ('6', '7', '8')"


class SqlRestitutions(Restitutions):
    def controle_invariants(self) -> list[dict]:
        return _lignes('SELECT invariant, libelle, anomalies::bigint AS anomalies FROM finance_controle_invariants')

    def codes_actifs(self) -> tuple[set[str], set[str]]:
        return (set(OffreModel.objects.filter(active=True).values_list('code', flat=True)),
                set(NatureModel.objects.filter(actif=True).values_list('code', flat=True)))

    def peut_on_cloturer(self, mois: date) -> list[dict]:
        return _lignes('SELECT controle, resultat, verdict, que_faire FROM finance_peut_on_cloturer(%s)', [mois])

    def synthese(self, debut, fin, axe1, axe2, familles, offres) -> list[dict]:
        try:
            return _lignes(
                'SELECT axe1, axe2, nb, montant FROM finance_synthese(%s, %s, %s, %s, %s::text[], %s::text[])',
                [debut, fin, axe1, axe2, familles, offres])
        except DatabaseError as erreur:
            diag = diagnostic(erreur)
            if getattr(diag, 'sqlstate', None) != REFUS_BASE:
                raise
            raise RestitutionRefusee(diag.message_primary) from erreur

    def rapport_defini(self, code: str) -> dict | None:
        return RapportModel.objects.filter(code=code, actif=True).values('axe1', 'axe2', 'familles', 'offres').first()

    def du_aux_partenaires(self) -> list[dict]:
        return _lignes('SELECT tiers_type, tiers_id, solde_du::bigint AS solde_du FROM finance_du_aux_partenaires '
                       'ORDER BY tiers_type, tiers_id')

    def derniers_mouvements(self, limite: int) -> list[dict]:
        return _lignes('SELECT p.id, p.date_evenement, p.famille, p.nature_code, p.nature_libelle, p.offre_code, '
                       'p.tiers_type, p.tiers_id, p.compte_argent_code, p.moyen_paiement_code, p.piece_reference, '
                       'p.montant, p.montant_signe, m.origine, m.annule_mouvement_id '
                       'FROM finance_pivot p JOIN finance_mouvement m ON m.id = p.id ORDER BY p.id DESC LIMIT %s',
                       [limite])

    def cautions_detenues(self) -> list[dict]:
        return _lignes('SELECT reservation_id, location_id, solde_detenu::bigint AS solde_detenu '
                       'FROM finance_cautions_detenues ORDER BY reservation_id, location_id')

    def soldes_comptes_argent(self) -> dict[str, int]:
        return {ligne['compte_argent_code']: ligne['solde_livre'] for ligne in _lignes(
            'SELECT compte_argent_code, solde_livre::bigint AS solde_livre FROM finance_solde_compte_argent')}

    def balance_generale(self, mois: date | None) -> list[dict]:
        sql = ('SELECT mois_comptable, compte_general, nb_lignes::bigint AS nb_lignes, '
               'total_debit::bigint AS total_debit, total_credit::bigint AS total_credit, solde::bigint AS solde '
               'FROM finance_balance_generale')
        return _lignes(sql) if mois is None else _lignes(sql + ' WHERE mois_comptable = %s', [mois])

    def controle_equilibre(self) -> list[dict]:
        return _lignes('SELECT mois_comptable, total_debit::bigint AS total_debit, '
                       'total_credit::bigint AS total_credit, ecart::bigint AS ecart FROM finance_controle_equilibre')

    def marge_par_offre(self, mois: date) -> list[dict]:
        return _lignes('SELECT offre_code, recettes::bigint AS recettes, '
                       'charges_variables::bigint AS charges_variables, marge::bigint AS marge '
                       'FROM finance_marge_par_offre WHERE mois_comptable = %s ORDER BY offre_code', [mois])

    def ecritures(self, mois: date) -> list[dict]:
        return _lignes('SELECT mouvement_id, ligne_ecriture, journal, compte_general, compte_auxiliaire, piece, '
                       'libelle, debit, credit FROM finance_ecriture WHERE mois_comptable = %s '
                       'ORDER BY mouvement_id, ligne_ecriture', [mois])

    # --- Books of article 19 (GL-2 to GL-6) ---------------------------------------------------------------------

    def mouvements(self, filtres: FiltresMouvements, decalage: int, limite: int) -> Page:
        conditions, params = [], []
        if filtres.du:
            conditions.append('p.date_evenement >= %s')
            params.append(filtres.du)
        if filtres.au:
            conditions.append('p.date_evenement < %s')
            params.append(filtres.au + timedelta(days=1))
        for champ, colonne in COLONNES_FILTRES.items():
            valeur = getattr(filtres, champ)
            if valeur:
                conditions.append(f'{colonne} = %s')
                params.append(valeur)
        if filtres.piece:
            conditions.append("p.piece_reference ILIKE %s ESCAPE '\\'")
            params.append(f'%{_echapper_like(filtres.piece)}%')
        return _page(COLONNES_MOUVEMENT, MOUVEMENTS, conditions, params, 'p.id DESC', decalage, limite)

    @staticmethod
    def _journal(debut: date, fin: date, journal: str | None) -> tuple[list[str], list]:
        conditions, params = ['date_ecriture BETWEEN %s AND %s'], [debut, fin]
        if journal:
            conditions.append('journal = %s')
            params.append(journal)
        return conditions, params

    def livre_journal(self, debut: date, fin: date, journal: str | None, decalage: int, limite: int) -> Page:
        conditions, params = self._journal(debut, fin, journal)
        return _page('date_ecriture, journal, mouvement_id, ligne_ecriture, compte_general, compte_auxiliaire, piece, '
                     'libelle, debit::bigint AS debit, credit::bigint AS credit, devise', 'finance_livre_journal',
                     conditions, params, 'date_ecriture, journal, mouvement_id, ligne_ecriture', decalage, limite)

    def totaux_journal(self, debut: date, fin: date, journal: str | None) -> dict:
        conditions, params = self._journal(debut, fin, journal)
        return _lignes('SELECT COALESCE(SUM(debit), 0)::bigint AS total_debit, '
                       'COALESCE(SUM(credit), 0)::bigint AS total_credit FROM finance_ecriture '
                       f"WHERE {' AND '.join(conditions)}", params)[0]

    def comptes(self) -> list[dict]:
        return _lignes(f'WITH lib AS ({LIBELLES_COMPTES}) '
                       "SELECT e.compte_general, COALESCE(lib.libelle, '') AS libelle, count(*)::bigint AS nb_lignes, "
                       'SUM(e.debit - e.credit)::bigint AS solde FROM finance_ecriture e '
                       'LEFT JOIN lib ON lib.compte = e.compte_general '
                       'GROUP BY e.compte_general, lib.libelle ORDER BY e.compte_general')

    def auxiliaires(self, compte: str) -> list[dict]:
        return _lignes('SELECT compte_auxiliaire, count(*)::bigint AS nb_lignes, '
                       'SUM(debit - credit)::bigint AS solde FROM finance_ecriture '
                       'WHERE compte_general = %s AND compte_auxiliaire IS NOT NULL '
                       'GROUP BY compte_auxiliaire ORDER BY compte_auxiliaire', [compte])

    def grand_livre_compte(self, compte: str, auxiliaire: str | None, debut: date, fin: date, decalage: int,
                           limite: int) -> Page:
        # The running balance is computed over every entry of the account (of its financial year for a result
        # account), then the period is cut out of it
        filtre_compte, params = 'compte_general = %s', [compte]
        if auxiliaire:
            filtre_compte += ' AND compte_auxiliaire = %s'
            params.append(auxiliaire)
        ecritures = (
            '(SELECT date_ecriture, journal, mouvement_id, ligne_ecriture, compte_auxiliaire, piece, libelle, '
            'debit::bigint AS debit, credit::bigint AS credit, '
            f'SUM(debit - credit) OVER (PARTITION BY CASE WHEN {RESULTAT} THEN extract(year FROM date_ecriture) END '
            'ORDER BY date_ecriture, mouvement_id, ligne_ecriture ROWS UNBOUNDED PRECEDING)::bigint AS solde_progressif '
            f'FROM finance_ecriture WHERE {filtre_compte}) x')
        # The parameters of the sub-query come first in the SQL text
        return _page('*', ecritures, ['date_ecriture BETWEEN %s AND %s'], [*params, debut, fin],
                     'date_ecriture, mouvement_id, ligne_ecriture', decalage, limite)

    def solde_compte_avant(self, compte: str, auxiliaire: str | None, avant: date, depuis: date | None) -> dict:
        conditions, params = ['compte_general = %s', 'date_ecriture < %s'], [compte, avant]
        if auxiliaire:
            conditions.append('compte_auxiliaire = %s')
            params.append(auxiliaire)
        if depuis:
            conditions.append('date_ecriture >= %s')
            params.append(depuis)
        ligne = _lignes('SELECT COALESCE(SUM(debit), 0)::bigint AS total_debit, '
                        'COALESCE(SUM(credit), 0)::bigint AS total_credit FROM finance_ecriture '
                        f"WHERE {' AND '.join(conditions)}", params)[0]
        return {**ligne, 'solde_ouverture': ligne['total_debit'] - ligne['total_credit']}

    def balance(self, debut: date, fin: date) -> list[dict]:
        # Opening balance: every earlier entry for a balance sheet account, those of the financial year for a result
        # account (no carry-over of a result)
        exercice = debut_exercice(debut)
        ouverture = f'date_ecriture < %s AND (NOT {RESULTAT} OR date_ecriture >= %s)'
        return _lignes(
            f'WITH lib AS ({LIBELLES_COMPTES}), b AS ('
            'SELECT compte_general, '
            f'SUM(CASE WHEN {ouverture} THEN debit - credit ELSE 0 END)::bigint AS solde_ouverture, '
            'SUM(CASE WHEN date_ecriture >= %s THEN debit ELSE 0 END)::bigint AS total_debit, '
            'SUM(CASE WHEN date_ecriture >= %s THEN credit ELSE 0 END)::bigint AS total_credit '
            'FROM finance_ecriture WHERE date_ecriture <= %s GROUP BY compte_general) '
            "SELECT b.compte_general, COALESCE(lib.libelle, '') AS libelle, b.solde_ouverture, b.total_debit, "
            'b.total_credit, (b.solde_ouverture + b.total_debit - b.total_credit)::bigint AS solde_cloture '
            'FROM b LEFT JOIN lib ON lib.compte = b.compte_general '
            'WHERE b.solde_ouverture <> 0 OR b.total_debit <> 0 OR b.total_credit <> 0 '
            'ORDER BY b.compte_general',
            [debut, exercice, debut, debut, fin])

    def export_comptable(self, debut: date, fin: date) -> list[dict]:
        return _lignes('SELECT date_ecriture, journal, mouvement_id, ligne_ecriture, compte_general, '
                       'compte_auxiliaire, piece, libelle, debit::bigint AS debit, credit::bigint AS credit, devise, '
                       'nature_code, offre_code FROM finance_export_comptable '
                       'WHERE date_ecriture BETWEEN %s AND %s '
                       'ORDER BY date_ecriture, mouvement_id, ligne_ecriture', [debut, fin])

    def taux_frais_reel(self, mois: date) -> dict | None:
        lignes = _lignes('SELECT frais::bigint AS frais, revenu::bigint AS revenu, '
                         'volume_encaisse::bigint AS volume_encaisse, pct_du_revenu::float AS pct_du_revenu '
                         'FROM finance_taux_frais_reel WHERE mois_comptable = %s', [mois])
        return lignes[0] if lignes else None

    def solde_famille(self, famille: str) -> int:
        return _lignes('SELECT COALESCE(SUM(montant_signe), 0)::bigint AS solde FROM finance_mouvement_signe '
                       'WHERE famille = %s', [famille])[0]['solde']
