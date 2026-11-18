"""Register of the deposits (GL-13) with fake adapters: a deposit received once, a withholding motivated and within the
deposit, a settlement whose amounts add up, with its document, and only once."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import pytest

from apps.finance.application.ports import Cautions, Clock, TransactionManager
from apps.finance.application.service import CautionService
from apps.finance.domain.entities import Caution
from apps.finance.domain.exceptions import CautionRefusee

MAINTENANT = datetime(2026, 11, 19, 10, tzinfo=timezone.utc)


class FauxRegistre(Cautions):
    def __init__(self):
        self.lignes = {}

    def lire(self, objet_type, objet_id, verrou=False):
        return self.lignes.get((objet_type, str(objet_id)))

    def creer(self, caution):
        self.lignes[(caution.objet_type, caution.objet_id)] = caution
        return caution

    def enregistrer(self, caution):
        self.lignes[(caution.objet_type, caution.objet_id)] = caution

    def liste(self, statut, en_retard_au, limite):
        return [c for c in self.lignes.values() if (not statut or c.statut == statut)
                and (not en_retard_au or c.date_limite < en_retard_au)][:limite]

    def total_detenu(self):
        return sum(c.montant for c in self.lignes.values() if c.statut == 'detenue')


class Transaction(TransactionManager):
    def atomic(self):
        return nullcontext()


class Horloge(Clock):
    def now(self):
        return MAINTENANT


@pytest.fixture
def registre():
    return CautionService(cautions=FauxRegistre(), tx=Transaction(), clock=Horloge())


def recevoir(registre, objet_id='l1', montant=60_000, limite=timedelta(days=2)):
    return registre.enregistrer(Caution(objet_type='location', objet_id=objet_id, reference='LOC-1', offre='VOITURE_SANS',
                                        montant=montant, recue_le=MAINTENANT - timedelta(days=5),
                                        date_limite=MAINTENANT + limite))


def test_a_deposit_is_received_once_and_counted_as_held(registre):
    recevoir(registre)
    recevoir(registre, montant=99_999)  # the same deposit delivered again
    r = registre.liste()
    assert [c.montant for c in r['cautions']] == [60_000] and r['total_detenu'] == 60_000 and r['en_retard'] == 0
    with pytest.raises(CautionRefusee, match='entier positif'):
        recevoir(registre, objet_id='l2', montant=0)


def test_a_withholding_is_motivated_and_within_the_deposit(registre):
    recevoir(registre)
    with pytest.raises(CautionRefusee, match='entre 0 et la caution'):
        registre.decider_retenue('location', 'l1', montant=60_001, motif='Trop', cgv_article='14.3', par_id=None)
    with pytest.raises(CautionRefusee, match='motif'):
        registre.decider_retenue('location', 'l1', montant=10_000, motif='', cgv_article='14.3', par_id=None)
    with pytest.raises(CautionRefusee, match='article'):
        registre.decider_retenue('location', 'l1', montant=10_000, motif='Rayure profonde', cgv_article='', par_id=None)
    c = registre.decider_retenue('location', 'l1', montant=10_000, motif='Rayure profonde', cgv_article='14.3',
                                 par_id=None)
    assert (c.montant_retenu, c.decision_le) == (10_000, MAINTENANT)
    assert registre.decider_retenue('location', 'l1', montant=0, motif='', cgv_article='', par_id=None).motif_retenue == ''


def test_a_settlement_adds_up_needs_its_document_and_happens_once(registre):
    recevoir(registre)
    registre.decider_retenue('location', 'l1', montant=10_000, motif='Rayure profonde', cgv_article='14.3', par_id=None)
    with pytest.raises(CautionRefusee, match='Rendu attendu : 50000'):
        registre.solder('location', 'l1', rendu=60_000, mode='Remboursement', document_numero='RET-2026-00001')
    with pytest.raises(CautionRefusee, match='document'):
        registre.solder('location', 'l1', rendu=50_000, mode='Remboursement', document_numero='')
    c = registre.solder('location', 'l1', rendu=50_000, mode='Remboursement', document_numero='RET-2026-00001')
    assert (c.statut, c.montant_rendu, c.soldee_le) == ('retenue', 50_000, MAINTENANT)
    with pytest.raises(CautionRefusee, match='déjà soldée'):
        registre.solder('location', 'l1', rendu=50_000, mode='Remboursement', document_numero='RET-2026-00002')
    assert registre.liste()['total_detenu'] == 0


def test_a_deposit_past_its_date_is_flagged(registre):
    recevoir(registre, limite=-timedelta(hours=1))
    assert registre.liste(en_retard=True)['en_retard'] == 1
