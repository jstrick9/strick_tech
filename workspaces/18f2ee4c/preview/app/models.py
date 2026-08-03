"""Pydantic request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    """Payload for creating an item."""

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    done: bool = False


class ItemUpdate(BaseModel):
    """Partial update — every field is optional."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    done: bool | None = None


class Item(ItemCreate):
    """An item as returned by the API."""

    id: int
