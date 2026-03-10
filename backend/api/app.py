from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.api.routes.health import router as health_router
from backend.api.routes.profile import router as profile_router
from backend.api.routes.session_ws import router as session_ws_router
from backend.api.routes.vision import router as vision_router
from backend.core.constants import SERVICE_NAME
from backend.core.settings import Settings
from backend.core.runtime import AppRuntime


class VisionPayloadLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, *, max_request_bytes: int) -> None:
        super().__init__(app)
        self._max_request_bytes = max_request_bytes

    async def dispatch(self, request, call_next):  # type: ignore[override]
        if (
            request.method.upper() == "POST"
            and request.url.path == "/vision/frame"
            and self._max_request_bytes > 0
        ):
            raw_content_length = request.headers.get("content-length")
            if raw_content_length is not None:
                try:
                    content_length = int(raw_content_length)
                except ValueError:
                    content_length = None
                else:
                    if content_length > self._max_request_bytes:
                        return JSONResponse(
                            status_code=413,
                            content={
                                "detail": (
                                    "Vision request exceeds "
                                    f"BACKEND_MAX_VISION_REQUEST_BYTES={self._max_request_bytes}"
                                )
                            },
                        )
        return await call_next(request)


def _make_lifespan(settings: Settings) -> Callable[[FastAPI], AsyncIterator[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = AppRuntime.from_settings(settings)
        await runtime.startup()
        app.state.runtime = runtime
        try:
            yield
        finally:
            await runtime.shutdown()

    return lifespan


def create_app() -> FastAPI:
    settings = Settings.from_env()
    app = FastAPI(title=SERVICE_NAME, lifespan=_make_lifespan(settings))

    allow_all = settings.cors_origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        VisionPayloadLimitMiddleware,
        max_request_bytes=settings.backend_max_vision_request_bytes,
    )

    app.include_router(health_router)
    app.include_router(profile_router)
    app.include_router(vision_router)
    app.include_router(session_ws_router)
    return app


app = create_app()
