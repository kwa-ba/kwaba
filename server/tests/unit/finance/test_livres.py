"""Use cases of the books, the month closing and the reports (GL-2 to GL-7, GL-19), with fake adapters: the rules
the services hold before any SQL (periods, closing order, report codes)."""
from contextlib import nullcontext
from datetime import date, datetime, timezone

import pytest

from apps.finance.application.ports import Clock, Periodes, Rapports, TransactionManager
from apps.finance.application.service import ClotureService, LivresService, RapportService
from apps.finance.domain.entities import FiltresMouvements, Page
from apps.finance.domain.exceptions import ClotureRefusee, RestitutionRefusee
from apps.finance.domain.rules import debut_exercice, est_compte_de_resultat

from .test_service import FauxJournal

MAINTENANT = datetime(2026, 11, 18, 10, tzinfo=timezone.utc)
OK = [{'controle': f'Contrôle {n}', 'resultat': '0', 'verdict': 'OK', 'que_faire': '—'} for n in range(1, 7)]


class FaussesRestitutions:
    """Only what the services call; records the arguments."""

    def __init__(self, controles=None):
        self.controles = controles or OK
        self.appels = []
        self.definis = {'recettes_type': {'axe1': 'nature', 'axe2': 'offre', 'familles': ['R'], 'offres': None}}

    def mouvements(self, filtres, decalage, limite):
        self.appels.append(('mouvements', filtres, decalage, limite))
        return Page(lignes=[], total=0)

    def livre_journal(self, debut, fin, journal, decalage, limite):
        self.appels.append(('journal', journal, decalage, limite))
        return Page(lignes=[], total=0)

    def totaux_journal(self, debut, fin, journal):
        return {'total_debit': 0, 'total_credit': 0}

    def solde_compte_avant(self, compte, auxiliaire, avant, depuis):
        self.appels.append(('avant', compte, avant, depuis))
        # 1 000 F of debit before the period, 1 500 F of debit and 300 F of credit up to its end
        return ({'total_debit': 1_000, 'total_credit': 0, 'solde_ouverture': 1_000} if avant.day == 1 and avant.month == 11
                else {'total_debit': 2_500, 'total_credit': 300, 'solde_ouverture': 2_200})

    def grand_livre_compte(self, compte, auxiliaire, debut, fin, decalage, limite):
        return Page(lignes=[], total=0)

    def balance(self, debut, fin):
        return [{'compte_general': '554', 'total_debit': 280_000, 'total_credit': 7_000},
                {'compte_general': '706', 'total_debit': 0, 'total_credit': 273_000}]

    def peut_on_cloturer(self, mois):
        return self.controles

    def rapport_defini(self, code):
        return self.definis.get(code)

    def synthese(self, debut, fin, axe1, axe2, familles, offres):
        self.appels.append(('synthese', axe1, axe2, familles, offres))
        return []


class FaussesPeriodes(Periodes):
    def __init__(self, etats=None):
        self.etats = dict(etats or {})
        self.verrouillages = []

    def serialiser(self):
        pass

    def toutes(self):
        return [{'mois': m, 'etat': e, 'verrouillee_le': None, 'verrouillee_par_id': None} for m, e in self.etats.items()]

    def verrouiller(self, mois, par_id, quand):
        self.etats[mois] = 'verrouillee'
        self.verrouillages.append((mois, par_id, quand))


class FauxRapports(Rapports):
    def __init__(self):
        self.lignes = [{'code': 'recettes_type', 'titre': 'Recettes', 'axe1': 'nature', 'axe2': 'offre'}]

    def liste(self):
        return self.lignes

    def axes(self):
        return [{'code': c, 'libelle': c} for c in ('mois', 'nature', 'offre', 'moyen')]

    def existe(self, code):
        return any(r['code'] == code for r in self.lignes)

    def creer(self, *, code, titre, axe1, axe2, familles, offres):
        self.lignes.append({'code': code, 'titre': titre, 'axe1': axe1, 'axe2': axe2, 'familles': familles,
                            'offres': offres})


class Transaction(TransactionManager):
    def atomic(self):
        return nullcontext()


class Horloge(Clock):
    def now(self):
        return MAINTENANT


def cloture(controles=None, etats=None):
    journal, periodes = FauxJournal(), FaussesPeriodes(etats)
    service = ClotureService(restitutions=FaussesRestitutions(controles), periodes=periodes, journal=journal,
                             tx=Transaction(), clock=Horloge())
    return service, periodes, journal


# --- Rules ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('compte, resultat', [('6317', True), ('706', True), ('811', True), ('554', False),
                                              ('47121', False), ('', False)])
def test_result_accounts_are_classes_6_7_and_8(compte, resultat):
    assert est_compte_de_resultat(compte) is resultat


def test_the_financial_year_is_the_calendar_year():
    assert debut_exercice(date(2027, 3, 14)) == date(2027, 1, 1)


# --- Books ------------------------------------------------------------------------------------------------------

def test_pages_are_twenty_rows_by_default_and_a_hundred_at_most():
    restitutions = FaussesRestitutions()
    livres = LivresService(restitutions=restitutions)
    livres.mouvements(FiltresMouvements())
    livres.mouvements(FiltresMouvements(), page=3, taille=500)
    assert [(a[2], a[3]) for a in restitutions.appels] == [(0, 20), (200, 100)]


@pytest.mark.parametrize('filtres, message', [
    (FiltresMouvements(du=date(2026, 11, 2), au=date(2026, 11, 1)), 'précéder'),
    (FiltresMouvements(sens='autre'), 'Sens inconnu'),
])
def test_wrong_filters_are_refused(filtres, message):
    with pytest.raises(RestitutionRefusee, match=message):
        LivresService(restitutions=FaussesRestitutions()).mouvements(filtres)


def test_a_book_covers_one_year_at_most_and_a_known_journal():
    livres = LivresService(restitutions=FaussesRestitutions())
    with pytest.raises(RestitutionRefusee, match='un an'):
        livres.livre_journal(date(2026, 1, 1), date(2027, 6, 1))
    with pytest.raises(RestitutionRefusee, match='Journal inconnu'):
        livres.livre_journal(date(2026, 11, 1), date(2026, 11, 30), 'XX')


def test_an_account_shows_its_opening_balance_the_period_and_its_closing_balance():
    restitutions = FaussesRestitutions()
    compte = LivresService(restitutions=restitutions).grand_livre_compte('554', date(2026, 11, 1), date(2026, 11, 30))
    assert {k: v for k, v in compte.items() if k != 'page'} == {
        'solde_ouverture': 1_000, 'total_debit': 1_500, 'total_credit': 300, 'solde_cloture': 2_200}
    # A balance sheet account carries its balance over from the first entry
    assert [a[3] for a in restitutions.appels] == [None, None]


def test_a_result_account_starts_the_financial_year_at_zero():
    restitutions = FaussesRestitutions()
    LivresService(restitutions=restitutions).grand_livre_compte('706', date(2026, 11, 1), date(2026, 11, 30))
    assert [a[3] for a in restitutions.appels] == [date(2026, 1, 1), date(2026, 1, 1)]


def test_the_trial_balance_says_whether_it_balances():
    balance = LivresService(restitutions=FaussesRestitutions()).balance(date(2026, 11, 1), date(2026, 11, 30))
    assert balance['totaux'] == {'total_debit': 280_000, 'total_credit': 280_000} and balance['equilibree']


# --- Closing ----------------------------------------------------------------------------------------------------

def test_a_finished_month_with_green_checks_is_locked_and_logged():
    service, periodes, journal = cloture(etats={date(2026, 10, 1): 'ouverte'})
    service.cloturer(date(2026, 10, 1), par_id='super-admin')
    assert periodes.etats[date(2026, 10, 1)] == 'verrouillee'
    assert periodes.verrouillages == [(date(2026, 10, 1), 'super-admin', MAINTENANT)]
    assert journal.clotures == [('super-admin', date(2026, 10, 1))]


@pytest.mark.parametrize('mois', [date(2026, 11, 1), date(2026, 12, 1)])
def test_the_current_month_and_a_future_one_never_close(mois):
    service, periodes, _ = cloture()
    with pytest.raises(ClotureRefusee, match='une fois terminé'):
        service.cloturer(mois, par_id=None)
    assert periodes.verrouillages == []


def test_months_close_in_order():
    service, periodes, _ = cloture(etats={date(2026, 9, 1): 'ouverte', date(2026, 10, 1): 'ouverte'})
    with pytest.raises(ClotureRefusee, match="d'abord 09/2026"):
        service.cloturer(date(2026, 10, 1), par_id=None)
    assert periodes.verrouillages == []


def test_a_month_already_locked_is_refused():
    service, _, _ = cloture(etats={date(2026, 10, 1): 'verrouillee'})
    with pytest.raises(ClotureRefusee, match='déjà clôturé'):
        service.cloturer(date(2026, 10, 1), par_id=None)


def test_a_refused_check_blocks_the_closing_and_names_it():
    refus = [*OK[:3], {'controle': 'Rapprochement du prestataire de paiement', 'resultat': '30 anomalie(s)',
                       'verdict': 'REFUSE', 'que_faire': 'Rapprocher'}, *OK[4:]]
    service, periodes, journal = cloture(controles=refus)
    with pytest.raises(ClotureRefusee, match='Rapprochement du prestataire'):
        service.cloturer(date(2026, 10, 1), par_id=None)
    assert periodes.verrouillages == [] and journal.clotures == []


def test_the_months_include_the_current_one_newest_first():
    service, _, _ = cloture(etats={date(2026, 9, 1): 'verrouillee', date(2026, 10, 1): 'ouverte'})
    assert [(m['mois'], m['etat'], m['en_cours']) for m in service.mois()] == [
        (date(2026, 11, 1), 'ouverte', True), (date(2026, 10, 1), 'ouverte', False),
        (date(2026, 9, 1), 'verrouillee', False)]


# --- Reports ----------------------------------------------------------------------------------------------------

def rapports():
    journal, restitutions = FauxJournal(), FaussesRestitutions()
    return RapportService(restitutions=restitutions, rapports=FauxRapports(), journal=journal), restitutions, journal


def test_a_new_report_is_a_row_and_is_logged():
    service, _, journal = rapports()
    cree = service.creer(code='frais_par_moyen', titre='Frais par moyen', axe1='moyen', axe2='mois', familles=['D'])
    assert cree['code'] == 'frais_par_moyen' and cree['familles'] == ['D']
    assert journal.rapports == [(None, 'frais_par_moyen', 'Frais par moyen')]


@pytest.mark.parametrize('champs, message', [
    ({'code': 'X', 'titre': 'Titre', 'axe1': 'mois'}, 'Code du rapport'),
    ({'code': 'recettes_type', 'titre': 'Titre', 'axe1': 'mois'}, 'existe déjà'),
    ({'code': 'nouveau', 'titre': 'T', 'axe1': 'mois'}, 'Titre du rapport'),
    ({'code': 'nouveau', 'titre': 'Titre', 'axe1': 'inconnu'}, 'Axe inconnu'),
    ({'code': 'nouveau', 'titre': 'Titre', 'axe1': 'mois', 'axe2': 'mois'}, 'Deux axes différents'),
    ({'code': 'nouveau', 'titre': 'Titre', 'axe1': 'mois', 'familles': ["R'; --"]}, 'Filtre invalide'),
])
def test_a_wrong_report_is_refused(champs, message):
    service, _, journal = rapports()
    with pytest.raises(RestitutionRefusee, match=message):
        service.creer(**champs)
    assert journal.rapports == []


def test_a_saved_report_runs_with_its_axes_and_filters():
    service, restitutions, _ = rapports()
    service.executer('recettes_type', date(2026, 11, 1), date(2026, 11, 30))
    assert restitutions.appels[-1] == ('synthese', 'nature', 'offre', ['R'], None)
    with pytest.raises(RestitutionRefusee, match='inconnu'):
        service.executer('absent', date(2026, 11, 1), date(2026, 11, 30))


def test_the_closing_writes_the_guarantee_fund_allocation_first():
    """GL-17: the allocation of the month is written before the checks; if it cannot be, the closing says why."""
    service, periodes, _ = cloture(etats={date(2026, 10, 1): 'ouverte'})
    dotes = []
    service.avant_cloture = lambda mois, par_id: dotes.append((mois, par_id))
    service.cloturer(date(2026, 10, 1), par_id='super-admin')
    assert dotes == [(date(2026, 10, 1), 'super-admin')]

    service, periodes, _ = cloture(etats={date(2026, 10, 1): 'ouverte'})

    def refuser(mois, par_id):
        raise ValueError('compte du fonds inactif')

    service.avant_cloture = refuser
    with pytest.raises(ClotureRefusee, match='fonds de garantie impossible : compte du fonds inactif'):
        service.cloturer(date(2026, 10, 1), par_id=None)
    assert periodes.verrouillages == []
