"""Reading a CSV bank statement (GL-22): columns named by the person who imports, French and English number formats,
a stable reference for a line without one, and a clear refusal with the line number."""
from datetime import date

import pytest

from apps.finance.domain import releve
from apps.finance.domain.entities import ENTREE, SORTIE
from apps.finance.domain.exceptions import VirementRefuse

COLONNES = {'date': 'Date opération', 'libelle': 'Libellé', 'debit': 'Débit', 'credit': 'Crédit'}


@pytest.mark.parametrize('texte, attendu', [
    ('1 234 567', 1_234_567), ('1.234.567', 1_234_567), ('1234567,00', 1_234_567), ('12 500,50', 12_501),
    ('-3 000', -3_000), ('(2 000)', -2_000), ('', None), ('1 000', 1_000), ('750 F CFA', 750), ('1,234', 1_234),
])
def test_amounts_of_every_format(texte, attendu):
    assert releve.montant(texte) == attendu


def test_a_statement_with_debit_and_credit_columns():
    texte = ('Date opération;Libellé;Débit;Crédit\n'
             '03/12/2026;VIREMENT FEDAPAY KWA-BA;;450 000\n'
             '04/12/2026;FRAIS TENUE DE COMPTE;2 500;\n'
             '\n'
             '04/12/2026;FRAIS TENUE DE COMPTE;2 500;\n')

    lignes = releve.lire(texte, COLONNES)

    assert [(x.jour, x.montant, x.sens) for x in lignes] == [
        (date(2026, 12, 3), 450_000, ENTREE), (date(2026, 12, 4), 2_500, SORTIE), (date(2026, 12, 4), 2_500, SORTIE)]
    # Two identical lines stay two operations, and keep their references when imported again
    assert lignes[1].reference != lignes[2].reference
    assert [x.reference for x in releve.lire(texte, COLONNES)] == [x.reference for x in lignes]


def test_a_signed_amount_column_and_the_bank_reference():
    texte = 'Date,Label,Amount,Ref\n2026-12-03,Transfer in,"450,000",VB-123\n2026-12-04,Fees,-2500,VB-124\n'
    lignes = releve.lire(texte, {'date': 'Date', 'libelle': 'Label', 'montant': 'Amount', 'reference': 'Ref'})
    assert [(x.montant, x.sens, x.reference) for x in lignes] == [(450_000, ENTREE, 'VB-123'), (2_500, SORTIE, 'VB-124')]


@pytest.mark.parametrize('texte, colonnes, message', [
    ('Date;Libellé\n03/12/2026;x\n', COLONNES, 'absente'),
    ('Date opération;Libellé;Débit;Crédit\n31/31/2026;x;1;\n', COLONNES, 'ligne 2 : date illisible'),
    ('Date opération;Libellé;Débit;Crédit\n03/12/2026;x;1;2\n', COLONNES, 'débit et crédit'),
    ('Date opération;Libellé;Débit;Crédit\n', COLONNES, 'Aucune opération'),
    ('', COLONNES, 'vide'),
    ('Date opération;Libellé;Débit;Crédit\n03/12/2026;x;1;\n', {'date': 'Date opération'}, 'débit et du crédit'),
])
def test_a_statement_that_cannot_be_read_is_refused(texte, colonnes, message):
    with pytest.raises(VirementRefuse, match=message):
        releve.lire(texte, colonnes)
