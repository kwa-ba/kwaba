"""Helpers shared by the finance screens: identifiers, periods, pagination, CSV."""
import csv
import io
import uuid
from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response

from apps.finance import api as finance
from apps.finance.domain.entities import TYPES_SANS_RELEVE
from apps.finance.infrastructure.persistence.models import (
    CompteArgentModel,
)
from apps.users import api as users

INCONNU = {'nom': '', 'email': ''}


def _uuid(valeur):
    try:
        return uuid.UUID(str(valeur))
    except (TypeError, ValueError):
        return None


def _comptes(tiers_ids) -> dict[str, dict]:
    """Name and email of the third parties that are accounts (hosts, travellers), in one read: two hosts may have
    the same name. Others (drivers, rental partners) keep their id."""
    ids = {u for u in (_uuid(t) for t in tiers_ids) if u}
    return {str(pk): {'nom': f"{c.first_name} {c.last_name}".strip() or c.email, 'email': c.email}
            for pk, c in users.comptes(ids).items()}


def _tiers_de_auxiliaire(auxiliaire: str | None) -> str:
    """The id of the third party in a sub-account « HOTE-<id> »."""
    return (auxiliaire or '').partition('-')[2]


def _refus(message: str, code=status.HTTP_400_BAD_REQUEST) -> Response:
    return Response({'detail': message}, status=code)


def _entier(valeur, defaut: int) -> int:
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return defaut


def _pagination(request) -> tuple[int, int]:
    return max(1, _entier(request.query_params.get('page'), 1)), _entier(request.query_params.get('page_size'), 20)


def _liste(lignes: list, total: int, page: int, taille: int, **extra) -> Response:
    """Paginated list of the back-office: {results, count, page, page_size} (backoffice-api.md)."""
    return Response({'results': lignes, 'count': total, 'page': page, 'page_size': min(max(taille, 1), 100), **extra})


def _periode(request) -> tuple[date, date]:
    """?debut=&fin= (YYYY-MM-DD, both included); this month so far by default."""
    aujourdhui = timezone.localdate()
    return (parse_date(request.query_params.get('debut') or '') or aujourdhui.replace(day=1),
            parse_date(request.query_params.get('fin') or '') or aujourdhui)


def _mois(texte: str | None) -> date | None:
    """« 2026-11 » → 1 November 2026."""
    return parse_date(f'{texte}-01') if texte and len(texte) == 7 else None


def _texte_csv(valeur):
    """A cell a spreadsheet must not read as a formula (CSV injection)."""
    if isinstance(valeur, str) and valeur[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + valeur
    return valeur


def _csv(entetes: list[str], lignes: list[list], nom: str) -> HttpResponse:
    """A CSV for a spreadsheet or an accounting software: separator ;, UTF-8 with BOM (Excel)."""
    tampon = io.StringIO()
    ecrit = csv.writer(tampon, delimiter=';')
    ecrit.writerow(entetes)
    for ligne in lignes:
        ecrit.writerow([_texte_csv(v) for v in ligne])
    reponse = HttpResponse(('﻿' + tampon.getvalue()).encode('utf-8'), content_type='text/csv; charset=utf-8')
    reponse['Content-Disposition'] = f'attachment; filename="{nom}"'
    reponse['Cache-Control'] = 'no-store'
    return reponse


def _soldes_reels() -> dict[str, int]:
    """Ledger balance of the money accounts that hold money (the account of passage and the fund have no statement)."""
    types = dict(CompteArgentModel.objects.values_list('code', 'type'))
    return {code: v for code, v in finance.soldes_comptes_argent().items() if types.get(code) not in TYPES_SANS_RELEVE}
