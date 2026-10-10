from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.common.config.settings import Settings, get_settings
from app.infrastructure.external.ai_client import AiServerClient
from app.modules.connectivity.router import router as connectivity_router
from app.modules.sessions.repository import SessionRepository
from app.modules.sessions.router import router as sessions_router
from app.modules.sessions.service import SessionService


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["backend"] = "backend"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(
            base_url=settings.ai_server_url,
            timeout=settings.ai_server_timeout_seconds,
            trust_env=False,
            follow_redirects=False,
        ) as http:
            app.state.ai_server_client = AiServerClient(
                http, settings.ai_server_timeout_seconds
            )
            app.state.session_service = SessionService(SessionRepository())
            try:
                yield
            finally:
                del app.state.ai_server_client
                del app.state.session_service

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Process liveness only; does not verify DB or AI connectivity."""
        return HealthResponse()

    application.include_router(connectivity_router)
    application.include_router(sessions_router)
    return application


app = create_app()
