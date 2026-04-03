from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.permissions import Permission
from app.db.session import get_db_session
from app.models.user import User
from app.models.videogame import Videogame
from app.schemas.videogame import (
    VideogameCreateRequest,
    VideogameListResponse,
    VideogameResponse,
    VideogameUpdateRequest,
)

router = APIRouter(
    prefix="/videogames",
    tags=["videogames"],
)


@router.post("", response_model=VideogameResponse, status_code=status.HTTP_201_CREATED)
async def create_videogame(
    payload: VideogameCreateRequest,
    db_session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission(Permission.VIDEOGAME_WRITE)),
) -> VideogameResponse:
    videogame = Videogame(**payload.model_dump())
    db_session.add(videogame)
    await db_session.commit()
    await db_session.refresh(videogame)
    return VideogameResponse.model_validate(videogame)


@router.get("", response_model=VideogameListResponse, status_code=status.HTTP_200_OK)
async def list_videogames(
    db_session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission(Permission.VIDEOGAME_READ)),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    genre: str | None = Query(default=None, min_length=1, max_length=100),
    platform: str | None = Query(default=None, min_length=1, max_length=100),
) -> VideogameListResponse:
    filters: list[object] = []
    if genre is not None:
        filters.append(Videogame.genre == genre)
    if platform is not None:
        filters.append(Videogame.platform == platform)

    count_query = select(func.count(Videogame.id))
    items_query = select(Videogame).order_by(Videogame.id.desc()).offset(offset).limit(limit)

    if filters:
        count_query = count_query.where(*filters)
        items_query = items_query.where(*filters)

    total = await db_session.scalar(count_query) or 0
    videogames = (await db_session.scalars(items_query)).all()
    return VideogameListResponse(
        total=total,
        items=[VideogameResponse.model_validate(videogame) for videogame in videogames],
    )


@router.get("/{videogame_id}", response_model=VideogameResponse, status_code=status.HTTP_200_OK)
async def get_videogame(
    videogame_id: int,
    db_session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission(Permission.VIDEOGAME_READ)),
) -> VideogameResponse:
    videogame = await db_session.get(Videogame, videogame_id)
    if videogame is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Videogame not found")
    return VideogameResponse.model_validate(videogame)


@router.patch("/{videogame_id}", response_model=VideogameResponse, status_code=status.HTTP_200_OK)
async def update_videogame(
    videogame_id: int,
    payload: VideogameUpdateRequest,
    db_session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission(Permission.VIDEOGAME_WRITE)),
) -> VideogameResponse:
    videogame = await db_session.get(Videogame, videogame_id)
    if videogame is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Videogame not found")

    update_payload = payload.model_dump(exclude_unset=True)
    if not update_payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    for field_name, field_value in update_payload.items():
        setattr(videogame, field_name, field_value)

    await db_session.commit()
    await db_session.refresh(videogame)
    return VideogameResponse.model_validate(videogame)


@router.delete("/{videogame_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_videogame(
    videogame_id: int,
    db_session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission(Permission.VIDEOGAME_WRITE)),
) -> None:
    videogame = await db_session.get(Videogame, videogame_id)
    if videogame is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Videogame not found")

    await db_session.delete(videogame)
    await db_session.commit()
