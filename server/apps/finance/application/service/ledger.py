"""Writes movements in the ledger, corrects them, reads the parameters."""
import uuid
from dataclasses import replace
from decimal import Decimal
from typing import Iterable

from apps.finance.application.ports import Alertes, Clock, GrandLivre, Journal, Parametres, TransactionManager
from apps.finance.domain.entities import (
    ENTREE,
    NATURES_COMPTE_COURANT,
    PERIODE_VERROUILLEE,
    TIERS_ASSOCIE,
    Ecriture,
    Ligne,
)
from apps.finance.domain.exceptions import MouvementRefuse
from apps.finance.domain.rules import inverse, preparer


class GrandLivreService:
    def __init__(self, *, grand_livre: GrandLivre, parametres: Parametres, alertes: Alertes, journal: Journal,
                 tx: TransactionManager, clock: Clock):
        self.grand_livre = grand_livre
        self.parametres = parametres
        self.alertes = alertes
        self.journal = journal
        self.tx = tx
        self.clock = clock

    def enregistrer(self, lignes: Iterable[Ligne], *, origine: str, par_id: uuid.UUID | None = None) -> list[int]:
        """Writes the lines, all or none, in the caller's transaction (FIN-01.6). Returns the ids of the new lines: a
        line of an external event already written is skipped (FIN-01.7). A refusal raises MouvementRefuse and alerts
        the finance team (FIN-01.4)."""
        lignes = list(lignes)
        origine = (origine or '').strip()
        try:
            if not origine:
                raise MouvementRefuse("L'origine du mouvement est obligatoire (paiement, versement, remboursement…).")
            if not lignes:
                return []
            maintenant = self.clock.now()
            ref = self.grand_livre.referentiels(lignes)
            ecritures = [preparer(ligne, ref, origine=origine, par_id=par_id, maintenant=maintenant)
                         for ligne in lignes]
            crees = []
            with self.tx.atomic():
                self._verifier_comptes_courants(ecritures)
                for ecriture in ecritures:
                    self._verifier_periode(ecriture)
                    pk = self.grand_livre.ecrire(ecriture)
                    if pk is None:
                        self._verifier_doublon(ecriture)
                    else:
                        crees.append(pk)
            return crees
        except MouvementRefuse as refus:
            self.alertes.mouvement_refuse(origine or 'inconnue', str(refus))
            raise

    def contre_passer(self, mouvement_id: int, *, motif: str, origine: str = 'correction',
                      par_id: uuid.UUID | None = None) -> int:
        """Cancels a line by an inverse line (FIN-01.3); both stay visible. A line is corrected once at most. The
        correction goes to the audit log (FIN-13.3)."""
        mouvement = self.grand_livre.mouvement(mouvement_id)
        if mouvement is None:
            raise MouvementRefuse(f'Ligne {mouvement_id} inconnue : rien à corriger.')
        ecriture = inverse(mouvement, motif=motif, origine=origine, par_id=par_id, maintenant=self.clock.now())
        with self.tx.atomic():
            # Two corrections of the same line at the same time: the second waits, then sees the first
            self.grand_livre.verrouiller(f'finance:correction:{mouvement_id}')
            if self.grand_livre.est_corrige(mouvement_id):
                raise MouvementRefuse(f'La ligne {mouvement_id} a déjà été corrigée.')
            self._verifier_comptes_courants([ecriture])
            self._verifier_periode(ecriture)
            pk = self.grand_livre.ecrire(ecriture)
            self.journal.correction(par_id, mouvement_id, pk, ecriture.ligne.motif)
        return pk

    def rectifier(self, nature: str, nouveau_montant: int, *, motif: str, origine: str, objet: dict,
                  par_id: uuid.UUID | None = None) -> list[int]:
        """Brings the amount of a nature for an object (booking, transfer, rental) to `nouveau_montant`: its lines in
        force are cancelled by inverse lines, and a new line carries the right amount (none if 0). Every line stays
        visible (FIN-01.3). For example, service fees lowered from 6 to 3 % after the payment."""
        if type(nouveau_montant) is not int or nouveau_montant < 0:
            raise MouvementRefuse('Le nouveau montant doit être un nombre entier de francs CFA, positif ou nul.')
        with self.tx.atomic():
            lignes = self.grand_livre.lignes_en_vigueur(nature, **objet)
            if not lignes:
                raise MouvementRefuse(f'Aucune ligne {nature} en vigueur pour cet objet : rien à rectifier.')
            ids = [self.contre_passer(m.id, motif=motif, origine=origine, par_id=par_id) for m in lignes]
            if nouveau_montant:
                nouvelle = replace(lignes[0].ligne, montant=nouveau_montant, motif=motif, date_evenement=None,
                                   externe_reference=None)
                ids += self.enregistrer([nouvelle], origine=origine, par_id=par_id)
            return ids

    def a_des_lignes(self, **filtres) -> bool:
        return self.grand_livre.a_des_lignes(**filtres)

    def parametre(self, cle: str) -> Decimal:
        """Value in force of a steered parameter (FIN-16). An unknown or inactive key is an error: an offer not open
        yet has no value to read."""
        trouve = self.parametres.lire(cle)
        if trouve is None:
            raise ValueError(f'Paramètre « {cle} » inconnu.')
        valeur, actif = trouve
        if not actif:
            raise ValueError(f'Paramètre « {cle} » inactif : son offre n\'est pas ouverte.')
        return valeur

    def _verifier_comptes_courants(self, ecritures: list[Ecriture]) -> None:
        """An associate's current account is never in debit (articles of association, art. 19): lines that would take
        out more than Kwa-Ba owes them are refused (a repayment above the balance, an advance cancelled after its
        repayment). The associate's account is locked until the end of the transaction."""
        variations: dict[str, int] = {}
        for e in ecritures:
            ligne = e.ligne
            if ligne.tiers_type == TIERS_ASSOCIE and ligne.tiers_id and ligne.nature in NATURES_COMPTE_COURANT:
                signe = ligne.montant if ligne.sens == ENTREE else -ligne.montant
                variations[str(ligne.tiers_id)] = variations.get(str(ligne.tiers_id), 0) + signe
        for associe_id, variation in sorted(variations.items()):
            if variation >= 0:
                continue
            self.grand_livre.verrouiller(f'finance:compte_courant:{associe_id}')
            solde = self.grand_livre.solde_compte_courant(associe_id)
            if solde + variation < 0:
                raise MouvementRefuse(
                    f"Le compte courant de l'associé deviendrait débiteur ({solde + variation} F CFA) : un compte "
                    "courant d'associé n'est jamais débiteur (statuts, art. 19).")

    def _verifier_periode(self, ecriture: Ecriture) -> None:
        if self.grand_livre.etat_periode(ecriture.mois) == PERIODE_VERROUILLEE:
            raise MouvementRefuse(f'La période {ecriture.mois:%m/%Y} est verrouillée : écriture refusée.')

    def _verifier_doublon(self, ecriture: Ecriture) -> None:
        """The event was already written: a delivery repeated with another amount is an anomaly to look at (the
        reconciliation with the provider will show it too)."""
        deja = self.grand_livre.deja_ecrite(ecriture)
        if deja is not None and deja.ligne.montant != ecriture.ligne.montant:
            self.alertes.evenement_rejoue(deja.id, ecriture.ligne.nature)
