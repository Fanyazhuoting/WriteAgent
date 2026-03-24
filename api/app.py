"""FastAPI application factory."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.routes import novel, entities, audit, admin
from api.websocket import ws_stream

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "ui", "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm ChromaDB so the embedding model is downloaded before the first request."""
    import logging
    logger = logging.getLogger("writeagent")
    logger.info("Pre-warming ChromaDB (downloading embedding model if needed)...")
    from memory.chroma_client import get_client
    client = get_client()
    # Trigger a dummy query on each collection to force model initialisation
    for col_name in ("world_entities", "scene_archive", "world_rules"):
        col = client.get_collection(col_name)
        try:
            col.query(query_texts=["warmup"], n_results=1)
        except Exception:
            pass  # empty collection — that's fine
    logger.info("ChromaDB ready.")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="WriteAgent API",
        description="Multi-agent novel writing system",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # REST routers
    app.include_router(novel.router, prefix="/api/v1")
    app.include_router(entities.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")

    # Serve static UI files
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    # WebSocket
    @app.websocket("/ws/{novel_id}/stream")
    async def websocket_endpoint(websocket: WebSocket, novel_id: str):
        await ws_stream(websocket, novel_id)

    @app.get("/")
    def root():
        return FileResponse(os.path.join(_STATIC_DIR, "index.html"))

    return app


app = create_app()
