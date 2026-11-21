"""Register of the deposits."""
from abc import ABC, abstractmethod
from datetime import datetime

from apps.finance.domain.entities import Caution


class Cautions(ABC):
    """Register of the deposits (GL-13)."""

    @abstractmethod
    def lire(self, objet_type: str, objet_id: str, verrou: bool = False) -> Caution | None:
        pass

    @abstractmethod
    def creer(self, caution: Caution) -> Caution:
        pass

    @abstractmethod
    def enregistrer(self, caution: Caution) -> None:
        pass

    @abstractmethod
    def liste(self, statut: str | None, en_retard_au: datetime | None, limite: int) -> list[Caution]:
        pass

    @abstractmethod
    def total_detenu(self) -> int:
        pass
