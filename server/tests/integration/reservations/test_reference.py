"""Reference of a booking under the Kwa-Ba identity (DEV-F2): RES-KB, the former RES-AF still found."""
from apps.reservations import api as reservations


def test_reference_carries_the_kwaba_prefix(make_hebergement, make_reservation):
    r = make_reservation(make_hebergement())
    assert r.reference == f'RES-KB{r.created_at.year}-{str(r.id)[:4].upper()}'


def test_search_finds_the_new_and_the_former_prefix(make_hebergement, make_reservation):
    r = make_reservation(make_hebergement())
    former = r.reference.replace('RES-KB', 'RES-AF')
    for reference in (r.reference, r.reference.lower(), former):
        assert [o.id for o in reservations.par_reference(reference)] == [r.id]
    assert reservations.par_reference(r.reference.replace('RES-KB', 'RES-XX')) == []
