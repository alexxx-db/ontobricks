from fastapi import APIRouter, Request

from backend.ports.identity import IdentityPort


def router(identity: IdentityPort) -> APIRouter:
    api = APIRouter(prefix="/api/me")

    @api.get("")
    def me(request: Request) -> dict[str, str]:
        return {"email": identity.actor(request.headers).email}

    return api
