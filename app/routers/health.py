from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.db.session import get_db_session

router = APIRouter(tags=["health"])


def _app_settings(request: Request) -> Settings:
    s = getattr(request.app.state, "settings", None)
    return s if isinstance(s, Settings) else default_settings


@router.get("/health", status_code=status.HTTP_200_OK)
async def liveness(request: Request) -> dict[str, str]:
    s = _app_settings(request)
    return {
        "status": "ok",
        "app": s.app_name,
        "version": s.app_version,
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    try:
        await db_session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None
    s = _app_settings(request)
    return {
        "status": "ok",
        "app": s.app_name,
        "version": s.app_version,
        "database": "up",
    }
