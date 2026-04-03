from __future__ import annotations

import base64
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, literal, or_, select
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
    VideogameSort,
    VideogameUpdateRequest,
)

router = APIRouter(
    prefix="/videogames",
    tags=["videogames"],
)


def _encode_cursor(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(raw: str) -> dict:
    try:
        pad = "=" * (-len(raw) % 4)
        data = base64.urlsafe_b64decode(raw + pad)
        return json.loads(data.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor",
        ) from exc


def _order_by_tuple(sort: VideogameSort) -> tuple[object, ...]:
    ltitle = func.lower(Videogame.title)
    if sort == VideogameSort.id_desc:
        return (Videogame.id.desc(),)
    if sort == VideogameSort.id_asc:
        return (Videogame.id.asc(),)
    if sort == VideogameSort.price_desc:
        return (Videogame.price.desc(), Videogame.id.desc())
    if sort == VideogameSort.price_asc:
        return (Videogame.price.asc(), Videogame.id.asc())
    if sort == VideogameSort.title_asc:
        return (ltitle.asc(), Videogame.id.asc())
    if sort == VideogameSort.title_desc:
        return (ltitle.desc(), Videogame.id.desc())
    return (Videogame.id.desc(),)


def _cursor_seek_condition(sort: VideogameSort, c: dict) -> object:
    if c.get("s") != sort.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cursor sort mismatch",
        )
    try:
        cid = int(c["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor",
        ) from exc

    if sort == VideogameSort.id_desc:
        return Videogame.id < cid
    if sort == VideogameSort.id_asc:
        return Videogame.id > cid
    if sort in (VideogameSort.price_desc, VideogameSort.price_asc):
        try:
            p = Decimal(str(c["p"]))
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor",
            ) from exc
        if sort == VideogameSort.price_desc:
            return or_(Videogame.price < p, and_(Videogame.price == p, Videogame.id < cid))
        return or_(Videogame.price > p, and_(Videogame.price == p, Videogame.id > cid))
    if sort in (VideogameSort.title_asc, VideogameSort.title_desc):
        try:
            t = str(c["t"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor",
            ) from exc
        lo = func.lower(Videogame.title)
        tl = func.lower(literal(t))
        if sort == VideogameSort.title_asc:
            return or_(lo > tl, and_(lo == tl, Videogame.id > cid))
        return or_(lo < tl, and_(lo == tl, Videogame.id < cid))

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor")


def _row_to_cursor_payload(sort: VideogameSort, row: Videogame) -> dict:
    payload: dict = {"s": sort.value, "id": row.id}
    if sort in (VideogameSort.price_asc, VideogameSort.price_desc):
        payload["p"] = str(row.price)
    if sort in (VideogameSort.title_asc, VideogameSort.title_desc):
        payload["t"] = row.title
    return payload


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
    q: str | None = Query(default=None, min_length=1, max_length=255),
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    sort: VideogameSort = Query(default=VideogameSort.id_desc),
    cursor: str | None = Query(
        default=None,
        description="Opaque token from a previous response. When set, `offset` is ignored.",
    ),
) -> VideogameListResponse:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_price cannot exceed max_price",
        )

    filters: list[object] = []
    if genre is not None:
        filters.append(Videogame.genre == genre)
    if platform is not None:
        filters.append(Videogame.platform == platform)
    if q is not None:
        filters.append(func.lower(Videogame.title).contains(q.lower()))
    if min_price is not None:
        filters.append(Videogame.price >= min_price)
    if max_price is not None:
        filters.append(Videogame.price <= max_price)

    count_query = select(func.count(Videogame.id))
    items_query = select(Videogame)
    if filters:
        count_query = count_query.where(*filters)
        items_query = items_query.where(*filters)

    items_query = items_query.order_by(*_order_by_tuple(sort))

    use_cursor = cursor is not None and str(cursor).strip() != ""
    if use_cursor:
        decoded = _decode_cursor(str(cursor).strip())
        items_query = items_query.where(_cursor_seek_condition(sort, decoded))
        items_query = items_query.limit(limit + 1)
    else:
        items_query = items_query.offset(offset).limit(limit + 1)

    total = await db_session.scalar(count_query) or 0
    rows = (await db_session.scalars(items_query)).all()

    has_more = len(rows) > limit
    page_rows = rows[:limit]

    next_cursor: str | None = None
    if page_rows:
        if has_more:
            next_cursor = _encode_cursor(_row_to_cursor_payload(sort, page_rows[-1]))
        elif not use_cursor and offset + limit < total:
            next_cursor = _encode_cursor(_row_to_cursor_payload(sort, page_rows[-1]))

    return VideogameListResponse(
        total=total,
        items=[VideogameResponse.model_validate(v) for v in page_rows],
        next_cursor=next_cursor,
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


@router.delete(
    "/{videogame_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_videogame(
    videogame_id: int,
    db_session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission(Permission.VIDEOGAME_WRITE)),
) -> Response:
    videogame = await db_session.get(Videogame, videogame_id)
    if videogame is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Videogame not found")

    await db_session.delete(videogame)
    await db_session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
