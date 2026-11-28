"""Register of the deposits: held, retained, returned."""
import uuid
from dataclasses import replace

from apps.finance.application.ports import Cautions, Clock, TransactionManager
from apps.finance.domain.entities import (
    ETAT_CAUTION_DETENUE,
    ETAT_CAUTION_LITIGE,
    ETAT_CAUTION_RESTITUEE,
    ETAT_CAUTION_RETENUE,
    ETATS_CAUTION_EN_COURS,
    Caution,
)
from apps.finance.domain.exceptions import CautionRefusee

# --- Register of the deposits (GL-13, FIN-05) ----------------------------------------------------------------------


class CautionService:
    """Every deposit held for a traveller, from its receipt to its settlement: the traveller's money, never Kwa-Ba's.
    A deposit is settled once, with its document (receipt REC, or notice RET for a motivated withholding). During a
    damage dispute (ADR-048), the part not claimed is given back first, and only the claimed amount stays held."""

    def __init__(self, *, cautions: Cautions, tx: TransactionManager, clock: Clock):
        self.cautions = cautions
        self.tx = tx
        self.clock = clock

    def enregistrer(self, caution: Caution) -> Caution:
        """The deposit received (idempotent: the same object gives one entry)."""
        if type(caution.montant) is not int or caution.montant <= 0:
            raise CautionRefusee('Le montant de la caution doit être un nombre entier positif de francs CFA.')
        with self.tx.atomic():
            existante = self.cautions.lire(caution.objet_type, caution.objet_id, verrou=True)
            return existante or self.cautions.creer(replace(caution, statut=ETAT_CAUTION_DETENUE))

    def declarer_litige(self, objet_type: str, objet_id, *, montant: int) -> Caution:
        """Amount claimed for a damage, still held while it is decided (0 withdraws the claim)."""
        with self.tx.atomic():
            c = self._detenue(objet_type, objet_id)
            if not 0 <= montant <= c.montant - c.montant_rendu:
                raise CautionRefusee(f'Le montant réclamé doit être compris entre 0 et ce qui reste détenu '
                                     f'({c.montant - c.montant_rendu} F CFA).')
            c = replace(c, montant_conteste=montant, statut=ETAT_CAUTION_LITIGE if montant else ETAT_CAUTION_DETENUE)
            self.cautions.enregistrer(c)
        return c

    def rendre_en_partie(self, objet_type: str, objet_id, *, montant: int) -> Caution:
        """Part of a disputed deposit given back before the settlement: never what is still claimed or withheld."""
        with self.tx.atomic():
            c = self._detenue(objet_type, objet_id)
            garde = max(c.montant_conteste, c.montant_retenu)
            if not 0 < montant <= c.montant - c.montant_rendu - garde:
                raise CautionRefusee('On ne rend pas ce qui est encore réclamé ou retenu.')
            c = replace(c, montant_rendu=c.montant_rendu + montant)
            self.cautions.enregistrer(c)
        return c

    def decider_retenue(self, objet_type: str, objet_id, *, montant: int, motif: str, cgv_article: str,
                        par_id: uuid.UUID | None) -> Caution:
        """Amount to withhold, decided before the settlement (0 cancels it). A withholding needs its reason and the
        article of the terms of sale it relies on."""
        motif, cgv_article = (motif or '').strip(), (cgv_article or '').strip()
        with self.tx.atomic():
            c = self._detenue(objet_type, objet_id)
            if not 0 <= montant <= c.montant - c.montant_rendu:
                raise CautionRefusee(f'La retenue doit être comprise entre 0 et ce qui reste détenu '
                                     f'({c.montant - c.montant_rendu} F CFA).')
            if montant and (len(motif) < 5 or not cgv_article):
                raise CautionRefusee("Une retenue exige son motif et l'article des conditions générales qui la fonde.")
            c = replace(c, montant_retenu=montant, motif_retenue=motif if montant else '',
                        cgv_article=cgv_article if montant else '', decision_par_id=par_id if montant else None,
                        decision_le=self.clock.now() if montant else None)
            self.cautions.enregistrer(c)
        return c

    def solder(self, objet_type: str, objet_id, *, rendu: int, mode: str, document_numero: str) -> Caution:
        """The deposit settled: `rendu` given back in all (what was given back during a dispute included), the rest
        withheld as decided; its document must exist."""
        with self.tx.atomic():
            c = self._detenue(objet_type, objet_id)
            if rendu != c.montant - c.montant_retenu:
                raise CautionRefusee(f'Rendu attendu : {c.montant - c.montant_retenu} F CFA (caution moins la retenue).')
            if not document_numero:
                raise CautionRefusee('Une caution ne se solde pas sans son document (reçu ou avis de retenue).')
            c = replace(c, statut=ETAT_CAUTION_RETENUE if c.montant_retenu else ETAT_CAUTION_RESTITUEE, montant_rendu=rendu,
                        soldee_le=self.clock.now(), mode_restitution=mode[:120], document_numero=document_numero)
            self.cautions.enregistrer(c)
        return c

    def lire(self, objet_type: str, objet_id) -> Caution | None:
        return self.cautions.lire(objet_type, str(objet_id))

    def liste(self, statut: str | None = None, en_retard: bool = False, limite: int = 200) -> dict:
        """The register, with the total held (third pocket: never free money) and the deposits past their date."""
        maintenant = self.clock.now()
        # A deposit in dispute is held past its date on purpose (ADR-048): it is not late
        retard = self.cautions.liste(ETAT_CAUTION_DETENUE, maintenant, 500)
        lignes = retard if en_retard else self.cautions.liste(statut, None, max(1, min(limite, 500)))
        return {'cautions': lignes, 'total_detenu': self.cautions.total_detenu(), 'en_retard': len(retard)}

    def _detenue(self, objet_type, objet_id) -> Caution:
        c = self.cautions.lire(objet_type, str(objet_id), verrou=True)
        if c is None:
            raise CautionRefusee('Caution inconnue du registre.')
        if c.statut not in ETATS_CAUTION_EN_COURS:
            raise CautionRefusee('Cette caution est déjà soldée.')
        return c
