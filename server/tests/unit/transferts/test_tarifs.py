from apps.transferts import tarifs


def test_prix_et_commission():
    p = tarifs.calculer(10000)
    assert p.prix == 10000
    assert (p.commission, p.montant_chauffeur) == (1500, 8500)  # 15 % (grid of 18 October 2026)


def test_aucune_majoration_de_nuit():
    # Removed by decision of the founders (audit no. 3): no more variable nor night calculation
    assert not any('nuit' in nom.lower() for nom in vars(tarifs))
    assert tarifs.calculer(15000).prix == 15000
