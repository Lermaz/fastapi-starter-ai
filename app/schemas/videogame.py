from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class VideogameSort(StrEnum):
    id_desc = "id_desc"
    id_asc = "id_asc"
    price_desc = "price_desc"
    price_asc = "price_asc"
    title_asc = "title_asc"
    title_desc = "title_desc"


class VideogameCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    genre: str = Field(min_length=1, max_length=100)
    platform: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    stock: int = Field(ge=0)
    release_date: date | None = None


class VideogameUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    genre: str | None = Field(default=None, min_length=1, max_length=100)
    platform: str | None = Field(default=None, min_length=1, max_length=100)
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    stock: int | None = Field(default=None, ge=0)
    release_date: date | None = None


class VideogameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    genre: str
    platform: str
    price: Decimal
    stock: int
    release_date: date | None
    created_at: datetime
    updated_at: datetime


class VideogameListResponse(BaseModel):
    total: int
    items: list[VideogameResponse]
    next_cursor: str | None = None
