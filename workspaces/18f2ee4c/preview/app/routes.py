"""CRUD endpoints backed by a simple in-memory store.

Swap `_STORE` for a real database when you outgrow this — the route handlers
and schemas stay the same.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from .models import Item, ItemCreate, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])

_STORE: dict[int, Item] = {}
_NEXT_ID = 1


@router.get("", response_model=list[Item])
def list_items(done: bool | None = None) -> list[Item]:
    """List items, optionally filtered by completion state."""
    items = list(_STORE.values())
    if done is not None:
        items = [i for i in items if i.done is done]
    return items


@router.post("", response_model=Item, status_code=201)
def create_item(payload: ItemCreate) -> Item:
    """Create an item."""
    global _NEXT_ID
    item = Item(id=_NEXT_ID, **payload.model_dump())
    _STORE[item.id] = item
    _NEXT_ID += 1
    return item


@router.get("/{item_id}", response_model=Item)
def get_item(item_id: int) -> Item:
    """Fetch a single item, or 404."""
    item = _STORE.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return item


@router.patch("/{item_id}", response_model=Item)
def update_item(item_id: int, payload: ItemUpdate) -> Item:
    """Apply a partial update."""
    item = _STORE.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    updated = item.model_copy(update=payload.model_dump(exclude_unset=True))
    _STORE[item_id] = updated
    return updated


@router.delete("/{item_id}", status_code=204, response_class=Response)
def delete_item(item_id: int) -> Response:
    """Delete an item, or 404."""
    if _STORE.pop(item_id, None) is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return Response(status_code=204)
