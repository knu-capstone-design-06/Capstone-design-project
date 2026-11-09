from contextlib import AsyncExitStack, asynccontextmanager
import logging
from typing import Literal

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.common.config.settings import Settings, get_settings
from app.infrastructure.database.postgres import PostgresDatabase
from app.infrastructure.external.ai_client import AiEngineClient
from app.infrastructure.external.jev_client import JevClient, create_jev_http
from app.infrastructure.external.openai_client import OpenAiClient, create_openai_http
from app.modules.connectivity.router import router as connectivity_router
from app.modules.ordering.catalog import PRODUCTS
from app.modules.ordering.repository import OrderingRepository
from app.modules.ordering.postgres_repository import PostgresOrderingRepository
from app.modules.ordering.router import router as ordering_router
from app.modules.ordering.service import OrderingService
from app.modules.sessions.repository import SessionRepository
from app.modules.sessions.postgres_repository import PostgresSessionRepository
from app.modules.sessions.router import router as sessions_router
from app.modules.sessions.service import SessionService
from app.modules.voice.executor import OrderingCartExecutor
from app.modules.voice.interpreter import build_voice_interpreter
from app.modules.voice.repository import VoiceRepository
from app.modules.voice.router import router as voice_router
from app.modules.voice.service import VoiceService, menu_from_products


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["backend"] = "backend"


def _database_voice_menu(repository: PostgresOrderingRepository):
    """A catalog outage fails the voice request instead of stranding it as processing."""
    try:
        return menu_from_products(repository.products())
    except Exception:
        # The voice service already turns an empty menu into a terminal failed
        # response. Do not log the exception: connection errors can contain URLs.
        logging.getLogger(__name__).warning("Voice menu unavailable")
        return []


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(
            base_url=settings.ai_engine_url,
            timeout=settings.ai_engine_timeout_seconds,
            trust_env=False,
            follow_redirects=False,
        ) as http, AsyncExitStack() as stack:
            app.state.ai_engine_client = AiEngineClient(
                http, settings.ai_engine_timeout_seconds
            )
            if settings.database_url is not None:
                database = PostgresDatabase(settings.database_url.get_secret_value())
                database.check()
                app.state.ordering_repository = PostgresOrderingRepository(database)
                session_repository = PostgresSessionRepository(database)
            else:
                app.state.ordering_repository = OrderingRepository()
                session_repository = SessionRepository()
            app.state.session_service = SessionService(
                session_repository, app.state.ordering_repository
            )
            openai = None
            if settings.openai_api_key is not None:
                openai_http = await stack.enter_async_context(create_openai_http(
                    settings.openai_api_key.get_secret_value(),
                    settings.openai_timeout_seconds,
                ))
                openai = OpenAiClient(
                    openai_http, settings.openai_model, settings.openai_timeout_seconds
                )
            # Jev answers decisions built by ai-engine; nothing asks it until the
            # analysis result carries a question (docs/Jev-Integration.md, step 0).
            app.state.jev_client = None
            if settings.jev_api_key is not None:
                jev_http = await stack.enter_async_context(create_jev_http(
                    settings.jev_api_key.get_secret_value(),
                    settings.jev_api_url,
                    settings.jev_timeout_seconds,
                ))
                app.state.jev_client = JevClient(
                    jev_http, settings.jev_model, settings.jev_timeout_seconds
                )
            executor = None
            if settings.voice_execute_tools:
                # Voice changes the cart through the same service as touch ordering.
                executor = OrderingCartExecutor(
                    OrderingService(session_repository.exists, app.state.ordering_repository),
                    app.state.ordering_repository,
                )
            app.state.voice_service = VoiceService(
                session_repository.exists, VoiceRepository(),
                build_voice_interpreter(openai),
                # Same demo catalog the ordering API sells.
                menu_provider=lambda: (
                    _database_voice_menu(app.state.ordering_repository)
                    if settings.database_url is not None else menu_from_products(PRODUCTS)
                ),
                ordering=app.state.ordering_repository,
                executor=executor,
            )
            try:
                yield
            finally:
                del app.state.ai_engine_client
                del app.state.session_service
                del app.state.voice_service
                del app.state.jev_client

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    application.state.ordering_repository = OrderingRepository()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Process liveness only; does not verify DB or AI connectivity."""
        return HealthResponse()

    application.include_router(ordering_router)
    application.include_router(connectivity_router)
    application.include_router(sessions_router)
    application.include_router(voice_router)
    return application


app = create_app()
