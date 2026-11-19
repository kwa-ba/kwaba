"""Django adapters of the ledger: reference tables, accounting months, lines, parameters."""
from contextlib import AbstractContextManager
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

from django.db import DatabaseError, IntegrityError, connection, models, transaction
from django.db.models import Sum

from apps.finance.application.ports import (Annuaire, Cautions, ComptesArgent, ComptesCourants, Depenses,
                                            FondsGarantie, GrandLivre, Releves, Virements,
                                            Parametres, ParametresPilotes, Periodes, Rapports, Rapprochements,
                                            Regularisations,
                                            TransactionManager, Validations)
from apps.finance.domain.entities import (COMPTE_FONDS_GARANTIE, FAMILLE_DEPENSE, NATURE_DOTATION_GARANTIE,
                                          NATURES_COMPTE_COURANT, PREFIXE_DOTATION, PREFIXE_REGULARISATION,
                                          RAPPROCHEMENT_EN_ERREUR, SINISTRE_IMPUTE, TIERS_ASSOCIE, Associe, Caution,
                                          Depense, Ecriture, Fournisseur, Ligne, Mouvement, Nature, OperationExterne,
                                          Referentiels, Regularisation, Sinistre, Validation, Virement)
from apps.finance.domain.exceptions import ClotureRefusee, DepenseRefusee, MouvementRefuse
from apps.finance.infrastructure.persistence.models import (CLE_IDEMPOTENCE, CORRECTION_UNIQUE, AssocieModel, AxeModel,
                                                            CautionModel, CompteArgentModel, DepenseModel,
                                                            FournisseurModel, MouvementModel, MoyenPaiementModel,
                                                            NatureModel, OffreModel, ParametreHistoModel,
                                                            ParametreModel, PeriodeModel,
                                                            RapportModel, RapprochementJourModel,
                                                            RapprochementLigneModel, RegularisationModel,
                                                            ReleveExterneModel, ReleveImportModel, SinistreModel,
                                                            TiersTypeModel, ValidationModel, VirementModel)

# SQLSTATE of RAISE EXCEPTION: a refusal of the database guards (migration 0003)
REFUS_BASE = 'P0001'


def diagnostic(erreur: DatabaseError):
    """Diagnostic of the PostgreSQL error (psycopg 2 and 3 both give .diag with sqlstate, constraint_name and
    message_primary)."""
    return getattr(erreur.__cause__, 'diag', None)


class DjangoTransactionManager(TransactionManager):
    def atomic(self) -> AbstractContextManager:
        return transaction.atomic()


def _actifs(modele, codes, champ: str = 'actif') -> dict[str, bool]:
    codes = {code for code in codes if code}
    return dict(modele.objects.filter(code__in=codes).values_list('code', champ)) if codes else {}


def _texte_id(valeur) -> str | None:
    return None if valeur is None else str(valeur)


def _mouvement(m: MouvementModel) -> Mouvement:
    return Mouvement(
        id=m.pk, mois=m.periode_id, origine=m.origine, annule_mouvement_id=m.annule_mouvement_id,
        ligne=Ligne(
            nature=m.nature_id, offre=m.offre_id, montant=m.montant, sens=m.sens, compte_argent=m.compte_argent_id,
            tiers_type=m.tiers_type_id, tiers_id=m.tiers_id, moyen_paiement=m.moyen_paiement_id,
            piece_reference=m.piece_reference, externe_reference=m.externe_reference, reservation_id=m.reservation_id,
            ligne_reservation_id=m.ligne_reservation_id, prestation_type=m.prestation_type,
            transfert_id=m.transfert_id, location_id=m.location_id, date_evenement=m.date_evenement, motif=m.motif,
            devise=m.devise, metadonnees=m.metadonnees,
        ),
    )


def _ligne_en_base(ecriture: Ecriture) -> MouvementModel:
    ligne = ecriture.ligne
    return MouvementModel(
        date_evenement=ecriture.date_evenement, periode_id=ecriture.mois, montant=ligne.montant, devise=ligne.devise,
        sens=ligne.sens, nature_id=ligne.nature, offre_id=ligne.offre, tiers_type_id=ligne.tiers_type,
        tiers_id=_texte_id(ligne.tiers_id), moyen_paiement_id=ligne.moyen_paiement, compte_argent_id=ligne.compte_argent,
        piece_reference=ligne.piece_reference, reservation_id=ligne.reservation_id,
        ligne_reservation_id=ligne.ligne_reservation_id, prestation_type=ligne.prestation_type,
        transfert_id=ligne.transfert_id, location_id=ligne.location_id, externe_reference=ligne.externe_reference,
        annule_mouvement_id=ecriture.annule_mouvement_id, motif=ligne.motif, cree_par_id=ecriture.par_id,
        origine=ecriture.origine, metadonnees=ligne.metadonnees,
    )


class DjangoGrandLivre(GrandLivre):
    def referentiels(self, lignes: list[Ligne]) -> Referentiels:
        natures = NatureModel.objects.filter(code__in={x.nature for x in lignes if x.nature})
        return Referentiels(
            natures={n.code: Nature(code=n.code, famille=n.famille_id, sens_attendu=n.sens_attendu, actif=n.actif)
                     for n in natures},
            offres=_actifs(OffreModel, {x.offre for x in lignes}, champ='active'),
            comptes_argent=_actifs(CompteArgentModel, {x.compte_argent for x in lignes}),
            tiers_types=_actifs(TiersTypeModel, {x.tiers_type for x in lignes}),
            moyens_paiement=_actifs(MoyenPaiementModel, {x.moyen_paiement for x in lignes}),
        )

    def etat_periode(self, mois) -> str:
        periode, _ = PeriodeModel.objects.get_or_create(mois=mois)
        return periode.etat

    def ecrire(self, ecriture: Ecriture) -> int | None:
        objet = _ligne_en_base(ecriture)
        try:
            # A savepoint: a refused line leaves the caller's transaction usable
            with transaction.atomic():
                objet.save(force_insert=True)
        except IntegrityError as erreur:
            contrainte = getattr(diagnostic(erreur), 'constraint_name', None)
            if contrainte == CLE_IDEMPOTENCE:
                return None
            if contrainte == CORRECTION_UNIQUE:
                # No row lock is taken to prevent it: the application role may not lock the ledger (no UPDATE
                # right), the unique index settles two simultaneous corrections
                raise MouvementRefuse(f'La ligne {ecriture.annule_mouvement_id} a déjà été corrigée.') from erreur
            raise
        except DatabaseError as erreur:
            diag = diagnostic(erreur)
            if getattr(diag, 'sqlstate', None) != REFUS_BASE:
                raise
            raise MouvementRefuse(getattr(diag, 'message_primary', None) or str(erreur)) from erreur
        return objet.pk

    def deja_ecrite(self, ecriture: Ecriture) -> Mouvement | None:
        ligne = ecriture.ligne
        trouve = MouvementModel.objects.filter(
            externe_reference=ligne.externe_reference, nature_id=ligne.nature, sens=ligne.sens,
            compte_argent_id=ligne.compte_argent, tiers_id=_texte_id(ligne.tiers_id),
            ligne_reservation_id=ligne.ligne_reservation_id, annule_mouvement__isnull=True,
        ).first()
        return _mouvement(trouve) if trouve else None

    def mouvement(self, mouvement_id: int) -> Mouvement | None:
        trouve = MouvementModel.objects.filter(pk=mouvement_id).first()
        return _mouvement(trouve) if trouve else None

    def est_corrige(self, mouvement_id: int) -> bool:
        return MouvementModel.objects.filter(annule_mouvement_id=mouvement_id).exists()

    def a_des_lignes(self, *, externe_reference=None, reservation_id=None, transfert_id=None,
                     location_id=None) -> bool:
        filtres = {nom: valeur for nom, valeur in (('externe_reference', externe_reference),
                                                    ('reservation_id', reservation_id), ('transfert_id', transfert_id),
                                                    ('location_id', location_id)) if valeur is not None}
        return bool(filtres) and MouvementModel.objects.filter(**filtres).exists()

    def lignes_en_vigueur(self, nature: str, *, reservation_id=None, transfert_id=None,
                          location_id=None) -> list[Mouvement]:
        objet = {nom: valeur for nom, valeur in (('reservation_id', reservation_id), ('transfert_id', transfert_id),
                                                  ('location_id', location_id)) if valeur is not None}
        if not objet:
            return []
        lignes = (MouvementModel.objects.filter(nature_id=nature, annule_mouvement__isnull=True, **objet)
                  .exclude(corrections__isnull=False).order_by('pk'))
        return [_mouvement(m) for m in lignes]

    def verrouiller(self, cle: str) -> None:
        # Advisory lock of the transaction: needs no right on any table, released at its end
        with connection.cursor() as curseur:
            curseur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', [cle])

    def solde_compte_courant(self, associe_id: str) -> int:
        with connection.cursor() as curseur:
            curseur.execute(f"""
                SELECT COALESCE(SUM({SIGNE}), 0) FROM finance_mouvement m
                WHERE m.tiers_type = %s AND m.tiers_id = %s AND m.nature_code = ANY(%s)""",
                            [TIERS_ASSOCIE, str(associe_id), list(NATURES_COMPTE_COURANT)])
            return int(curseur.fetchone()[0])


class DjangoParametres(Parametres):
    def lire(self, cle: str) -> tuple[Decimal, bool] | None:
        return ParametreModel.objects.filter(cle=cle).values_list('valeur', 'actif').first()


class DjangoPeriodes(Periodes):
    def serialiser(self) -> None:
        # Two closings at the same time: the second waits for the first, then sees it
        with connection.cursor() as curseur:
            curseur.execute("SELECT pg_advisory_xact_lock(hashtextextended('finance:cloture', 0))")

    def toutes(self) -> list[dict]:
        return list(PeriodeModel.objects.order_by('mois').values('mois', 'etat', 'verrouillee_le',
                                                                 'verrouillee_par_id'))

    def verrouiller(self, mois, par_id, quand) -> None:
        PeriodeModel.objects.get_or_create(mois=mois)
        changes = (PeriodeModel.objects.filter(mois=mois).exclude(etat=PeriodeModel.VERROUILLEE)
                   .update(etat=PeriodeModel.VERROUILLEE, verrouillee_le=quand, verrouillee_par_id=par_id))
        if not changes:
            raise ClotureRefusee(f'{mois:%m/%Y} est déjà clôturé.')


class DjangoRapports(Rapports):
    CHAMPS = ('code', 'titre', 'axe1', 'axe2', 'familles', 'offres', 'periodicite', 'destinataire')

    def liste(self) -> list[dict]:
        return [{**r, 'axe1': r.pop('axe1_id'), 'axe2': r.pop('axe2_id')} for r in
                RapportModel.objects.filter(actif=True).order_by('cree_le', 'code')
                .values('code', 'titre', 'axe1_id', 'axe2_id', 'familles', 'offres', 'periodicite', 'destinataire')]

    def axes(self) -> list[dict]:
        return list(AxeModel.objects.filter(actif=True).order_by('code').values('code', 'libelle'))

    def existe(self, code: str) -> bool:
        return RapportModel.objects.filter(code=code).exists()

    def creer(self, *, code, titre, axe1, axe2, familles, offres) -> None:
        RapportModel.objects.create(code=code, titre=titre, axe1_id=axe1, axe2_id=axe2, familles=familles,
                                    offres=offres)


def _validation(m: ValidationModel) -> Validation:
    return Validation(id=m.id, operation=m.operation, objet_type=m.objet_type, objet_id=m.objet_id, montant=m.montant,
                      motif=m.motif, donnees=m.donnees, statut=m.statut, demandee_par_id=m.demandee_par_id,
                      demandee_le=m.demandee_le, premiere_par_id=m.premiere_par_id, decidee_par_id=m.decidee_par_id,
                      decidee_le=m.decidee_le, resultat=m.resultat)


class DjangoValidations(Validations):
    CHAMPS = ('statut', 'premiere_par_id', 'decidee_par_id', 'decidee_le', 'resultat')

    def creer(self, validation: Validation) -> Validation:
        m = ValidationModel.objects.create(
            id=validation.id, operation=validation.operation, objet_type=validation.objet_type,
            objet_id=validation.objet_id, montant=validation.montant, motif=validation.motif,
            donnees=validation.donnees, statut=validation.statut, demandee_par_id=validation.demandee_par_id,
            demandee_le=validation.demandee_le)
        return _validation(m)

    def verrouiller(self, validation_id) -> Validation | None:
        m = ValidationModel.objects.select_for_update().filter(pk=validation_id).first()
        return _validation(m) if m else None

    def enregistrer(self, validation: Validation) -> None:
        ValidationModel.objects.filter(pk=validation.id).update(
            **{champ: getattr(validation, champ) for champ in self.CHAMPS})

    def en_attente(self, operation, objet_type, objet_id) -> Validation | None:
        m = ValidationModel.objects.filter(operation=operation, objet_type=objet_type, objet_id=objet_id,
                                           statut='en_attente').first()
        return _validation(m) if m else None

    def derniere(self, operation, objet_type, objet_id) -> Validation | None:
        m = (ValidationModel.objects.filter(operation=operation, objet_type=objet_type, objet_id=objet_id)
             .order_by('-demandee_le').first())
        return _validation(m) if m else None

    def liste(self, statut, limite) -> list[Validation]:
        qs = ValidationModel.objects.order_by('-demandee_le')
        if statut:
            qs = qs.filter(statut=statut)
        return [_validation(m) for m in qs[:limite]]


CHAMPS_CAUTION = ('reference', 'offre', 'montant', 'recue_le', 'date_limite', 'voyageur_id', 'statut', 'montant_retenu',
                  'montant_rendu', 'motif_retenue', 'cgv_article', 'decision_par_id', 'decision_le', 'soldee_le',
                  'mode_restitution', 'document_numero')


def _caution(m: CautionModel) -> Caution:
    return Caution(objet_type=m.objet_type, objet_id=m.objet_id, offre=m.offre_code,
                   **{c: getattr(m, c) for c in CHAMPS_CAUTION if c != 'offre'})


def _champs_caution(c: Caution) -> dict:
    champs = {champ: getattr(c, champ) for champ in CHAMPS_CAUTION if champ != 'offre'}
    return {**champs, 'offre_code': c.offre}


class DjangoCautions(Cautions):
    def lire(self, objet_type, objet_id, verrou=False) -> Caution | None:
        qs = CautionModel.objects.filter(objet_type=objet_type, objet_id=str(objet_id))
        m = (qs.select_for_update() if verrou else qs).first()
        return _caution(m) if m else None

    def creer(self, caution: Caution) -> Caution:
        return _caution(CautionModel.objects.create(objet_type=caution.objet_type, objet_id=caution.objet_id,
                                                    **_champs_caution(caution)))

    def enregistrer(self, caution: Caution) -> None:
        CautionModel.objects.filter(objet_type=caution.objet_type, objet_id=caution.objet_id).update(
            **_champs_caution(caution))

    def liste(self, statut, en_retard_au, limite) -> list[Caution]:
        qs = CautionModel.objects.order_by('date_limite') if statut == 'detenue' or en_retard_au else (
            CautionModel.objects.order_by('-recue_le'))
        if statut:
            qs = qs.filter(statut=statut)
        if en_retard_au:
            qs = qs.filter(date_limite__lt=en_retard_au)
        return [_caution(m) for m in qs[:limite]]

    def total_detenu(self) -> int:
        return CautionModel.objects.filter(statut='detenue').aggregate(t=Sum('montant'))['t'] or 0


# --- Reconciliation with the payment provider (GL-12) ---------------------------------------------------------------

# The operation a ledger line belongs to: its external reference, or the operation a regularisation explains
# (« regul:<reference>:<id> »)
CLE_OPERATION = (f"COALESCE(substring(m.externe_reference from '^{PREFIXE_REGULARISATION}(.*):[^:]*$'), "
                 "m.externe_reference, '')")
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
                WHERE m.compte_argent_code = %s AND m.annule_mouvement_id IS NULL AND {CLE_OPERATION} = ANY(%s)
                GROUP BY 1""", [compte, list(references)])
            return {cle: (int(total), bool(regul)) for cle, total, regul in curseur.fetchall()}

    def internes(self, compte, jour) -> int:
        debut, fin = _bornes(jour)
        with connection.cursor() as curseur:
            curseur.execute(f"""
                SELECT COALESCE(SUM({SIGNE}), 0)
                FROM finance_mouvement m
                WHERE m.compte_argent_code = %s AND m.date_evenement >= %s AND m.date_evenement < %s
                  AND NOT (m.annule_mouvement_id IS NULL
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


# --- Expenses (GL-15) -------------------------------------------------------------------------------------------------

def _depense(m: DepenseModel) -> Depense:
    return Depense(id=m.id, numero=m.numero, date_depense=m.date_depense, nature=m.nature_code, offre=m.offre_code,
                   montant=m.montant, libelle=m.libelle, fournisseur_id=m.fournisseur_id, mode=m.mode,
                   associe_id=m.associe_id, reference_facture=m.reference_facture, statut=m.statut,
                   demandee_par_id=m.demandee_par_id, demandee_le=m.demandee_le, mouvement_ids=tuple(m.mouvement_ids),
                   ecrite_le=m.ecrite_le, annulee_le=m.annulee_le, motif_annulation=m.motif_annulation)


class DjangoDepenses(Depenses):
    def prochain_numero(self, annee: int) -> str:
        with connection.cursor() as curseur:
            curseur.execute("SELECT pg_advisory_xact_lock(hashtextextended('finance:depense:numero', 0))")
        prefixe = f'DEP-{annee}-'
        dernier = (DepenseModel.objects.filter(numero__startswith=prefixe).order_by('-numero')
                   .values_list('numero', flat=True).first())
        rang = int(dernier.rsplit('-', 1)[1]) + 1 if dernier else 1
        return f'{prefixe}{rang:05d}'

    def nature_de_depense(self, code: str) -> bool:
        return NatureModel.objects.filter(code=code, famille_id=FAMILLE_DEPENSE, actif=True).exists()

    def creer(self, depense: Depense) -> Depense:
        d = depense
        return _depense(DepenseModel.objects.create(
            id=d.id, numero=d.numero, date_depense=d.date_depense, nature_code=d.nature, offre_code=d.offre,
            montant=d.montant, libelle=d.libelle, fournisseur_id=d.fournisseur_id, mode=d.mode,
            associe_id=d.associe_id, reference_facture=d.reference_facture, statut=d.statut,
            demandee_par_id=d.demandee_par_id, demandee_le=d.demandee_le))

    def lire(self, depense_id, verrou=False) -> Depense | None:
        qs = DepenseModel.objects.filter(pk=depense_id)
        m = (qs.select_for_update() if verrou else qs).first()
        return _depense(m) if m else None

    def enregistrer(self, depense: Depense) -> None:
        DepenseModel.objects.filter(pk=depense.id).update(
            statut=depense.statut, mouvement_ids=list(depense.mouvement_ids), ecrite_le=depense.ecrite_le,
            annulee_le=depense.annulee_le, motif_annulation=depense.motif_annulation)

    def liste(self, *, debut, fin, nature, fournisseur_id, associe_id, statut, decalage, limite):
        qs = DepenseModel.objects.all()
        if debut:
            qs = qs.filter(date_depense__gte=debut)
        if fin:
            qs = qs.filter(date_depense__lte=fin)
        if nature:
            qs = qs.filter(nature_code=nature)
        if fournisseur_id:
            qs = qs.filter(fournisseur_id=fournisseur_id)
        if associe_id:
            qs = qs.filter(associe_id=associe_id)
        if statut:
            qs = qs.filter(statut=statut)
        total = qs.filter(statut='ecrite').aggregate(t=Sum('montant'))['t'] or 0
        lignes = [_depense(m) for m in qs.order_by('-date_depense', '-numero')[decalage:decalage + limite]]
        return lignes, qs.count(), total

    def couverte_par_le_fonds(self, depense_id) -> bool:
        return SinistreModel.objects.filter(depense_id=depense_id, statut=SINISTRE_IMPUTE).exists()


def _unique(enregistrer, message: str):
    try:
        with transaction.atomic():
            return enregistrer()
    except IntegrityError as erreur:
        raise DepenseRefusee(message) from erreur


def _fournisseur(m: FournisseurModel) -> Fournisseur:
    return Fournisseur(id=m.id, nom=m.nom, nif=m.nif, contact=m.contact, actif=m.actif)


def _associe(m: AssocieModel) -> Associe:
    return Associe(id=m.id, nom=m.nom, email=m.email, compte_id=m.compte_id, actif=m.actif,
                   capital_souscrit=m.capital_souscrit)


class DjangoAnnuaire(Annuaire):
    def serialiser(self) -> None:
        with connection.cursor() as curseur:
            curseur.execute("SELECT pg_advisory_xact_lock(hashtextextended('finance:associes', 0))")

    def fournisseurs(self, actifs_seulement) -> list[Fournisseur]:
        qs = FournisseurModel.objects.filter(actif=True) if actifs_seulement else FournisseurModel.objects.all()
        return [_fournisseur(m) for m in qs.order_by('nom')]

    def fournisseur(self, fournisseur_id) -> Fournisseur | None:
        m = FournisseurModel.objects.filter(pk=fournisseur_id).first()
        return _fournisseur(m) if m else None

    def enregistrer_fournisseur(self, f: Fournisseur, nouveau: bool) -> Fournisseur:
        champs = {'nom': f.nom, 'nif': f.nif, 'contact': f.contact, 'actif': f.actif}
        _unique(lambda: FournisseurModel.objects.create(id=f.id, **champs) if nouveau
                else FournisseurModel.objects.filter(pk=f.id).update(**champs),
                f'Un fournisseur « {f.nom} » existe déjà.')
        return f

    def associes(self, actifs_seulement) -> list[Associe]:
        qs = AssocieModel.objects.filter(actif=True) if actifs_seulement else AssocieModel.objects.all()
        return [_associe(m) for m in qs.order_by('nom')]

    def associe(self, associe_id) -> Associe | None:
        m = AssocieModel.objects.filter(pk=associe_id).first()
        return _associe(m) if m else None

    def enregistrer_associe(self, a: Associe, nouveau: bool) -> Associe:
        champs = {'nom': a.nom, 'email': a.email, 'compte_id': a.compte_id, 'actif': a.actif,
                  'capital_souscrit': a.capital_souscrit}
        _unique(lambda: AssocieModel.objects.create(id=a.id, **champs) if nouveau
                else AssocieModel.objects.filter(pk=a.id).update(**champs),
                f'Un associé « {a.nom} » existe déjà.')
        return a


# --- Associates' current accounts (GL-16) and guarantee fund (GL-17) -------------------------------------------------

def _rangees(sql: str, params: list) -> list[dict]:
    with connection.cursor() as curseur:
        curseur.execute(sql, params)
        colonnes = [c[0] for c in curseur.description]
        return [dict(zip(colonnes, r)) for r in curseur.fetchall()]


class DjangoComptesCourants(ComptesCourants):
    def soldes(self) -> dict[str, dict]:
        lignes = _rangees(f"""
            SELECT m.tiers_id,
                   COALESCE(SUM(CASE WHEN m.nature_code <> 'F04' THEN {SIGNE} ELSE 0 END), 0)::bigint AS avances,
                   COALESCE(SUM(CASE WHEN m.nature_code = 'F04' THEN -{SIGNE} ELSE 0 END), 0)::bigint AS remboursements,
                   COALESCE(SUM({SIGNE}), 0)::bigint AS solde
            FROM finance_mouvement m
            WHERE m.tiers_type = %s AND m.nature_code = ANY(%s)
            GROUP BY m.tiers_id""", [TIERS_ASSOCIE, list(NATURES_COMPTE_COURANT)])
        return {r.pop('tiers_id'): r for r in lignes}

    def releve(self, associe_id: str) -> list[dict]:
        return _rangees(f"""
            SELECT m.id AS mouvement_id, m.date_evenement AS date, m.piece_reference AS piece, m.nature_code AS nature,
                   n.libelle AS nature_libelle, COALESCE(m.motif, '') AS libelle, ({SIGNE})::bigint AS montant_signe,
                   m.annule_mouvement_id
            FROM finance_mouvement m JOIN finance_nature n ON n.code = m.nature_code
            WHERE m.tiers_type = %s AND m.tiers_id = %s AND m.nature_code = ANY(%s)
            ORDER BY m.date_evenement, m.id""", [TIERS_ASSOCIE, str(associe_id), list(NATURES_COMPTE_COURANT)])


CHAMPS_SINISTRE = ('montant', 'decision_reference', 'motif', 'statut', 'impute_par_id', 'impute_le', 'mouvement_id',
                   'annule_le', 'motif_annulation')


def _sinistre(m: SinistreModel) -> Sinistre:
    return Sinistre(id=m.id, depense_id=m.depense_id, **{c: getattr(m, c) for c in CHAMPS_SINISTRE})


class DjangoFondsGarantie(FondsGarantie):
    def serialiser(self) -> None:
        with connection.cursor() as curseur:
            curseur.execute("SELECT pg_advisory_xact_lock(hashtextextended('finance:fonds_garantie', 0))")

    def dotations(self) -> list[dict]:
        return _rangees("""
            SELECT d.mois_comptable AS mois, d.assiette, d.taux, d.due, d.ecrite, COALESCE(p.etat, 'ouverte') AS etat
            FROM finance_dotation_garantie d LEFT JOIN finance_periode p ON p.mois = d.mois_comptable
            ORDER BY d.mois_comptable DESC""", [])

    def dotation(self, mois) -> dict | None:
        lignes = _rangees("""
            SELECT d.mois_comptable AS mois, d.assiette, d.taux, d.due, d.ecrite, COALESCE(p.etat, 'ouverte') AS etat
            FROM finance_dotation_garantie d LEFT JOIN finance_periode p ON p.mois = d.mois_comptable
            WHERE d.mois_comptable = %s""", [mois])
        return lignes[0] if lignes else None

    def nb_lignes_dotation(self, mois) -> int:
        return MouvementModel.objects.filter(
            compte_argent_id=COMPTE_FONDS_GARANTIE, nature_id=NATURE_DOTATION_GARANTIE,
            externe_reference__startswith=f'{PREFIXE_DOTATION}{mois:%Y-%m}').count()

    def solde(self) -> int:
        with connection.cursor() as curseur:
            curseur.execute(f'SELECT COALESCE(-SUM({SIGNE}), 0) FROM finance_mouvement m '
                            'WHERE m.compte_argent_code = %s', [COMPTE_FONDS_GARANTIE])
            return int(curseur.fetchone()[0])

    def creer(self, sinistre: Sinistre) -> Sinistre:
        return _sinistre(SinistreModel.objects.create(id=sinistre.id, depense_id=sinistre.depense_id,
                                                      **{c: getattr(sinistre, c) for c in CHAMPS_SINISTRE}))

    def lire(self, sinistre_id, verrou=False) -> Sinistre | None:
        qs = SinistreModel.objects.filter(pk=sinistre_id)
        m = (qs.select_for_update() if verrou else qs).first()
        return _sinistre(m) if m else None

    def enregistrer(self, sinistre: Sinistre) -> None:
        SinistreModel.objects.filter(pk=sinistre.id).update(
            statut=sinistre.statut, mouvement_id=sinistre.mouvement_id, annule_le=sinistre.annule_le,
            motif_annulation=sinistre.motif_annulation)

    def sinistres(self, limite: int) -> list[Sinistre]:
        return [_sinistre(m) for m in SinistreModel.objects.order_by('-impute_le')[:limite]]


# --- Steered parameters (GL-20) --------------------------------------------------------------------------------------

CHAMPS_PARAMETRE = ('cle', 'valeur', 'unite', 'categorie', 'offre_id', 'libelle', 'source', 'actif', 'maj_le',
                    'maj_par_id')


def _parametre(p: dict) -> dict:
    return {**{k: v for k, v in p.items() if k != 'offre_id'}, 'offre': p['offre_id']}


class DjangoParametresPilotes(ParametresPilotes):
    def tous(self) -> list[dict]:
        return [_parametre(p) for p in ParametreModel.objects.order_by('categorie', 'cle').values(*CHAMPS_PARAMETRE)]

    def lire_pour_modifier(self, cle) -> dict | None:
        p = ParametreModel.objects.select_for_update().filter(cle=cle).values(*CHAMPS_PARAMETRE).first()
        return _parametre(p) if p else None

    def historique(self, cle=None, limite=200) -> list[dict]:
        qs = ParametreHistoModel.objects.order_by('-date_effet', '-id')
        if cle:
            qs = qs.filter(cle=cle)
        return list(qs.values('cle', 'valeur_avant', 'valeur_apres', 'date_effet', 'cree_le', 'cree_par_id',
                              'motif')[:limite])

    def modifier(self, cle, valeur, *, par_id, motif, quand) -> None:
        avant = ParametreModel.objects.filter(cle=cle).values_list('valeur', flat=True).first()
        ParametreModel.objects.filter(cle=cle).update(valeur=valeur, maj_le=quand, maj_par_id=par_id)
        ParametreHistoModel.objects.create(cle=cle, valeur_avant=avant, valeur_apres=valeur, date_effet=quand,
                                           cree_par_id=par_id, motif=motif)


# --- Internal transfers, money accounts, bank statements (GL-22) -------------------------------------------------

def _virement(m: VirementModel) -> Virement:
    return Virement(id=m.id, numero=m.numero, date_virement=m.date_virement, source=m.source_id,
                    destination=m.destination_id, montant=m.montant, motif=m.motif,
                    reference_externe=m.reference_externe, statut=m.statut, demandee_par_id=m.demandee_par_id,
                    demandee_le=m.demandee_le, mouvement_ids=tuple(m.mouvement_ids), ecrit_le=m.ecrit_le,
                    annule_le=m.annule_le, motif_annulation=m.motif_annulation)


class DjangoVirements(Virements):
    def prochain_numero(self, annee: int) -> str:
        with connection.cursor() as curseur:
            curseur.execute("SELECT pg_advisory_xact_lock(hashtextextended('finance:virement:numero', 0))")
        prefixe = f'VIR-{annee}-'
        dernier = (VirementModel.objects.filter(numero__startswith=prefixe).order_by('-numero')
                   .values_list('numero', flat=True).first())
        return f'{prefixe}{(int(dernier.rsplit("-", 1)[1]) + 1 if dernier else 1):05d}'

    def creer(self, v: Virement) -> Virement:
        return _virement(VirementModel.objects.create(
            id=v.id, numero=v.numero, date_virement=v.date_virement, source_id=v.source, destination_id=v.destination,
            montant=v.montant, motif=v.motif, reference_externe=v.reference_externe, statut=v.statut,
            demandee_par_id=v.demandee_par_id, demandee_le=v.demandee_le))

    def lire(self, virement_id, verrou=False) -> Virement | None:
        qs = VirementModel.objects.filter(pk=virement_id)
        m = (qs.select_for_update() if verrou else qs).first()
        return _virement(m) if m else None

    def enregistrer(self, v: Virement) -> None:
        VirementModel.objects.filter(pk=v.id).update(statut=v.statut, mouvement_ids=list(v.mouvement_ids),
                                                     ecrit_le=v.ecrit_le, annule_le=v.annule_le,
                                                     motif_annulation=v.motif_annulation)

    def liste(self, *, compte, statut, decalage, limite):
        qs = VirementModel.objects.all()
        if compte:
            qs = qs.filter(models.Q(source_id=compte) | models.Q(destination_id=compte))
        if statut:
            qs = qs.filter(statut=statut)
        return [_virement(m) for m in qs.order_by('-date_virement', '-numero')[decalage:decalage + limite]], qs.count()

    def ecrits_du_compte(self, compte, debut, fin) -> list[Virement]:
        return [_virement(m) for m in VirementModel.objects.filter(
            models.Q(source_id=compte) | models.Q(destination_id=compte), statut='ecrit',
            date_virement__gte=debut, date_virement__lte=fin).order_by('date_virement', 'numero')]


class DjangoComptesArgent(ComptesArgent):
    def liste(self) -> list[dict]:
        soldes = dict(MouvementModel.objects.values('compte_argent_id').annotate(
            n=models.Count('id')).values_list('compte_argent_id', 'n'))
        with connection.cursor() as curseur:
            curseur.execute(f'SELECT m.compte_argent_code, COALESCE(SUM({SIGNE}), 0) FROM finance_mouvement m '
                            'GROUP BY 1')
            montants = dict(curseur.fetchall())
        return [{**c, 'solde': int(montants.get(c['code'], 0)), 'nb_lignes': soldes.get(c['code'], 0)}
                for c in CompteArgentModel.objects.order_by('code').values(
                    'code', 'libelle', 'type', 'compte_syscohada', 'actif', 'actif_depuis')]

    def lire(self, code) -> dict | None:
        return next((c for c in self.liste() if c['code'] == code), None)

    def activer(self, code, actif, depuis) -> None:
        champs = {'actif': actif}
        if actif:
            champs['actif_depuis'] = depuis
        CompteArgentModel.objects.filter(code=code).update(**champs)


class DjangoReleves(Releves):
    def enregistrer(self, *, compte, debut, fin, nb_lignes, nom_fichier, contenu, par_id, quand) -> str:
        import uuid as _uuid

        m = ReleveImportModel.objects.create(id=_uuid.uuid4(), compte_argent_id=compte, debut=debut, fin=fin,
                                             nb_lignes=nb_lignes, nom_fichier=nom_fichier, contenu=contenu,
                                             importe_par_id=par_id, importe_le=quand)
        return str(m.id)

    def liste(self, compte, limite) -> list[dict]:
        qs = ReleveImportModel.objects.order_by('-importe_le')
        if compte:
            qs = qs.filter(compte_argent_id=compte)
        return list(qs.values('id', 'compte_argent_id', 'debut', 'fin', 'nb_lignes', 'nom_fichier', 'importe_par_id',
                              'importe_le')[:limite])
