"""Sensitive actions of the finance module in the activity log (module activity), append only for the application
role. The rate changes and payouts of FIN-13.3 will join this adapter."""
from apps.finance.application.ports import Journal
from apps.activity import api as activity


class AuditJournal(Journal):
    def correction(self, par_id, mouvement_id: int, inverse_id: int, motif: str) -> None:
        activity.record('ecriture_corrigee', actor=par_id, mouvement=mouvement_id, ligne_inverse=inverse_id,
                        motif=motif)

    def cloture(self, par_id, mois) -> None:
        activity.record('periode_cloturee', actor=par_id, mois=f'{mois:%Y-%m}')

    def rapport_cree(self, par_id, code: str, titre: str) -> None:
        activity.record('rapport_cree', actor=par_id, code=code, titre=titre)

    def validation(self, action: str, par_id, validation) -> None:
        activity.record(f'validation_{action}', actor=par_id, operation=validation.operation,
                        objet=f'{validation.objet_type}:{validation.objet_id}', montant=validation.montant,
                        motif=validation.motif if action == 'demandee' else validation.resultat)

    def rapprochement(self, par_id, compte: str, jour, etat: str) -> None:
        activity.record('rapprochement_importe', actor=par_id, compte=compte, jour=jour.isoformat(), etat=etat)

    def regularisation(self, action: str, par_id, regularisation) -> None:
        r = regularisation
        activity.record(f'regularisation_{action}', actor=par_id, objet=f'regularisation:{r.id}',
                        jour=r.jour.isoformat(), operation=r.reference, nature=r.nature, sens=r.sens,
                        montant=r.montant, motif=r.motif)
