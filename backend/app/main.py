from contextlib import AsyncExitStack, asynccontextmanager
from typing import Literal

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.common.config.settings import Settings, get_settings
from app.infrastructure.external.ai_client import AiEngineClient
from app.infrastructure.external.jev_client import JevClient, create_jev_http
from app.infrastructure.external.openai_client import OpenAiClient, create_openai_http
from app.modules.connectivity.router import router as connectivity_router
from app.modules.decision.jev_questions import build_stages
from app.modules.decision.repository import DecisionRepository
from app.modules.decision.schemas import PILOT_PARAMS
from app.modules.decision.service import DecisionService
from app.modules.ordering.catalog import PRODUCTS
from app.modules.ordering.repository import OrderingRepository
from app.modules.ordering.router import router as ordering_router
from app.modules.ordering.service import OrderingService
from app.modules.sessions.repository import SessionRepository
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
            # Jev answers decisions in shadow mode; nothing reaches the screen until thresholds
            # are agreed (docs/Jev-Integration.md). No key: the rule table still runs, Jev is not asked.
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
            app.state.decision_repository = DecisionRepository()
            # JEV_STAGES picks the experiment arm: off = rule table alone, or 1..n Jev stages.
            app.state.decision_service = DecisionService(
                app.state.decision_repository, PILOT_PARAMS, app.state.jev_client,
                stages=build_stages(settings.jev_stages),
            )
            session_repository = SessionRepository()
            app.state.session_service = SessionService(
                session_repository, app.state.ordering_repository, decision=app.state.decision_service
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
                menu_provider=lambda: menu_from_products(PRODUCTS),
                ordering=app.state.ordering_repository,
                executor=executor,
            )
            try:
                yield
            finally:
                del app.state.ai_engine_client
                del app.state.session_service
                del app.state.voice_service
                await app.state.decision_service.drain()
                del app.state.decision_service
                del app.state.decision_repository
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
