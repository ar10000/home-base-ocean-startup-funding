"""Sign-in tokens from Keycloak (ADR-006): verify signature, issuer, audience and expiry.

Keycloak's signing keys come from its JWKS endpoint and are cached. The settings come
from the environment; with none set, every request is refused (nothing is open by
accident). Token contents are never logged.
"""

import os
from dataclasses import dataclass
from functools import lru_cache

import jwt

from home_base.core.errors import NotSignedInError

ISSUER_ENV = "HOME_BASE_OIDC_ISSUER"  # e.g. https://<keycloak>/realms/home-base
AUDIENCE_ENV = "HOME_BASE_OIDC_AUDIENCE"  # the API's client ID, e.g. home-base-api


@dataclass(frozen=True, slots=True)
class Identity:
    subject: str
    given_name: str | None


class TokenVerifier:
    def __init__(self, issuer: str, audience: str) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self._keys = jwt.PyJWKClient(
            f"{self.issuer}/protocol/openid-connect/certs", cache_keys=True
        )

    def verify(self, token: str) -> Identity:
        try:
            key = self._keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise NotSignedInError("your sign-in is not valid; sign in again") from exc
        return Identity(subject=str(claims["sub"]), given_name=claims.get("given_name"))


@lru_cache(maxsize=1)
def verifier() -> TokenVerifier:
    issuer, audience = os.environ.get(ISSUER_ENV), os.environ.get(AUDIENCE_ENV)
    if not issuer or not audience:
        raise NotSignedInError("sign-in is not configured")
    return TokenVerifier(issuer, audience)
