from fastapi import APIRouter


def router() -> APIRouter:
    api = APIRouter()

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return api
