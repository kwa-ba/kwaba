"""Recette DEV-L3: the payment simulation (PAIEMENT_HORS_LIGNE) can never be on in production."""
from apps.paiements.checks import aucune_confirmation_sans_paiement_en_production
from config.settings import _env_bool


def test_the_simulation_is_off_by_default_outside_development(monkeypatch):
    monkeypatch.delenv('PAIEMENT_HORS_LIGNE', raising=False)
    # settings.py: PAIEMENT_HORS_LIGNE = _env_bool('PAIEMENT_HORS_LIGNE', str(DEBUG))
    assert _env_bool('PAIEMENT_HORS_LIGNE', str(False)) is False
    assert _env_bool('PAIEMENT_HORS_LIGNE', str(True)) is True


def test_the_deployment_stops_if_it_is_on_in_production(settings):
    settings.FRONTEND_URL, settings.PAIEMENT_HORS_LIGNE = 'https://kwa-ba.com', True
    assert [e.id for e in aucune_confirmation_sans_paiement_en_production()] == ['paiements.E001']

    settings.PAIEMENT_HORS_LIGNE = False
    assert aucune_confirmation_sans_paiement_en_production() == []

    # The preprod may simulate payments (decision D1)
    settings.FRONTEND_URL, settings.PAIEMENT_HORS_LIGNE = 'https://preprod.kwa-ba.com', True
    assert aucune_confirmation_sans_paiement_en_production() == []
