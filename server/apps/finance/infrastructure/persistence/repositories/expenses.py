"""Expenses, suppliers, partners and their current accounts."""

from django.db import IntegrityError, connection, transaction
from django.db.models import Sum

from apps.finance.application.ports import Annuaire, ComptesCourants, Depenses
from apps.finance.domain.entities import (
    FAMILLE_DEPENSE,
    NATURES_COMPTE_COURANT,
    SINISTRE_IMPUTE,
    TIERS_ASSOCIE,
    Associe,
    Depense,
    Fournisseur,
)
from apps.finance.domain.exceptions import DepenseRefusee
from apps.finance.infrastructure.persistence.models import (
    AssocieModel,
    DepenseModel,
    FournisseurModel,
    NatureModel,
    SinistreModel,
)

from .reconciliation import SIGNE

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
