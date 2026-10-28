"""FastAPI application factory. Run: `uv run uvicorn trafiqon.api.app:app --reload`."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trafiqon import __version__
from trafiqon.api.errors import install_error_handlers
from trafiqon.api.routes import router

DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def create_app(cors_origins: list[str] | None = None) -> FastAPI:
    if cors_origins is None:
        raw = os.environ.get("TRAFIQON_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
        cors_origins = [o.strip() for o in raw.split(",") if o.strip()]
    app = FastAPI(title="TRAFIQON API", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    install_error_handlers(app)
    app.include_router(router)
    logging.getLogger("trafiqon.api").info("TRAFIQON API %s, CORS %s", __version__, cors_origins)
    return app


app = create_app()
