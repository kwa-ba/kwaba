"""Deposit chosen by the host on a listing (ADR-036): options, checks against the referential, hotels left out."""
from apps.finance.models import ParametreModel
from apps.paiements.models import ConditionsHoteModel

HEBERGEMENTS = '/api/v1/hebergements/'


def _ouvrir_le_sequestre():
    ParametreModel.objects.filter(cle='caution_sequestre_active').update(valeur=1)


def _changer(client, annonce, **champs):
    return client.patch(f'{HEBERGEMENTS}{annonce.id}/', champs, format='json')


def test_a_listing_has_no_deposit_by_default(make_hebergement):
    annonce = make_hebergement()
    assert (annonce.deposit_option, annonce.deposit_rate, annonce.guarantee_fee) == ('none', None, None)


def test_the_enhanced_guarantee_keeps_its_fee(client_for, make_hebergement, make_user):
    hote = make_user(role='hote')
    annonce, client = make_hebergement(host=hote), client_for(hote)

    assert _changer(client, annonce, deposit_option='enhanced_guarantee').status_code == 400
    r = _changer(client, annonce, deposit_option='enhanced_guarantee', guarantee_fee=5_000, deposit_rate='10')

    assert r.status_code == 200, r.data
    annonce.refresh_from_db()
    assert (annonce.deposit_option, annonce.guarantee_fee, annonce.deposit_rate) == ('enhanced_guarantee', 5_000, None)


def test_the_escrowed_deposit_waits_for_fedapay(client_for, make_hebergement, make_user):
    hote = make_user(role='hote')
    annonce, client = make_hebergement(host=hote), client_for(hote)

    refus = _changer(client, annonce, deposit_option='escrow', deposit_rate='10')
    assert refus.status_code == 400 and "pas encore ouverte" in str(refus.data)

    _ouvrir_le_sequestre()
    assert _changer(client, annonce, deposit_option='escrow', deposit_rate='10').status_code == 200
    annonce.refresh_from_db()
    assert (annonce.deposit_option, str(annonce.deposit_rate)) == ('escrow', '10.00')


def test_the_rate_is_capped_by_the_server(client_for, make_hebergement, make_user):
    _ouvrir_le_sequestre()
    hote = make_user(role='hote')
    annonce, client = make_hebergement(host=hote), client_for(hote)

    for taux in ('45', '0', 'abc'):
        assert _changer(client, annonce, deposit_option='escrow', deposit_rate=taux).status_code == 400
    assert _changer(client, annonce, deposit_option='escrow', deposit_rate='40').status_code == 200


def test_going_back_to_no_deposit_empties_the_other_fields(client_for, make_hebergement, make_user):
    _ouvrir_le_sequestre()
    hote = make_user(role='hote')
    annonce, client = make_hebergement(host=hote), client_for(hote)
    _changer(client, annonce, deposit_option='escrow', deposit_rate='15')

    assert _changer(client, annonce, deposit_option='none').status_code == 200
    annonce.refresh_from_db()
    assert (annonce.deposit_option, annonce.deposit_rate, annonce.guarantee_fee) == ('none', None, None)


def test_a_hotel_takes_no_deposit(client_for, make_hebergement, make_user):
    hote = make_user(role='hote')
    ConditionsHoteModel.objects.create(hote_id=hote.pk, categorie='hotel')
    annonce, client = make_hebergement(host=hote), client_for(hote)

    refus = _changer(client, annonce, deposit_option='enhanced_guarantee', guarantee_fee=5_000)
    assert refus.status_code == 400 and 'hôtel' in str(refus.data)


def test_the_rules_are_given_to_the_site(api_client):
    regles = api_client.get('/api/v1/paiements/config/').json()['deposit']
    assert regles == {'rate_max': 40.0, 'rate_proposed': 10.0, 'rate_warning': 20.0, 'minimum': 5000, 'ceiling': 150000,
                      'rounding': 500, 'guarantee_multiple': 5, 'escrow_open': False}
