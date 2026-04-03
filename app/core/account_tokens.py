from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.db.datetime_utils import utc_now
from app.models.user import User
from app.models.user_account_token import AccountTokenPurpose, UserAccountToken


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def mint_account_token(
    db_session: AsyncSession,
    *,
    user_id: int,
    purpose: AccountTokenPurpose,
    expire_minutes: int,
) -> str:
    await db_session.execute(
        delete(UserAccountToken).where(
            UserAccountToken.user_id == user_id,
            UserAccountToken.purpose == purpose.value,
        )
    )
    suffix = secrets.token_urlsafe(32)
    expires_at = utc_now() + timedelta(minutes=expire_minutes)
    row = UserAccountToken(
        user_id=user_id,
        purpose=purpose.value,
        token_hash=hash_password(suffix),
        expires_at=expires_at,
    )
    db_session.add(row)
    await db_session.flush()
    return f"{row.id}:{suffix}"


async def consume_account_token(
    db_session: AsyncSession,
    *,
    raw_token: str,
    purpose: AccountTokenPurpose,
) -> User | None:
    parts = raw_token.strip().split(":", 1)
    if len(parts) != 2:
        return None
    tid_s, suffix = parts
    if not tid_s.isdigit():
        return None
    row = await db_session.get(UserAccountToken, int(tid_s))
    if row is None or row.purpose != purpose.value or row.used_at is not None:
        return None
    if _as_utc(row.expires_at) < utc_now():
        return None
    if not verify_password(suffix, row.token_hash):
        return None
    row.used_at = utc_now()
    return await db_session.get(User, row.user_id)
