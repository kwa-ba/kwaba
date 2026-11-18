"""Django adapters of the ledger: reference tables, accounting months, lines, parameters."""
from contextlib import AbstractContextManager
from decimal import Decimal

from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import Sum

from apps.finance.application.ports import (Cautions, GrandLivre, Parametres, Periodes, Rapports, TransactionManager,
                                            Validations)
from apps.finance.domain.entities import Caution, Ecriture, Ligne, Mouvement, Nature, Referentiels, Validation
from apps.finance.domain.exceptions import ClotureRefusee, MouvementRefuse
from apps.finance.infrastructure.persistence.models import (CLE_IDEMPOTENCE, CORRECTION_UNIQUE, AxeModel, CautionModel,
                                                            CompteArgentModel, MouvementModel, MoyenPaiementModel,
                                                            NatureModel, OffreModel, ParametreModel, PeriodeModel,
                                                            RapportModel, TiersTypeModel, ValidationModel)

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
