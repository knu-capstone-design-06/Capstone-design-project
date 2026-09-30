from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.modules.analyze.router import router as analyze_router


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["ai-server"] = "ai-server"


def create_app() -> FastAPI:
    application = FastAPI(title="Capstone AI Server", version="0.1.0")

    @application.get(
        "/health",
        response_model=HealthResponse,
        tags=["health"],
        operation_id="getAiHealth",
    )
    def health() -> HealthResponse:
        """Process liveness only; does not check that a model is loaded."""
        return HealthResponse()

    application.include_router(analyze_router)
    return application


app = create_app()
