"""Reconciliation of the FedaPay account, day by day (GL-12, FIN-02): this module is the only one that talks to FedaPay,
so it reads the provider's side and gives the finance module the operations of a day on three sides.

For a finished day:
- every payment, refund and payout of Kwa-Ba near that day is read again at FedaPay (amount, real fees, status, date);
  the day of an operation is FedaPay's (approval or sending), Kwa-Ba's when FedaPay does not know it;
- FedaPay transactions unknown to Kwa-Ba are searched for, as far as the API lets us (best effort, see `_inconnues`);
- the real fees of the operations whose money is in the ledger are written there (D01, account 6317, one line per
  transaction, at the amount of the statement): they are Kwa-Ba's charge (decisions of 2026-11-13 and 2026-11-19);
- the finance module compares the three sides with the ledger lines of the FEDAPAY account.

Money of a product not in the ledger yet (Give, transfers, rentals, or paid before the ledger existed) is shown apart,
outside the gap of the day (decision of 2026-11-19).

The worker imports the last three finished days once a day (`importer_si_du`), and an admin can import any day again
from Finance → Rapprochement.
"""
import logging
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.finance import api as finance

from . import demo, fedapay, grand_livre
from .models import PaiementModel, RemboursementModel, VersementModel

logger = logging.getLogger('apps.paiements.rapprochement')

COMPTE = 'FEDAPAY'
# Window around the day in which Kwa-Ba's records are read: a payment created two days earlier may be approved on
# the day, a refund marked sent the next morning may have left on the day
FENETRE_AVANT, FENETRE_APRES = timedelta(days=3), timedelta(days=2)
# Days imported again by the worker: statuses settle within a few days
JOURS_AUTOMATIQUES = 3
# Hour (Lomé, UTC+0) from which the worker imports the finished days
HEURE_IMPORT = 3
# Pages of the FedaPay transaction search read at most per day
PAGES_RECHERCHE = 5
# Longest period imported in one request from the back-office
JOURS_MAX = 31


class ImportImpossible(Exception):
    """FedaPay could not be read: the day stays to import again."""


def _bornes(jour: date) -> tuple[datetime, datetime]:
    debut = datetime.combine(jour, time.min, tzinfo=dt_timezone.utc)
    return debut, debut + timedelta(days=1)


def _date(donnees: dict, *cles: str) -> datetime | None:
    for cle in cles:
        valeur = donnees.get(cle)
        if valeur:
            moment = parse_datetime(str(valeur))
            if moment is not None:
                return moment if timezone.is_aware(moment) else moment.replace(tzinfo=dt_timezone.utc)
    return None


def _jour(moment: datetime | None, defaut: datetime) -> date:
    return (moment or defaut).astimezone(dt_timezone.utc).date()


def _entier(valeur) -> int | None:
    try:
        return int(round(float(valeur)))
    except (TypeError, ValueError):
        return None


def _frais(donnees: dict) -> int:
    """Real fees FedaPay kept on the operation: `fees` (with the commission if FedaPay states one apart), or what
    the amount transferred tells."""
    frais = _entier(donnees.get('fees'))
    if frais is None:
        montant, transfere = _entier(donnees.get('amount')), _entier(donnees.get('amount_transferred'))
        frais = montant - transfere if montant is not None and transfere is not None else 0
    commission = _entier(donnees.get('commission')) or 0
    return max(0, frais + commission)


def _lire(lecture, identifiant: str) -> tuple[dict | None, str]:
    """(FedaPay's object, problem). A FedaPay out of reach stops the import: nothing is half read."""
    try:
        return lecture(identifiant), ''
    except fedapay.FedaPayErreur as erreur:
        if 'injoignable' in str(erreur).lower():
            raise ImportImpossible(str(erreur)) from erreur
        return None, f'Lecture FedaPay impossible : {str(erreur)[:150]}'


# --- The three sides of each operation ----------------------------------------------------------------------------

def _encaissements(jour: date, client) -> list[finance.OperationExterne]:
    debut, fin = _bornes(jour)
    operations = []
    paiements = PaiementModel.objects.filter(prestataire='fedapay', statut='reussi', transaction_id__isnull=False,
                                             cree_le__gte=debut - FENETRE_AVANT, cree_le__lt=fin + FENETRE_APRES)
    for paiement in paiements:
        donnees, probleme = _lire(client.lire_transaction, paiement.transaction_id)
        moment = _date(donnees or {}, 'approved_at', 'transferred_at', 'updated_at')
        if _jour(moment, paiement.cree_le) != jour:
            continue
        statut = str((donnees or {}).get('status', '')).lower()
        reussi = fedapay.STATUTS_TRANSACTION.get(statut) == 'reussi'
        dans_livre = grand_livre.dans_le_grand_livre(paiement.type_objet, paiement.objet_id)
        operations.append(finance.OperationExterne(
            reference=paiement.transaction_id, type='encaissement', sens=finance.ENTREE, jour=jour,
            date_operation=moment or paiement.cree_le, kwaba_reference=paiement.reference,
            kwaba_montant=paiement.montant, kwaba_statut=paiement.statut,
            externe_montant=(_entier(donnees.get('amount')) if reussi else 0) if donnees else None,
            externe_frais=_frais(donnees) if donnees and reussi else (0 if donnees else None),
            externe_statut=statut, moyen_paiement=grand_livre.moyen(paiement), hors_grand_livre=not dans_livre,
            offre=grand_livre.offre_de(paiement.type_objet, paiement.objet_id), message=probleme))
    return operations


def _payout(ligne, *, type_operation: str, paiement, dans_livre: bool, offre: str | None, jour: date,
            client) -> finance.OperationExterne | None:
    donnees, probleme = _lire(client.lire_versement, ligne.payout_id)
    moment = _date(donnees or {}, 'sent_at', 'updated_at', 'created_at')
    if _jour(moment, ligne.envoye_le or ligne.mis_a_jour_le) != jour:
        return None
    statut = str((donnees or {}).get('status', '')).lower()
    envoye = fedapay.STATUTS_PAYOUT.get(statut) == 'envoye'
    return finance.OperationExterne(
        reference=ligne.payout_id, type=type_operation, sens=finance.SORTIE, jour=jour,
        date_operation=moment or ligne.envoye_le, kwaba_reference=paiement.reference if paiement else '',
        kwaba_montant=ligne.montant, kwaba_statut=ligne.statut,
        externe_montant=(_entier(donnees.get('amount')) if envoye else 0) if donnees else None,
        externe_frais=_frais(donnees) if donnees and envoye else (0 if donnees else None),
        externe_statut=statut, moyen_paiement=grand_livre.moyen(paiement) if paiement else None,
        hors_grand_livre=not dans_livre, offre=offre, message=probleme)


def _sorties(jour: date, client) -> list[finance.OperationExterne]:
    debut, fin = _bornes(jour)
    fenetre = {'envoye_le__gte': debut - FENETRE_AVANT, 'envoye_le__lt': fin + FENETRE_APRES}
    operations = []
    remboursements = (RemboursementModel.objects.filter(statut='envoye', paiement__prestataire='fedapay', **fenetre)
                      .exclude(payout_id='').select_related('paiement'))
    for r in remboursements:
        p = r.paiement
        op = _payout(r, type_operation='remboursement', paiement=p, jour=jour, client=client,
                     dans_livre=grand_livre.dans_le_grand_livre(p.type_objet, p.objet_id),
                     offre=grand_livre.offre_de(p.type_objet, p.objet_id))
        if op:
            operations.append(op)
    for v in VersementModel.objects.filter(statut='envoye', **fenetre).exclude(payout_id=''):
        paiement = (PaiementModel.objects.filter(reservation_id=v.reservation_id, statut='reussi')
                    .order_by('cree_le').first())
        dans_livre = grand_livre.dans_le_grand_livre('reservation', v.reservation_id)
        op = _payout(v, type_operation='versement', paiement=paiement, jour=jour, client=client,
                     dans_livre=dans_livre, offre=grand_livre.offre_de('reservation', v.reservation_id))
        if op:
            operations.append(op)
    return operations


def _inconnues(jour: date, client, connues: set[str]) -> tuple[list[finance.OperationExterne], str]:
    """FedaPay transactions approved that day that Kwa-Ba does not know (a payment outside the site, a test left in
    production). FedaPay documents its search poorly: we read a few pages and keep those of the day; if the search
    fails, the day says so but is not blocked by it."""
    chercher = getattr(client, 'chercher_transactions', None)
    if chercher is None:
        return [], ''
    trouvees, vues = [], set()
    try:
        for page in range(1, PAGES_RECHERCHE + 1):
            lot = chercher(page=page)
            nouvelles = [t for t in lot if str(t.get('id')) not in vues]
            if not nouvelles:
                break
            for t in nouvelles:
                vues.add(str(t.get('id')))
                statut = str(t.get('status', '')).lower()
                moment = _date(t, 'approved_at', 'transferred_at')
                if (fedapay.STATUTS_TRANSACTION.get(statut) != 'reussi' or moment is None
                        or _jour(moment, moment) != jour or str(t.get('id')) in connues):
                    continue
                trouvees.append(t)
    except fedapay.FedaPayErreur as erreur:
        return [], f'Recherche des transactions inconnues indisponible : {str(erreur)[:120]}'
    connues_kwaba = set(PaiementModel.objects.filter(transaction_id__in=[str(t['id']) for t in trouvees])
                        .values_list('transaction_id', flat=True))
    return [finance.OperationExterne(
        reference=str(t['id']), type='inconnu', sens=finance.ENTREE, jour=jour,
        date_operation=_date(t, 'approved_at', 'transferred_at'), externe_montant=_entier(t.get('amount')),
        externe_frais=_frais(t), externe_statut=str(t.get('status', '')).lower(),
        message='Payée chez FedaPay, inconnue de Kwa-Ba.' if str(t['id']) not in connues_kwaba else
        'Connue de Kwa-Ba mais pas comme un paiement réussi de ce jour.')
        for t in trouvees], ''


def operations_du_jour(jour: date, client=None) -> tuple[list[finance.OperationExterne], str]:
    """(operations of the day on two sides, remark). Raises ImportImpossible if FedaPay is out of reach."""
    # The preprod demo operations are rebuilt from the records: FedaPay's sandbox does not know them
    client = demo.Lecteur(client or fedapay.client())
    operations = _encaissements(jour, client) + _sorties(jour, client)
    inconnues, remarque = _inconnues(jour, client, {op.reference for op in operations})
    return operations + inconnues, remarque


# --- Real fees in the ledger (D01) --------------------------------------------------------------------------------

def _ecrire_frais(op: finance.OperationExterne) -> None:
    """The real fees of an operation whose money is in the ledger: D01, Kwa-Ba's charge, out of the FEDAPAY account,
    under the reference of the operation (written once)."""
    if op.hors_grand_livre or not op.externe_frais or not op.offre or op.type == 'inconnu':
        return
    finance.enregistrer([finance.Ligne(
        nature='D01', offre=op.offre, montant=op.externe_frais, sens=finance.SORTIE, compte_argent=COMPTE,
        moyen_paiement=op.moyen_paiement, piece_reference=op.kwaba_reference or None, externe_reference=op.reference,
        date_evenement=op.date_operation, motif=f'Frais FedaPay réels ({op.type})')], origine='frais_paiement')


# --- Import ---------------------------------------------------------------------------------------------------------

def importer(jour: date, *, par_id=None, client=None) -> dict:
    """Imports a finished day and reconciles it: the result of the day ({etat, solde_livre, solde_externe, …}).
    FedaPay out of reach: the day is « en erreur » and ImportImpossible is raised. RapprochementRefuse for a day
    not finished or a locked month."""
    if finance.mois_verrouille(jour):
        raise finance.RapprochementRefuse(f'{jour:%m/%Y} est clôturé : sa journée ne se réimporte plus.')
    try:
        operations, remarque = operations_du_jour(jour, client)
    except ImportImpossible as erreur:
        finance.echec_rapprochement(COMPTE, jour, f'FedaPay injoignable : {erreur}')
        raise
    with transaction.atomic():
        for op in operations:
            _ecrire_frais(op)
        resultat = finance.importer_rapprochement(COMPTE, jour, operations, par_id=par_id)
    if remarque:
        logger.warning('Rapprochement du %s : %s', jour, remarque)
    return {**resultat, 'remarque': remarque}


def importer_periode(debut: date, fin: date, *, par_id=None, client=None) -> list[dict]:
    """Imports each finished day of [debut, fin] (31 days at most): one result per day, an error stays on its day."""
    hier = timezone.now().astimezone(dt_timezone.utc).date() - timedelta(days=1)
    fin = min(fin, hier)
    if debut > fin:
        raise finance.RapprochementRefuse("Aucune journée terminée dans cette période.")
    if (fin - debut).days >= JOURS_MAX:
        raise finance.RapprochementRefuse(f'{JOURS_MAX} jours au plus par import.')
    client = client or fedapay.client()
    resultats, jour = [], debut
    while jour <= fin:
        try:
            resultats.append({'jour': jour, **importer(jour, par_id=par_id, client=client)})
        except (ImportImpossible, finance.RapprochementRefuse, finance.MouvementRefuse) as erreur:
            resultats.append({'jour': jour, 'etat': 'en_erreur', 'message': str(erreur)})
        jour += timedelta(days=1)
    return resultats


def importer_si_du() -> int:
    """Worker: once a day after 03:00, imports the last finished days; FedaPay out of reach is tried again an hour
    later. Returns the number of days imported."""
    maintenant = timezone.now().astimezone(dt_timezone.utc)
    if maintenant.hour < HEURE_IMPORT or not settings.FEDAPAY['SECRET_KEY']:
        return 0
    hier = maintenant.date() - timedelta(days=1)
    dernier = finance.rapprochement_du_jour(COMPTE, hier)
    if dernier and dernier['calcule_le'] and dernier['calcule_le'].astimezone(dt_timezone.utc).date() == maintenant.date():
        technique = dernier['etat'] == 'en_erreur' and (dernier['message'] or '').startswith('FedaPay injoignable')
        if not technique or maintenant - dernier['calcule_le'] < timedelta(hours=1):
            return 0
    importes = 0
    for ecart in range(JOURS_AUTOMATIQUES, 0, -1):
        jour = maintenant.date() - timedelta(days=ecart)
        try:
            importer(jour)
            importes += 1
        except (ImportImpossible, finance.RapprochementRefuse, finance.MouvementRefuse) as erreur:
            logger.warning('Rapprochement FedaPay du %s non importé : %s', jour, erreur)
    return importes
