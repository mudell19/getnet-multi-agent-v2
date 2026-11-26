"""HS256 JWT issue/verify and FastAPI role dependencies."""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from getnet_multi_agent.contracts import Principal
from getnet_multi_agent.core.settings import get_settings

_ROLES = ("merchant", "operator")
_bearer = HTTPBearer(auto_error=False)


class AuthError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


def _secret(settings) -> str:
    secret = settings.JWT_SECRET.get_secret_value()
    if not secret:
        raise AuthError(500, "misconfigured", "JWT_SECRET is empty")
    return secret


def issue_token(settings, sub: str, role: str, ttl_minutes: int = 60) -> str:
    if role not in _ROLES:
        raise ValueError(f"invalid role: {role}")
    now = datetime.now(UTC)
    claims = {
        "iss": settings.JWT_ISSUER, "aud": settings.JWT_AUDIENCE, "sub": sub, "role": role,
        "iat": now, "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(claims, _secret(settings), algorithm="HS256")


def verify_token(settings, token: str) -> Principal:
    key = _secret(settings)
    try:
        claims = jwt.decode(
            token, key, algorithms=["HS256"], audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER, options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except jwt.PyJWTError as e:
        raise AuthError(401, "unauthorized", "invalid or expired token") from e
    if claims.get("role") not in _ROLES:
        raise AuthError(401, "unauthorized", "invalid role claim")
    return Principal(sub=str(claims["sub"]), role=claims["role"])


def _principal(
    creds: HTTPAuthorizationCredentials | None, settings
) -> Principal:
    if creds is None or not creds.credentials:
        raise HTTPException(401, detail={"code": "unauthorized", "message": "missing bearer token"})
    try:
        return verify_token(settings, creds.credentials)
    except AuthError as e:
        raise HTTPException(e.status_code, detail={"code": e.code, "message": e.message}) from e


def _require(role: str):
    def dep(
        creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
        settings=Depends(get_settings),
    ) -> Principal:
        principal = _principal(creds, settings)
        if principal.role != role:
            raise HTTPException(
                403, detail={"code": "forbidden", "message": f"{role} role required"}
            )
        return principal

    return dep


require_merchant = _require("merchant")
require_operator = _require("operator")
