from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.adapters.forwarded_identity import ForwardedIdentity
from backend.adapters.lakebase import LakebaseAppState
from backend.features.health import route as health
from backend.features.items import route as items
from backend.features.me import route as me
from backend.kernel.errors import Unauthorized
from backend.runtime.config import Config


def unauthorized_as_401(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": str(exc)})


def create_app(config: Config) -> FastAPI:
    state = LakebaseAppState(config.lakebase)
    identity = ForwardedIdentity()

    app = FastAPI(title="Hello Abacus")
    app.add_exception_handler(Unauthorized, unauthorized_as_401)
    app.include_router(health.router())
    app.include_router(items.router(state=state, identity=identity))
    app.include_router(me.router(identity=identity))
    app.mount("/", StaticFiles(directory=config.static_dir, html=True), name="frontend")
    return app
