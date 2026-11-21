"""Internal transfers, money accounts and bank statements."""

from django.db import connection, models

from apps.finance.application.ports import ComptesArgent, Releves, Virements
from apps.finance.domain.entities import Virement
from apps.finance.infrastructure.persistence.models import (
    CompteArgentModel,
    MouvementModel,
    ReleveImportModel,
    VirementModel,
)

from .reconciliation import SIGNE

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
