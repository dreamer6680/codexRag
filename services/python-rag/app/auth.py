"""Supabase JWT verification and the trusted application identity."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .settings import settings


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    email: str | None = None
    display_name: str | None = None


class AuthVerifier:
    def __init__(self, supabase_url: str, audience: str) -> None:
        self.supabase_url = supabase_url.rstrip("/")
        self.audience = audience
        self.issuer = f"{self.supabase_url}/auth/v1"
        self._jwks_client = (
            jwt.PyJWKClient(f"{self.issuer}/.well-known/jwks.json")
            if self.supabase_url
            else None
        )

    def decode(self, token: str) -> dict[str, Any]:
        if self._jwks_client is None:
            raise RuntimeError("Supabase authentication is not configured")
        signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience=self.audience,
            issuer=self.issuer,
            options={"require": ["exp", "iat", "sub"]},
        )

    def authenticate(self, token: str) -> AuthenticatedUser:
        try:
            claims = self.decode(token)
            user_id = UUID(str(claims["sub"]))
        except Exception as exc:
            raise HTTPException(
                status_code=401,
                detail="登录已失效，请重新登录",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        metadata = claims.get("user_metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        display_name = metadata.get("display_name") or metadata.get("full_name")
        return AuthenticatedUser(
            id=user_id,
            email=claims.get("email"),
            display_name=str(display_name) if display_name else None,
        )


bearer = HTTPBearer(auto_error=False)
verifier = AuthVerifier(settings.supabase_url, settings.supabase_jwt_audience)


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verifier.authenticate(credentials.credentials)
