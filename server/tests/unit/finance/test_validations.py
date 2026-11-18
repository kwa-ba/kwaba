"""Double validation (GL-10) with fake adapters: two different people, two approvals when the system asks, the
operation run by the last approval, and nothing half done when it fails."""
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.finance.application.ports import Clock, Parametres, TransactionManager, Validations
from apps.finance.application.service import ValidationService
from apps.finance.domain.entities import Operation
from apps.finance.domain.exceptions import ValidationRefusee

from .test_service import FauxJournal

ALICE, BOB, CARLA = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


class FaussesValidations(Validations):
    def __init__(self):
        self.lignes = {}

    def creer(self, validation):
        self.lignes[validation.id] = validation
        return validation

    def verrouiller(self, validation_id):
        return self.lignes.get(validation_id)

    def enregistrer(self, validation):
        self.lignes[validation.id] = validation

    def en_attente(self, operation, objet_type, objet_id):
        return next((v for v in self.lignes.values() if (v.operation, v.objet_type, v.objet_id, v.statut)
                     == (operation, objet_type, objet_id, 'en_attente')), None)

    def derniere(self, operation, objet_type, objet_id):
        return next((v for v in reversed(list(self.lignes.values()))
                     if (v.operation, v.objet_type, v.objet_id) == (operation, objet_type, objet_id)), None)

    def liste(self, statut, limite):
        return [v for v in self.lignes.values() if not statut or v.statut == statut][:limite]


class Seuil(Parametres):
    def __init__(self, valeur):
        self.valeur = valeur

    def lire(self, cle):
        return (Decimal(self.valeur), True) if cle == 'double_validation_seuil' else None


class Transaction(TransactionManager):
    def atomic(self):
        return nullcontext()


class Horloge(Clock):
    def now(self):
        return datetime(2026, 11, 18, 12, tzinfo=timezone.utc)


def service(seuil=250_000, executer=None):
    faits = []

    def remboursement(donnees):
        faits.append(donnees)
        return f"{donnees['montant']} F remboursés"

    operations = {'remboursement_sejour': Operation('remboursement_sejour', 'Remboursement', executer or remboursement)}
    journal = FauxJournal()
    s = ValidationService(validations=FaussesValidations(), parametres=Seuil(seuil), operations=operations,
                          journal=journal, tx=Transaction(), clock=Horloge())
    return s, faits, journal


def demande(s, par_id=ALICE, montant=300_000):
    return s.demander('remboursement_sejour', objet_type='reservation', objet_id='r1', montant=montant,
                      motif='Hôte injoignable', donnees={'montant': montant}, par_id=par_id)


def test_the_threshold_says_when_a_second_person_is_needed():
    s, _, _ = service()
    assert (s.requise(249_999), s.requise(250_000)) == (False, True)
    # No decision (0): the rule is inert
    assert not service(seuil=0)[0].requise(10_000_000)


def test_the_person_who_asked_cannot_approve_and_another_one_runs_the_operation():
    s, faits, journal = service()
    v = demande(s)
    with pytest.raises(ValidationRefusee, match='autre personne'):
        s.approuver(v.id, par_id=ALICE)
    assert faits == []

    v = s.approuver(v.id, par_id=BOB)
    assert (v.statut, v.decidee_par_id, v.resultat) == ('executee', BOB, '300000 F remboursés')
    assert faits == [{'montant': 300_000}]
    assert [a for a, _, _ in journal.validations] == ['demandee', 'accordee']
    with pytest.raises(ValidationRefusee, match='déjà été décidée'):
        s.approuver(v.id, par_id=CARLA)


def test_asked_by_the_system_it_needs_two_different_approvals():
    s, faits, journal = service()
    v = demande(s, par_id=None)
    v = s.approuver(v.id, par_id=ALICE)
    assert (v.statut, v.premiere_par_id) == ('en_attente', ALICE) and faits == []
    with pytest.raises(ValidationRefusee, match='autre personne'):
        s.approuver(v.id, par_id=ALICE)
    assert s.approuver(v.id, par_id=BOB).statut == 'executee' and len(faits) == 1
    assert [a for a, _, _ in journal.validations] == ['demandee', 'premiere', 'accordee']


def test_one_request_waits_per_object():
    s, _, _ = service()
    assert demande(s).id == demande(s, par_id=BOB).id


def test_an_operation_that_fails_is_recorded_as_failed():
    def echoue(donnees):
        raise RuntimeError('FedaPay indisponible')

    s, _, journal = service(executer=echoue)
    v = s.approuver(demande(s).id, par_id=BOB)
    assert (v.statut, v.resultat) == ('echouee', 'FedaPay indisponible')
    assert journal.validations[-1][0] == 'echouee'


def test_a_refusal_needs_a_reason_and_closes_the_request():
    s, faits, _ = service()
    v = demande(s)
    with pytest.raises(ValidationRefusee, match='motif'):
        s.refuser(v.id, par_id=BOB, motif='non')
    v = s.refuser(v.id, par_id=BOB, motif='Le séjour a bien eu lieu')
    assert (v.statut, v.resultat) == ('refusee', 'Le séjour a bien eu lieu') and faits == []
    assert s.statut_de('remboursement_sejour', 'reservation', 'r1') == 'refusee'


def test_a_person_must_give_a_reason_and_the_operation_must_be_known():
    s, _, _ = service()
    with pytest.raises(ValidationRefusee, match='motif'):
        s.demander('remboursement_sejour', objet_type='reservation', objet_id='r1', montant=1, motif='',
                   donnees={}, par_id=ALICE)
    with pytest.raises(ValidationRefusee, match='inconnue'):
        s.demander('virement', objet_type='x', objet_id='1', montant=1, motif='Un motif', donnees={}, par_id=ALICE)
