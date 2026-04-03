from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hasher.verify(password, hashed_password)


def create_token(
    *,
    subject: str,
    expires_delta: timedelta,
    token_type: str,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    expires_at = datetime.now(UTC) + expires_delta
    payload: dict[str, Any] = {"sub": subject, "exp": expires_at, "type": token_type}
    if additional_claims is not None:
        payload.update(additional_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(*, subject: str, token_version: int) -> str:
    return create_token(
        subject=subject,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        token_type="access",
        additional_claims={"token_version": token_version},
    )


def create_refresh_token(*, subject: str, token_version: int) -> str:
    return create_token(
        subject=subject,
        expires_delta=timedelta(minutes=settings.refresh_token_expire_minutes),
        token_type="refresh",
        additional_claims={"token_version": token_version},
    )


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc


def create_csrf_token() -> str:
    return create_token(
        subject="csrf",
        expires_delta=timedelta(minutes=settings.refresh_token_expire_minutes),
        token_type="csrf",
    )


def csrf_token_is_valid(token: str | None) -> bool:
    if token is None or not str(token).strip():
        return False
    try:
        payload = decode_token(str(token).strip())
    except ValueError:
        return False
    return payload.get("type") == "csrf" and payload.get("sub") == "csrf"
