"""Cut-off of the service fees (ADR-034)."""
from abc import ABC, abstractmethod
from datetime import date


class CutOff(ABC):
    @abstractmethod
    def serialiser(self) -> None:
        """Two cut-offs at the same time: the second waits for the first."""

    @abstractmethod
    def mois_a_regulariser(self, avant: date) -> list[date]:
        """Months before `avant`, not locked, holding service fees, oldest first."""

    @abstractmethod
    def ecarts(self, mois: date) -> list[dict]:
        """Bookings whose 477 at the end of `mois` is not what it should be:
        {reservation_id, offre_code, frais, en_attente, commence_le}."""

    @abstractmethod
    def nb_lignes(self, mois: date, reservation_id) -> int:
        """Cut-off lines already written for the booking and the month (to number the next one)."""
