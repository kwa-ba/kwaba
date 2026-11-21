"""Steering and reporting of the finance officer (GL-18, GL-21, GL-23), read from the ledger:
- the dashboard of a month: activity, revenue by offer, result, payment fee rate, cancellations, taxes, and the
  thresholds of the associates' decisions (break-even, advertising per booking, balance at the provider, the prudent
  scenario of the business plan);
- the statement of a partner (what is owed, paid, the commissions) and its yearly summary, and the monthly report to
  the associates with the comment of the referent;
- the inventory of the financial year: amortisation of the Solution (D20), the inventory book and the balances
  carried forward."""
import uuid
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from decimal import ROUND_HALF_UP, Decimal

from apps.finance.application.ports import Clock, Journal, Parametres, Periodes, Pilotage, TransactionManager
from apps.finance.domain.entities import PERIODE_VERROUILLEE, SORTIE, Ligne
from apps.finance.domain.exceptions import RestitutionRefusee

COMPTE_AMORTISSEMENTS = 'AMORTISSEMENTS'


def fin_du_mois(mois: date) -> date:
    return (mois + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def _pct(part, total) -> float | None:
    return round(100 * part / total, 2) if total else None


class PilotageService:
    def __init__(self, *, pilotage: Pilotage, parametres: Parametres, grand_livre, periodes: Periodes,
                 journal: Journal, tx: TransactionManager, clock: Clock):
        self.pilotage = pilotage
        self.parametres = parametres
        self.grand_livre = grand_livre
        self.periodes = periodes
        self.journal = journal
        self.tx = tx
        self.clock = clock

    def _p(self, cle: str) -> Decimal:
        """A steered value; 0 (inert) when unknown or inactive."""
        trouve = self.parametres.lire(cle)
        return Decimal(trouve[0]) if trouve and trouve[1] else Decimal(0)

    # --- Dashboard (GL-18) -----------------------------------------------------------------------------------------

    def tableau_de_bord(self, mois: date, *, solde_prestataire: int = 0) -> dict:
        """The figures of a month and of the year to date; `solde_prestataire`: the ledger balance at FedaPay."""
        mois = mois.replace(day=1)
        fin = min(fin_du_mois(mois), self.clock.now().date())
        annee = date(mois.year, 1, 1)
        resultat, cumul = self.pilotage.resultat(mois, fin), self.pilotage.resultat(annee, fin)
        activite = self.pilotage.activite(mois, fin)
        revenu = resultat['chiffre_affaires']
        payees = activite['reservations_payees']
        impot = max(Decimal(max(cumul['resultat'], 0)) * self._p('impot_societes') / 100,
                    Decimal(cumul['chiffre_affaires']) * self._p('impot_minimum') / 100)
        charges_fixes, prudent = int(self._p('charges_fixes_mois')), int(self._p('scenario_prudent_revenu_mois'))
        pub_max = int(self._p('publicite_par_reservation'))
        alerte, plafond = int(self._p('prestataire_solde_alerte')), int(self._p('prestataire_solde_plafond'))
        seuil_tva = int(self._p('tva_seuil'))
        seuils = [
            {'code': 'point_mort', 'libelle': 'Point mort : revenu du mois face aux charges fixes',
             'valeur': revenu, 'seuil': charges_fixes, 'ok': not charges_fixes or revenu >= charges_fixes},
            {'code': 'scenario_prudent', 'libelle': 'Revenu du mois face au scénario prudent',
             'valeur': revenu, 'seuil': prudent, 'ok': not prudent or revenu >= prudent},
            {'code': 'publicite', 'libelle': 'Publicité par réservation payée',
             'valeur': round(activite['publicite'] / payees) if payees else activite['publicite'], 'seuil': pub_max,
             'ok': not pub_max or (activite['publicite'] <= pub_max * max(payees, 1))},
            {'code': 'solde_prestataire', 'libelle': 'Solde chez le prestataire de paiement',
             'valeur': solde_prestataire, 'seuil': alerte, 'plafond': plafond,
             'ok': not alerte or solde_prestataire < alerte},
            {'code': 'tva', 'libelle': "Chiffre d'affaires de l'année face au seuil de la TVA",
             'valeur': cumul['chiffre_affaires'], 'seuil': seuil_tva,
             'ok': not seuil_tva or cumul['chiffre_affaires'] < seuil_tva},
        ]
        return {
            'mois': mois, 'au': fin,
            'activite': {**activite, 'taux_annulation': _pct(activite['annulations'], payees),
                         'taux_frais_reel': _pct(activite['frais_paiement'], revenu)},
            'resultat': resultat, 'cumul_annee': cumul,
            'marge_par_offre': self.pilotage.marge_par_offre(mois, fin),
            'fiscal': {'impot_estime': int(impot.quantize(Decimal(1), rounding=ROUND_HALF_UP)),
                       'taux_is': self._p('impot_societes'), 'taux_minimum': self._p('impot_minimum'),
                       'tva_seuil': seuil_tva, 'part_du_seuil_tva': _pct(cumul['chiffre_affaires'], seuil_tva)},
            'jours_en_ecart': self.pilotage.jours_en_ecart(mois, fin),
            'seuils': seuils,
        }

    # --- Partner statements and the associates' report (GL-21) -----------------------------------------------------

    def partenaires(self) -> list[dict]:
        return self.pilotage.partenaires()

    def releve(self, tiers_type: str, tiers_id: str, mois: date) -> dict:
        mois = mois.replace(day=1)
        return {'mois': mois, **self.pilotage.releve_partenaire(tiers_type, str(tiers_id), mois, fin_du_mois(mois))}

    def recapitulatif_annuel(self, tiers_type: str, tiers_id: str, annee: int) -> list[dict]:
        lignes = []
        for numero in range(1, 13):
            mois = date(annee, numero, 1)
            if mois > self.clock.now().date():
                break
            r = self.pilotage.releve_partenaire(tiers_type, str(tiers_id), mois, fin_du_mois(mois))
            lignes.append({'mois': mois, 'du': r['du'], 'verse': r['verse'], 'commissions': r['commissions'],
                           'solde_cloture': r['solde_cloture']})
        return lignes

    def commentaire(self, mois: date) -> dict | None:
        return self.pilotage.commentaire(mois.replace(day=1))

    def commenter(self, mois: date, texte: str, *, par_id: uuid.UUID | None) -> dict:
        texte = (texte or '').strip()[:5000]
        mois = mois.replace(day=1)
        with self.tx.atomic():
            self.pilotage.enregistrer_commentaire(mois, texte, par_id, self.clock.now())
            self.journal.tresorerie('rapport_commente', par_id, {'mois': f'{mois:%Y-%m}'})
        return self.pilotage.commentaire(mois)

    # --- Inventory of the financial year (GL-23) -------------------------------------------------------------------

    def amortissement_du(self, annee: int) -> dict:
        """Amortisation of the Solution for the year: straight line over its duration from its putting into service
        (parameters solution_valeur, solution_duree_mois, solution_mise_en_service as YYYYMM; 0: inert)."""
        valeur, duree = int(self._p('solution_valeur')), int(self._p('solution_duree_mois'))
        service = int(self._p('solution_mise_en_service'))
        vide = {'annee': annee, 'valeur': valeur, 'duree_mois': duree, 'mois': 0, 'du': 0,
                'ecrit': self.pilotage.amortissement_ecrit(annee)}
        if not (valeur and duree and service):
            return vide
        debut = date(service // 100, service % 100, 1)
        if debut.year > annee:
            return vide
        mois_avant = max(0, (annee - debut.year) * 12 - (debut.month - 1))
        mois = max(0, min(12 - (debut.month - 1 if debut.year == annee else 0), duree - mois_avant))
        cumul_avant = self.pilotage.amortissement_cumule_avant(annee)
        du = int((Decimal(valeur) * mois / duree).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if mois_avant + mois >= duree:
            du = valeur - cumul_avant  # the last year takes what is left
        return {**vide, 'mois': mois, 'du': max(du, 0)}

    def ecrire_inventaire(self, annee: int, *, par_id: uuid.UUID | None) -> dict:
        """Writes what the amortisation of a finished year still lacks, dated 31 December (its month must be open)."""
        if date(annee + 1, 1, 1) > self.clock.now().date():
            raise RestitutionRefusee("Les écritures d'inventaire se passent une fois l'exercice terminé.")
        decembre = date(annee, 12, 1)
        if any(p['mois'] == decembre and p['etat'] == PERIODE_VERROUILLEE for p in self.periodes.toutes()):
            raise RestitutionRefusee(f'12/{annee} est clôturé : ses écritures d\'inventaire ne changent plus.')
        a = self.amortissement_du(annee)
        manque = a['du'] - a['ecrit']
        if manque <= 0:
            return {**a, 'ajoute': 0}
        ligne = Ligne(nature='D20', offre='STRUCTURE', montant=manque, sens=SORTIE, compte_argent=COMPTE_AMORTISSEMENTS,
                      piece_reference=f'INV-{annee}', externe_reference=f'inventaire:amortissement:{annee}:{a["ecrit"]}',
                      date_evenement=datetime.combine(date(annee, 12, 31), time(23), tzinfo=dt_timezone.utc),
                      motif=f'Amortissement de la Solution, exercice {annee} : {a["mois"]} mois sur {a["duree_mois"]}')
        with self.tx.atomic():
            self.grand_livre.enregistrer([ligne], origine='inventaire', par_id=par_id)
            self.journal.tresorerie('inventaire_ecrit', par_id, {'annee': annee, 'montant': manque})
        return {**a, 'ecrit': a['ecrit'] + manque, 'ajoute': manque}

    def livre_inventaire(self, annee: int, balance: list[dict]) -> dict:
        """The inventory book of the year (AUDCIF art. 19): the closing balances, the inventory entries, the summary
        balance sheet and income statement, and the balances carried forward to the next year."""
        bilan = [c for c in balance if c['compte_general'][:1] in '12345']
        resultat_comptes = [c for c in balance if c['compte_general'][:1] in '678']
        produits = -sum(c['solde_cloture'] for c in resultat_comptes if c['compte_general'][:1] in '78')
        charges = sum(c['solde_cloture'] for c in resultat_comptes if c['compte_general'][:1] == '6')
        resultat = produits - charges
        actif = [c for c in bilan if c['solde_cloture'] > 0]
        passif = [c for c in bilan if c['solde_cloture'] < 0]
        compte_resultat = '131' if resultat >= 0 else '139'
        a_nouveaux = [{'compte_general': c['compte_general'], 'libelle': c['libelle'], 'solde': c['solde_cloture']}
                      for c in bilan if c['solde_cloture']]
        a_nouveaux.append({'compte_general': compte_resultat, 'solde': -resultat,
                           'libelle': f"Résultat net de l'exercice {annee} : "
                                      f"{'bénéfice' if resultat >= 0 else 'perte'}, en attente d'affectation"})
        return {
            'annee': annee, 'ecritures': self.pilotage.ecritures_inventaire(annee),
            'amortissement': self.amortissement_du(annee),
            'bilan': {'actif': actif, 'passif': passif, 'total_actif': sum(c['solde_cloture'] for c in actif),
                      'total_passif': -sum(c['solde_cloture'] for c in passif)},
            'compte_de_resultat': {'produits': produits, 'charges': charges, 'resultat': resultat},
            'a_nouveaux': a_nouveaux,
            'equilibre': sum(c['solde_cloture'] for c in balance) == 0,
        }


__all__ = ['PilotageService', 'fin_du_mois']
