"""Money accounts and bank statements."""
import uuid
from datetime import date, timedelta

from apps.finance.application.ports import (
    Clock,
    ComptesArgent,
    Journal,
    Periodes,
    Releves,
    TransactionManager,
    Virements,
)
from apps.finance.domain.entities import (
    ENTREE,
    PERIODE_VERROUILLEE,
    SORTIE,
    TOLERANCE_JOURS_VIREMENT,
    TYPES_COMPTE_BANQUE,
    TYPES_SANS_RELEVE,
    OperationExterne,
    Virement,
)
from apps.finance.domain.exceptions import VirementRefuse

from .reconciliation import RapprochementService


class TresorerieService:
    """The money accounts (which are open, since when) and the bank statements: a statement imported in CSV is read,
    each line matched with the transfer it is (by its reference, or by its amount within a few days), and every day
    it covers reconciled on three sides like FedaPay's. A line nobody explains (bank fees, an unknown payment) is
    regularised from the reconciliation screen."""

    def __init__(self, *, comptes: ComptesArgent, virements: Virements, releves: Releves,
                 rapprochement: RapprochementService, periodes: Periodes, journal: Journal, tx: TransactionManager,
                 clock: Clock):
        self.comptes = comptes
        self.virements = virements
        self.releves = releves
        self.rapprochement = rapprochement
        self.periodes = periodes
        self.journal = journal
        self.tx = tx
        self.clock = clock

    def comptes_argent(self) -> list[dict]:
        return [{**c, 'banque': c['type'] in TYPES_COMPTE_BANQUE, 'sans_releve': c['type'] in TYPES_SANS_RELEVE}
                for c in self.comptes.liste()]

    def activer(self, code: str, *, actif: bool, par_id: uuid.UUID | None) -> dict:
        """Opens a bank account (reconciled from today) or switches it off while nothing was written on it."""
        c = self.comptes.lire(code)
        if c is None or c['type'] not in TYPES_COMPTE_BANQUE:
            raise VirementRefuse('Seul un compte bancaire s\'active ou se désactive ici.')
        if c['actif'] == actif:
            return c
        if not actif and c['nb_lignes']:
            raise VirementRefuse('Ce compte a des lignes au grand livre : il reste ouvert (sa clôture se fait avec '
                                 "l'expert-comptable).")
        with self.tx.atomic():
            self.comptes.activer(code, actif, self.clock.now().date() if actif else None)
            self.journal.tresorerie('compte_active' if actif else 'compte_desactive', par_id, {'compte': code})
        return self.comptes.lire(code)

    def importer_releve(self, compte: str, texte: str, colonnes: dict, *, nom_fichier: str = '',
                        par_id: uuid.UUID | None) -> dict:
        from apps.finance.domain import releve

        c = self.comptes.lire(compte)
        if c is None or not c['actif'] or c['type'] not in TYPES_COMPTE_BANQUE:
            raise VirementRefuse("Choisissez un compte bancaire ouvert : il s'active dans Finance → Virements.")
        lignes = releve.lire(texte, colonnes)
        debut, fin = min(x.jour for x in lignes), max(x.jour for x in lignes)
        if fin >= self.clock.now().date():
            raise VirementRefuse("Le relevé contient des opérations d'aujourd'hui ou à venir : exportez-le jusqu'à hier, "
                                 'une journée se rapproche une fois terminée.')
        if c['actif_depuis'] and debut < c['actif_depuis']:
            raise VirementRefuse(f"Le relevé commence avant l'ouverture du compte dans l'appli "
                                 f"({c['actif_depuis']:%d/%m/%Y}) : exportez-le à partir de cette date.")
        verrouilles = {p['mois'] for p in self.periodes.toutes() if p['etat'] == PERIODE_VERROUILLEE}
        if any(x.jour.replace(day=1) in verrouilles for x in lignes):
            raise VirementRefuse('Le relevé couvre un mois clôturé : ses journées ne se réimportent plus.')
        operations = self._rapprocher(compte, lignes, debut, fin)
        with self.tx.atomic():
            jours, jour = [], debut
            while jour <= fin:
                jours.append(self.rapprochement.importer(compte, jour, [o for o in operations if o.jour == jour],
                                                         par_id=par_id))
                jour += timedelta(days=1)
            self.releves.enregistrer(compte=compte, debut=debut, fin=fin, nb_lignes=len(lignes),
                                     nom_fichier=(nom_fichier or 'releve.csv')[:150], contenu=texte, par_id=par_id,
                                     quand=self.clock.now())
            self.journal.tresorerie('releve_importe', par_id, {'compte': compte, 'debut': debut.isoformat(),
                                                               'fin': fin.isoformat(), 'lignes': len(lignes)})
        rapprochees = sum(1 for o in operations if o.kwaba_montant is not None)
        return {'debut': debut, 'fin': fin, 'lignes': len(lignes), 'rapprochees': rapprochees,
                'inconnues': len(lignes) - rapprochees,
                'jours': [{'jour': j['jour'], 'etat': j['etat'], 'ecart': j.get('ecart'), 'message': j['message']}
                          for j in jours]}

    def _rapprocher(self, compte: str, lignes, debut: date, fin: date) -> list[OperationExterne]:
        """Each statement line with the transfer it is: its reference first, else the same amount in the same
        direction within the tolerance, the closest date first; each transfer once."""
        marge = timedelta(days=TOLERANCE_JOURS_VIREMENT)
        libres = list(self.virements.ecrits_du_compte(compte, debut - marge, fin + marge))
        operations = []
        for ligne in sorted(lignes, key=lambda x: x.jour):
            sens_virement = 'entrant' if ligne.sens == ENTREE else 'sortant'

            def convient(v: Virement) -> bool:
                return (v.montant == ligne.montant and abs((v.date_virement - ligne.jour).days) <= marge.days
                        and (v.destination if sens_virement == 'entrant' else v.source) == compte)

            trouve = next((v for v in libres if v.reference_externe and v.reference_externe == ligne.reference
                           and convient(v)), None) or min(
                (v for v in libres if convient(v)), key=lambda v: abs((v.date_virement - ligne.jour).days),
                default=None)
            if trouve:
                libres.remove(trouve)
                operations.append(OperationExterne(
                    reference=trouve.cle_grand_livre, type='versement' if ligne.sens == SORTIE else 'encaissement',
                    sens=ligne.sens, jour=ligne.jour, kwaba_reference=trouve.numero, kwaba_montant=trouve.montant,
                    kwaba_statut='ecrit', externe_montant=ligne.montant, externe_frais=0, externe_statut='comptabilise',
                    moyen_paiement='VIREMENT'))
            else:
                operations.append(OperationExterne(
                    reference=ligne.reference, type='inconnu', sens=ligne.sens, jour=ligne.jour,
                    externe_montant=ligne.montant, externe_frais=0, externe_statut='comptabilise',
                    moyen_paiement='VIREMENT',
                    message=f'{ligne.libelle} : sans opération Kwa-Ba, à expliquer (frais bancaires, versement '
                            'inconnu) par une régularisation'.strip(' :')))
        return operations

    def liste_releves(self, compte: str | None = None, limite: int = 50) -> list[dict]:
        return self.releves.liste(compte, max(1, min(limite, 200)))
