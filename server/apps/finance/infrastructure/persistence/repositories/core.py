"""Shared pieces of the Django adapters: refusals of the database guards, transactions."""
from contextlib import AbstractContextManager

from django.db import DatabaseError, transaction

from apps.finance.application.ports import (
    TransactionManager,
)

# SQLSTATE of RAISE EXCEPTION: a refusal of the database guards (migration 0003)
REFUS_BASE = 'P0001'


def diagnostic(erreur: DatabaseError):
    """Diagnostic of the PostgreSQL error (psycopg 2 and 3 both give .diag with sqlstate, constraint_name and
    message_primary)."""
    return getattr(erreur.__cause__, 'diag', None)


class DjangoTransactionManager(TransactionManager):
    def atomic(self) -> AbstractContextManager:
        return transaction.atomic()


def _actifs(modele, codes, champ: str = 'actif') -> dict[str, bool]:
    codes = {code for code in codes if code}
    return dict(modele.objects.filter(code__in=codes).values_list('code', champ)) if codes else {}


def _texte_id(valeur) -> str | None:
    return None if valeur is None else str(valeur)
