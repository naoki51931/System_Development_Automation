from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import jwt


class TokenVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedAccessToken:
    subject: str
    expires_at: datetime
    claims: Mapping[str, Any]


class AccessTokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedAccessToken: ...


class CognitoAccessTokenVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        client_id: str,
        key_provider: Callable[[str], Any],
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.key_provider = key_provider

    def verify(self, token: str) -> VerifiedAccessToken:
        try:
            header = jwt.get_unverified_header(token)
            key_id = header.get("kid")
            if not key_id:
                raise TokenVerificationError("JWT kid is missing")
            claims = jwt.decode(
                token,
                key=self.key_provider(key_id),
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"verify_aud": False, "require": ["exp", "iss", "sub", "token_use"]},
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise TokenVerificationError("Access token validation failed") from exc

        if claims.get("token_use") != "access":
            raise TokenVerificationError("JWT token_use must be access")
        audience = claims.get("aud")
        audiences = {audience} if isinstance(audience, str) else set(audience or [])
        if claims.get("client_id") != self.client_id and self.client_id not in audiences:
            raise TokenVerificationError("JWT client does not match")

        return VerifiedAccessToken(
            subject=str(claims["sub"]),
            expires_at=datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc),
            claims=claims,
        )


class StaticAccessTokenVerifier:
    def __init__(self, tokens: Mapping[str, VerifiedAccessToken]) -> None:
        self.tokens = tokens

    def verify(self, token: str) -> VerifiedAccessToken:
        try:
            verified = self.tokens[token]
        except KeyError as exc:
            raise TokenVerificationError("Access token validation failed") from exc
        if verified.expires_at <= datetime.now(timezone.utc):
            raise TokenVerificationError("Access token expired")
        return verified
