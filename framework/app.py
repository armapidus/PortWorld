from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config.settings import SETTINGS
from backend.routers.config import router as config_router
from backend.routers.debug import router as debug_router
from backend.routers.health import router as health_router
from backend.routers.pipeline import router as pipeline_router
from backend.routers.runs import router as runs_router
from backend.routers.ws import router as ws_router
from backend.services.run_log import RUN_LOG


@asynccontextmanager
async def lifespan(app: FastAPI):
    RUN_LOG.open()
    yield
    RUN_LOG.close()


app = FastAPI(title=SETTINGS.app_name, version=SETTINGS.app_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.cors_origins,
    allow_credentials="*" not in SETTINGS.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(config_router)
app.include_router(pipeline_router)
app.include_router(debug_router)
app.include_router(runs_router)
app.include_router(ws_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8082")),
        reload=os.getenv("RELOAD", "false").strip().lower() in {"1", "true", "yes", "on"},
    )
