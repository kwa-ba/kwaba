"""Invariants I1 to I4, I6 and I7 of the developers' brief (03_Prompt, « les dix invariants ») named on the control
screen, and the identity of the balances (recette live of 19 November 2026, DEV-L5)."""
import uuid

from django.db import connection
from django.utils import timezone

from apps.finance import api as finance
from apps.finance.models import RapprochementLigneModel

HOTE = str(uuid.uuid4())


def invariants() -> dict[str, int]:
    return {i['invariant']: i['anomalies'] for i in finance.controle_invariants()}


def paiement(ref='TX-1', nuits=250_000, frais_service=15_000, frais=7_000) -> uuid.UUID:
    """A stay paid as the payment flow writes it: the split (origin « paiement »), then the provider's real fees."""
    reservation = uuid.uuid4()
    commun = dict(offre='COURTE_DUREE', compte_argent='FEDAPAY', moyen_paiement='MOOV', reservation_id=reservation,
                  externe_reference=ref)
    finance.enregistrer([
        finance.Ligne(nature='T01', montant=nuits, sens=finance.ENTREE, tiers_type='hote', tiers_id=HOTE, **commun),
        finance.Ligne(nature='R01', montant=frais_service, sens=finance.ENTREE, **commun),
    ], origine='paiement')
    finance.enregistrer([finance.Ligne(nature='D01', montant=frais, sens=finance.SORTIE, **commun)],
                        origine='frais_paiement')
    return reservation


def operation(reference, montant, type_='encaissement', sens='entree', jour=None):
    return RapprochementLigneModel.objects.create(
        compte_argent_id='FEDAPAY', jour=jour or (timezone.now().date()), reference=reference, type=type_, sens=sens,
        kwaba_reference='RES-TEST', kwaba_montant=montant, externe_montant=montant, externe_frais=0,
        importe_le=timezone.now())


def test_the_control_screen_names_the_seventeen_invariants_in_order():
    assert [i['invariant'] for i in finance.controle_invariants()] == [f'I{n}' for n in range(1, 18)]
    assert all(i['anomalies'] == 0 for i in finance.controle_invariants())


def test_i1_a_collection_is_split_into_revenue_partner_money_and_deposit_only():
    paiement()
    assert invariants()['I1'] == 0

    # A charge slipped into the split of a payment: what was collected is no longer R + T + C
    finance.enregistrer([finance.Ligne(nature='D10', offre='COURTE_DUREE', montant=1_000, sens=finance.SORTIE,
                                       compte_argent='FEDAPAY', externe_reference='TX-2')], origine='paiement')
    assert invariants()['I1'] == 1


def test_i2_the_amount_kwaba_recorded_equals_its_split_in_the_ledger():
    paiement()
    operation('TX-1', 265_000)
    assert invariants()['I2'] == 0

    RapprochementLigneModel.objects.filter(reference='TX-1').update(kwaba_montant=266_000)
    assert invariants()['I2'] == 1


def test_i3_the_balance_of_the_day_is_collected_minus_refunded_minus_paid_out_on_both_sides():
    paiement()
    finance.enregistrer([finance.Ligne(nature='T09', offre='COURTE_DUREE', montant=100_000, sens=finance.SORTIE,
                                       compte_argent='FEDAPAY', tiers_type='hote', tiers_id=HOTE,
                                       externe_reference='PO-1')], origine='versement')
    operation('TX-1', 265_000)
    operation('PO-1', 100_000, type_='versement', sens='sortie')
    # The provider's fees D01 are Kwa-Ba's charge, not part of what Kwa-Ba recorded: they do not count
    assert invariants()['I3'] == 0

    RapprochementLigneModel.objects.filter(reference='PO-1').update(kwaba_montant=90_000)
    assert invariants()['I3'] == 1


def test_i4_the_sums_owed_by_third_party_add_up_to_the_total_owed():
    paiement()
    # A driver not assigned yet: his share is owed to « to be assigned », still in the total
    finance.enregistrer([finance.Ligne(nature='T04', offre='TRANSFERT', montant=6_000, sens=finance.ENTREE,
                                       compte_argent='FEDAPAY', tiers_type='chauffeur', externe_reference='TX-3')],
                        origine='paiement')
    du = finance.du_aux_partenaires()
    with connection.cursor() as c:
        c.execute("SELECT SUM(montant_signe) FROM finance_mouvement_signe WHERE famille = 'T'")
        total_t = c.fetchone()[0]
    assert sum(d['solde_du'] for d in du) == total_t == 256_000
    assert invariants()['I4'] == 0


def test_i6_and_i7_each_journal_balances_and_r_minus_d_is_the_result_of_the_balance():
    paiement()
    assert invariants()['I6'] == 0 and invariants()['I7'] == 0
    resultat = sum(r['solde'] for r in finance.balance_generale(finance.mois_de(timezone.now()))
                   if r['compte_general'][0] in '678')
    # Revenue 15 000 (credit) less the fees 7 000 (debit): the balance shows -8 000 (debit - credit)
    assert resultat == -8_000


def test_the_identity_of_the_balances_reads_without_a_calculation():
    paiement()
    fedapay = next(i for i in finance.identite_soldes() if i['compte_argent_code'] == 'FEDAPAY')
    assert fedapay == {'compte_argent_code': 'FEDAPAY', 'revenu': 15_000, 'du_partenaires': 250_000,
                       'du_voyageurs': 0, 'cautions': 0, 'frais_paiement': 7_000, 'autres': 0, 'solde': 258_000}
    assert (fedapay['revenu'] + fedapay['du_partenaires'] + fedapay['du_voyageurs'] + fedapay['cautions']
            - fedapay['frais_paiement'] + fedapay['autres']) == fedapay['solde'] == finance.soldes_comptes_argent()[
        'FEDAPAY']
