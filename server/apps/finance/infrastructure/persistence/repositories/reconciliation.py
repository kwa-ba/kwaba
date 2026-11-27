"""Reconciliation with the payment provider and regularisations."""
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone

from django.db import connection

from apps.finance.application.ports import Rapprochements, Regularisations
from apps.finance.domain.entities import (
    NATURE_FRAIS_PAIEMENT,
    PREFIXE_AJUSTEMENT_FRAIS,
    PREFIXE_REGULARISATION,
    RAPPROCHEMENT_EN_ERREUR,
    OperationExterne,
    Regularisation,
)
from apps.finance.infrastructure.persistence.models import (
    CompteArgentModel,
    RapprochementJourModel,
    RapprochementLigneModel,
    RegularisationModel,
    ReleveExterneModel,
)

# --- Reconciliation with the payment provider (GL-12) ---------------------------------------------------------------

# The operation a ledger line belongs to: its external reference, the operation a regularisation explains
# (« regul:<reference>:<id> ») or whose fees a line aligns on the statement (« frais:<reference>:<n> », ADR-047)
CLE_OPERATION = ("COALESCE(substring(m.externe_reference from "
                 f"'^(?:{PREFIXE_REGULARISATION}|{PREFIXE_AJUSTEMENT_FRAIS})(.*):[^:]*$'), m.externe_reference, '')")


# A line counts in its operation unless it corrects another one; the payment fees D01 always count, their corrections
# included: aligning them on a lower statement cancels them before writing the right amount (ADR-047)
COMPTEE_DANS_L_OPERATION = f"(m.annule_mouvement_id IS NULL OR m.nature_code = '{NATURE_FRAIS_PAIEMENT}')"


SIGNE = "CASE WHEN m.sens = 'entree' THEN m.montant ELSE -m.montant END"


CHAMPS_JOUR = ('solde_kwaba', 'solde_livre', 'solde_externe', 'frais', 'hors_grand_livre', 'internes',
               'nb_operations', 'nb_anomalies', 'etat', 'message')


def _bornes(jour) -> tuple[datetime, datetime]:
    """The day in UTC, like the accounting months (Lomé is UTC+0)."""
    debut = datetime.combine(jour, time.min, tzinfo=dt_timezone.utc)
    return debut, debut + timedelta(days=1)


def _operation(m: RapprochementLigneModel) -> OperationExterne:
    return OperationExterne(
        reference=m.reference, type=m.type, sens=m.sens, jour=m.jour, date_operation=m.date_operation,
        kwaba_reference=m.kwaba_reference, kwaba_montant=m.kwaba_montant, kwaba_statut=m.kwaba_statut,
        externe_montant=m.externe_montant, externe_frais=m.externe_frais, externe_statut=m.externe_statut,
        moyen_paiement=m.moyen_paiement_code, hors_grand_livre=m.hors_grand_livre, offre=m.offre_code,
        message=m.message_import)


class DjangoRapprochements(Rapprochements):
    def serialiser(self, compte, jour) -> None:
        with connection.cursor() as curseur:
            curseur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))',
                            [f'finance:rapprochement:{compte}:{jour.isoformat()}'])

    def compte_actif(self, compte) -> bool:
        return CompteArgentModel.objects.filter(code=compte, actif=True).exists()

    def remplacer(self, compte, jour, operations, quand) -> None:
        references = [op.reference for op in operations]
        RapprochementLigneModel.objects.filter(compte_argent_id=compte, jour=jour).exclude(
            reference__in=references).delete()
        for op in operations:
            RapprochementLigneModel.objects.update_or_create(
                compte_argent_id=compte, reference=op.reference,
                defaults={'jour': op.jour, 'type': op.type, 'sens': op.sens, 'date_operation': op.date_operation,
                          'kwaba_reference': op.kwaba_reference[:60], 'kwaba_montant': op.kwaba_montant,
                          'kwaba_statut': op.kwaba_statut[:30], 'externe_montant': op.externe_montant,
                          'externe_frais': op.externe_frais, 'externe_statut': op.externe_statut[:30],
                          'moyen_paiement_code': op.moyen_paiement, 'hors_grand_livre': op.hors_grand_livre,
                          'offre_code': op.offre, 'message_import': op.message[:500], 'importe_le': quand})
            if op.externe_montant is not None:
                # The provider's statement line (finance_releve_externe), with its real fees
                ReleveExterneModel.objects.update_or_create(
                    compte_argent_id=compte, externe_reference=op.reference,
                    defaults={'date_operation': op.date_operation or _bornes(op.jour)[0],
                              'montant': op.externe_montant, 'sens': op.sens, 'frais': op.externe_frais or 0,
                              'moyen_paiement_id': op.moyen_paiement, 'statut': op.externe_statut[:30]})

    def operations(self, compte, jour) -> list[OperationExterne]:
        return [_operation(m) for m in RapprochementLigneModel.objects.filter(compte_argent_id=compte, jour=jour)]

    def livre_par_reference(self, compte, references) -> dict[str, tuple[int, bool]]:
        if not references:
            return {}
        with connection.cursor() as curseur:
            curseur.execute(f"""
                SELECT {CLE_OPERATION} AS cle, SUM({SIGNE}),
                       bool_or(m.externe_reference LIKE '{PREFIXE_REGULARISATION}%%')
                FROM finance_mouvement m
                WHERE m.compte_argent_code = %s AND {COMPTEE_DANS_L_OPERATION} AND {CLE_OPERATION} = ANY(%s)
                GROUP BY 1""", [compte, list(references)])
            return {cle: (int(total), bool(regul)) for cle, total, regul in curseur.fetchall()}

    def frais_ecrits(self, compte, reference) -> tuple[list[tuple[int, int]], int]:
        with connection.cursor() as curseur:
            curseur.execute(f"""
                SELECT m.id, m.montant, m.annule_mouvement_id IS NULL
                       AND NOT EXISTS (SELECT 1 FROM finance_mouvement c WHERE c.annule_mouvement_id = m.id)
                FROM finance_mouvement m
                WHERE m.compte_argent_code = %s AND m.nature_code = %s AND {CLE_OPERATION} = %s
                ORDER BY m.id""", [compte, NATURE_FRAIS_PAIEMENT, reference])
            lignes = curseur.fetchall()
        return [(pk, montant) for pk, montant, en_vigueur in lignes if en_vigueur], len(lignes)

    def internes(self, compte, jour) -> int:
        debut, fin = _bornes(jour)
        with connection.cursor() as curseur:
            curseur.execute(f"""
                SELECT COALESCE(SUM({SIGNE}), 0)
                FROM finance_mouvement m
                WHERE m.compte_argent_code = %s AND m.date_evenement >= %s AND m.date_evenement < %s
                  AND NOT ({COMPTEE_DANS_L_OPERATION}
                           AND {CLE_OPERATION} IN (SELECT reference FROM finance_rapprochement_ligne
                                                   WHERE compte_argent_code = %s))""",
                            [compte, debut, fin, compte])
            return int(curseur.fetchone()[0])

    def juger(self, compte, jugements) -> None:
        for reference, livre, etat, message in jugements:
            RapprochementLigneModel.objects.filter(compte_argent_id=compte, reference=reference).update(
                livre_montant=livre, etat=etat, message=message)

    def enregistrer_jour(self, compte, jour, totaux, quand) -> None:
        RapprochementJourModel.objects.update_or_create(
            compte_argent_id=compte, jour=jour,
            defaults={**{c: totaux[c] for c in CHAMPS_JOUR}, 'calcule_le': quand})

    def echec(self, compte, jour, message, quand) -> None:
        RapprochementJourModel.objects.update_or_create(
            compte_argent_id=compte, jour=jour,
            defaults={'etat': RAPPROCHEMENT_EN_ERREUR, 'message': message[:500], 'calcule_le': quand})

    def jour(self, compte, jour) -> dict | None:
        return (RapprochementJourModel.objects.filter(compte_argent_id=compte, jour=jour)
                .values('jour', 'ecart', 'calcule_le', *CHAMPS_JOUR).first())

    def jours(self, compte, debut, fin) -> list[dict]:
        return list(RapprochementJourModel.objects.filter(compte_argent_id=compte, jour__gte=debut, jour__lte=fin)
                    .order_by('jour').values('jour', 'ecart', 'calcule_le', *CHAMPS_JOUR))

    def lignes(self, compte, jour) -> list[dict]:
        return list(RapprochementLigneModel.objects.filter(compte_argent_id=compte, jour=jour)
                    .order_by('date_operation', 'reference')
                    .values('reference', 'type', 'sens', 'date_operation', 'kwaba_reference', 'kwaba_montant',
                            'kwaba_statut', 'externe_montant', 'externe_frais', 'externe_statut',
                            'moyen_paiement_code', 'hors_grand_livre', 'offre_code', 'livre_montant', 'etat',
                            'message'))


CHAMPS_REGULARISATION = ('jour', 'reference', 'sens', 'montant', 'motif', 'tiers_type', 'tiers_id', 'statut',
                         'demandee_par_id', 'demandee_le', 'mouvement_id', 'ecrite_le')


def _regularisation(m: RegularisationModel) -> Regularisation:
    return Regularisation(id=m.id, compte_argent=m.compte_argent_id, nature=m.nature_code, offre=m.offre_code,
                          **{c: getattr(m, c) for c in CHAMPS_REGULARISATION})


class DjangoRegularisations(Regularisations):
    def creer(self, regularisation) -> Regularisation:
        r = regularisation
        return _regularisation(RegularisationModel.objects.create(
            id=r.id, compte_argent_id=r.compte_argent, nature_code=r.nature, offre_code=r.offre,
            **{c: getattr(r, c) for c in CHAMPS_REGULARISATION}))

    def lire(self, regularisation_id, verrou=False) -> Regularisation | None:
        qs = RegularisationModel.objects.filter(pk=regularisation_id)
        m = (qs.select_for_update() if verrou else qs).first()
        return _regularisation(m) if m else None

    def enregistrer(self, regularisation) -> None:
        RegularisationModel.objects.filter(pk=regularisation.id).update(
            statut=regularisation.statut, mouvement_id=regularisation.mouvement_id,
            ecrite_le=regularisation.ecrite_le)

    def du_jour(self, compte, jour) -> list[Regularisation]:
        return [_regularisation(m) for m in RegularisationModel.objects.filter(compte_argent_id=compte, jour=jour)
                .order_by('demandee_le')]
