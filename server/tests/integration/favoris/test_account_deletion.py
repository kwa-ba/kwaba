"""Account deletion (ADR-039): the favourites are erased."""
from apps.favoris.models import FavoriModel


def test_the_favourites_are_erased(make_user, make_hebergement, delete_account):
    voyageur = make_user()
    FavoriModel.objects.create(user_id=voyageur.pk, hebergement_id=make_hebergement().pk)

    assert delete_account(voyageur).status_code == 204

    assert not FavoriModel.objects.filter(user_id=voyageur.pk).exists()
