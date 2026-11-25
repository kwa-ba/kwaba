from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AppleUserInfo:
    """What a verified identity token of Apple says (ADR-045)."""
    apple_id: str              # "sub": stable identifier of the person for our team
    email: str                 # possibly a private relay address (…@privaterelay.appleid.com)
    email_verified: bool
    client_id: str             # "aud": identifier of the app the token was issued for


class AppleIdentityVerifier(ABC):
    @abstractmethod
    def verify(self, identity_token: str) -> AppleUserInfo:
        """Raises ValueError (message for the person) when the token is not a valid one for one of our apps."""
