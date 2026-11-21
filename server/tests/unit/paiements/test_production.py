"""Recette DEV-L3, decision D1 (ADR-033): the payment simulation (PAIEMENT_HORS_LIGNE) is only for development."""
from apps.paiements.checks import aucune_confirmation_sans_paiement_en_production
from config.settings import _env_bool


def test_the_simulation_is_off_by_default_outside_development(monkeypatch):
    monkeypatch.delenv('PAIEMENT_HORS_LIGNE', raising=False)
    # settings.py: PAIEMENT_HORS_LIGNE = _env_bool('PAIEMENT_HORS_LIGNE', str(DEBUG))
    assert _env_bool('PAIEMENT_HORS_LIGNE', str(False)) is False
    assert _env_bool('PAIEMENT_HORS_LIGNE', str(True)) is True


def test_the_deployment_stops_if_it_is_on_outside_development(settings):
    settings.DEBUG, settings.PAIEMENT_HORS_LIGNE = False, True
    assert [e.id for e in aucune_confirmation_sans_paiement_en_production()] == ['paiements.E001']

    settings.PAIEMENT_HORS_LIGNE = False
    assert aucune_confirmation_sans_paiement_en_production() == []


def test_the_preprod_no_longer_simulates_payments(settings):
    """Decision D1 (ADR-033): the preprod goes through the FedaPay sandbox, like the production."""
    settings.DEBUG, settings.PAIEMENT_HORS_LIGNE = False, True
    settings.FRONTEND_URL = 'https://preprod.kwa-ba.com'
    assert [e.id for e in aucune_confirmation_sans_paiement_en_production()] == ['paiements.E001']


def test_development_may_simulate_payments(settings):
    settings.DEBUG, settings.PAIEMENT_HORS_LIGNE = True, True
    assert aucune_confirmation_sans_paiement_en_production() == []
