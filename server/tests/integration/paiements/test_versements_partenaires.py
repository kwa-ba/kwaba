"""Payouts to the partners (GL-11) and recovery of a payout made for a stay cancelled afterwards (GL-23, FF-04): the
page of every payout due, a failed one sent again, the daily alert, and what a host received for a cancelled stay
withheld on their next payouts. FedaPay is simulated (test_versements_surs)."""
from datetime import timedelta

import pytest
from django.core import mail
from django.core.cache import cache
from django.utils import timezone

from apps.activity.models import ActivityEntryModel
from apps.paiements import services, versements
from apps.paiements.models import RetenueVersementModel, VersementModel
from apps.paiements.registre import PRODUITS, ProduitPaye

from .test_versements_surs import FedaPayEtat, fedapay_etat, versement_du  # noqa: F401 (fixtures)

PAGE = '/api/v1/admin/paiements/finances/versements/'


@pytest.fixture
def finance(make_user, client_for):
    def _creer(*permissions):
        u = make_user(role='admin', admin_sections=['finances'], admin_permissions=list(permissions))
        return client_for(u)
    return _creer


def _autre_sejour(versement, make_hebergement, make_reservation, montant):
    """A payout of another stay of the same host, due now."""
    from django.contrib.auth import get_user_model

    hote = get_user_model().objects.get(pk=versement.hote_id)
    resa = make_reservation(make_hebergement(host=hote), starts_in=-3)
    return VersementModel.objects.create(reservation_id=resa.id, hote_id=hote.pk, montant_brut=montant, commission=0,
                                         montant=montant, date_prevue=timezone.now() - timedelta(hours=1))


# --- Recovery after a payout (GL-23) ------------------------------------------------------------------------------

def test_a_cancelled_stay_already_paid_is_withheld_on_the_next_payout(fedapay_etat, versement_du,  # noqa: F811
                                                                     make_hebergement, make_reservation):
    deja_paye = _autre_sejour(versement_du, make_hebergement, make_reservation, 30_000)
    VersementModel.objects.filter(pk=deja_paye.pk).update(statut='envoye', envoye_le=timezone.now())
    deja_paye.refresh_from_db()
    # Cancelled after the payout: the scale lets the host keep 5 000 F
    r = versements.ouvrir_recuperation(deja_paye, 5_000, motif='Annulation par le voyageur après le versement')
    assert r.montant == 25_000

    services.envoyer_versements_dus()

    versement_du.refresh_from_db()
    assert (versement_du.retenue, versement_du.montant, versement_du.statut) == (25_000, 30_200, 'en_cours')
    assert [p['montant'] for p in fedapay_etat.payouts.values()] == [30_200]
    r.refresh_from_db()
    assert (r.recupere, r.statut) == (25_000, 'soldee')
    assert RetenueVersementModel.objects.get().versement_id == versement_du.pk


def test_a_payout_smaller_than_the_debt_is_fully_withheld(fedapay_etat, versement_du,  # noqa: F811
                                                          make_hebergement, make_reservation):
    deja_paye = _autre_sejour(versement_du, make_hebergement, make_reservation, 100_000)
    VersementModel.objects.filter(pk=deja_paye.pk).update(statut='envoye', envoye_le=timezone.now())
    deja_paye.refresh_from_db()
    r = versements.ouvrir_recuperation(deja_paye, 0, motif="Annulation par l'hôte après le versement")

    services.envoyer_versements_dus()

    versement_du.refresh_from_db()
    # Nothing leaves: the whole payout pays back part of the debt, and no « payout of 0 F » email is sent
    assert (versement_du.statut, versement_du.montant, versement_du.retenue, versement_du.notifie) == (
        'envoye', 0, 55_200, True)
    assert fedapay_etat.payouts == {}
    r.refresh_from_db()
    assert (r.reste, r.statut) == (44_800, 'en_cours')


def test_a_payout_changed_before_leaving_gives_its_withholding_back(fedapay_etat, versement_du,  # noqa: F811
                                                                     make_hebergement, make_reservation):
    deja_paye = _autre_sejour(versement_du, make_hebergement, make_reservation, 10_000)
    VersementModel.objects.filter(pk=deja_paye.pk).update(statut='envoye')
    deja_paye.refresh_from_db()
    r = versements.ouvrir_recuperation(deja_paye, 0, motif='Annulation après le versement')
    versements.retenir(versement_du)
    assert versement_du.montant == 45_200

    versements.liberer_retenues(versement_du)

    assert (versement_du.montant, versement_du.retenue) == (55_200, 0)
    r.refresh_from_db()
    assert (r.recupere, r.statut) == (0, 'en_cours') and not RetenueVersementModel.objects.exists()


def test_a_payout_that_fails_after_the_cancellation_paid_nothing(fedapay_etat, versement_du):  # noqa: F811
    VersementModel.objects.filter(pk=versement_du.pk).update(statut='en_cours', payout_id='P9')
    versement_du.refresh_from_db()
    r = versements.ouvrir_recuperation(versement_du, 0, motif='Annulation pendant le versement')
    fedapay_etat.payouts['P9'] = {'status': 'failed', 'montant': 55_200}

    services.synchroniser_payout(versement_du)

    versement_du.refresh_from_db()
    r.refresh_from_db()
    # Never sent again in full for a cancelled stay, nothing to recover
    assert versement_du.statut == 'annule' and r.statut == 'annulee'


def test_a_host_without_a_coming_payout_is_asked_to_pay_back(fedapay_etat, versement_du, finance):  # noqa: F811
    VersementModel.objects.filter(pk=versement_du.pk).update(statut='envoye')
    versement_du.refresh_from_db()
    r = versements.ouvrir_recuperation(versement_du, 0, motif='Annulation après le versement')
    admin = finance('finance_operations')

    d = admin.get(PAGE).json()
    [ligne] = d['recuperations']
    assert (ligne['reste'], ligne['versement_a_venir']) == (55_200, False) and d['totaux']['a_recuperer'] == 55_200

    reponse = admin.post(f"/api/v1/admin/paiements/finances/recuperations/{r.pk}/relancer/", {}, format='json')

    assert reponse.status_code == 200 and reponse.json()['relances'] == 1
    [email] = [m for m in mail.outbox if 'annulé après votre versement' in m.subject]
    assert '55 200' in email.body
    assert ActivityEntryModel.objects.filter(action='recuperation_relancee').exists()


# --- The payouts page (GL-11) -------------------------------------------------------------------------------------

def test_a_failed_payout_is_listed_late_and_sent_again(fedapay_etat, versement_du, finance):  # noqa: F811
    VersementModel.objects.filter(pk=versement_du.pk).update(
        statut='echoue', tentatives=5, derniere_erreur='Numéro invalide', notifie=True,
        date_prevue=timezone.now() - timedelta(days=3))
    admin = finance('finance_operations')

    d = admin.get(PAGE).json()

    [ligne] = d['versements']
    assert (ligne['type'], ligne['statut'], ligne['en_retard'], ligne['relancable'], ligne['derniere_erreur']) == (
        'hote', 'echoue', True, True, 'Numéro invalide')
    assert (d['totaux']['echoues'], d['totaux']['en_retard'], d['totaux']['du'], d['retard_heures']) == (1, 1, 55_200, 24)

    r = admin.post(f"{PAGE}hote/{versement_du.pk}/relancer/", {}, format='json')

    assert r.status_code == 200
    versement_du.refresh_from_db()
    assert (versement_du.statut, versement_du.tentatives, versement_du.derniere_erreur, versement_du.notifie) == (
        'planifie', 0, '', False)
    assert ActivityEntryModel.objects.filter(action='versement_relance').exists()
    # Only a failed payout is sent again
    assert admin.post(f"{PAGE}hote/{versement_du.pk}/relancer/", {}, format='json').status_code == 409


def test_sending_again_needs_the_finance_operations_permission(versement_du, finance):  # noqa: F811
    VersementModel.objects.filter(pk=versement_du.pk).update(statut='echoue')
    lecteur = finance()
    assert lecteur.get(PAGE).json()['peut_operer'] is False
    assert lecteur.post(f"{PAGE}hote/{versement_du.pk}/relancer/", {}, format='json').status_code == 403


def test_the_payouts_of_the_other_products_come_through_the_registry(monkeypatch, finance):
    relances = []
    ligne = {'id': 'c1', 'categorie': 'Chauffeur (transfert)', 'beneficiaire': 'Koffi', 'objet': 'TRF-1',
             'montant': 12_000, 'retenue': 0, 'commission': 2_000, 'statut': 'echoue',
             'date_prevue': timezone.now() - timedelta(hours=2), 'envoye_le': None, 'tentatives': 5,
             'derniere_erreur': 'Refus'}
    monkeypatch.setitem(PRODUITS, 'essai', ProduitPaye(type='essai', a_verser=lambda statut: [ligne],
                                                      relancer=relances.append))
    admin = finance('finance_operations')

    [x] = [v for v in admin.get(PAGE).json()['versements'] if v['type'] == 'essai']
    assert (x['relancable'], x['en_retard']) == (True, False)
    import uuid
    pk = uuid.uuid4()
    assert admin.post(f"{PAGE}essai/{pk}/relancer/", {}, format='json').status_code == 200
    assert relances == [pk]


def test_late_and_failed_payouts_are_reported_once_a_day(versement_du, make_user):  # noqa: F811
    make_user(role='admin', admin_sections=['finances'])
    VersementModel.objects.filter(pk=versement_du.pk).update(statut='echoue')
    cache.delete(f'paiements:alerte_versements:{timezone.localdate():%Y-%m-%d}')

    assert versements.alerter_retards() == 1
    assert versements.alerter_retards() == 0
    [email] = [m for m in mail.outbox if 'Versements aux partenaires' in m.subject]
    assert 'en échec, à relancer : 1' in email.body and '55' not in email.body
