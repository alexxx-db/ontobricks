from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.features.items import sql
from backend.ports.app_state import AppStatePort
from backend.ports.identity import IdentityPort


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def router(state: AppStatePort, identity: IdentityPort) -> APIRouter:
    api = APIRouter(prefix="/api/items")

    @api.get("")
    def list_items(request: Request) -> list[dict[str, object]]:
        caller = identity.user_token(request.headers)
        return state.fetch_all(caller, sql.LIST_ITEMS, {"limit": 100})

    @api.post("", status_code=201)
    def create_item(item: ItemCreate, request: Request) -> dict[str, object]:
        caller = identity.user_token(request.headers)
        actor = identity.actor(request.headers)
        return state.fetch_one(caller, sql.CREATE_ITEM, {"name": item.name, "created_by": actor.email})

    return api
