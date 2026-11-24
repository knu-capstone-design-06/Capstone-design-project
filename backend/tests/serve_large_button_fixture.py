"""Serve a local frontend build with real in-memory orders and test support responses."""

import argparse
import json
import re
from pathlib import Path

import uvicorn
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.common.config.settings import Settings
from app.infrastructure.external.ai_client import get_ai_engine_client
from app.infrastructure.external.ai_schemas import AiHealthResponse, AnalyzeRequest, AnalyzeResponse
from app.main import create_app
from app.modules.ordering.exceptions import OrderingError
from app.modules.ordering.router import get_ordering_service


FEATURE_PATH = re.compile(r"/api/v1/sessions/([^/]+)/features")


class FixtureAi:
    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        return AnalyzeResponse(
            session_id=request.session_id, measurable=False, model_version="large-button-fixture",
        )

    async def health(self) -> AiHealthResponse:
        return AiHealthResponse(status="ok", service="ai-engine")


def create_fixture_app(frontend_dist: Path):
    app = create_app(Settings(
        _env_file=None, database_url=None, openai_api_key=None, voice_execute_tools=False,
        jev_api_key=None, jev_stages="off",
    ))
    app.dependency_overrides[get_ai_engine_client] = FixtureAi

    @app.middleware("http")
    async def offer_large_button(request: Request, call_next):
        # Match the /backend proxy used by the frontend's production build.
        path = request.scope["path"]
        if path.startswith("/backend/"):
            request.scope["path"] = path.removeprefix("/backend")
        match = FEATURE_PATH.fullmatch(request.url.path)
        if request.method != "POST" or match is None:
            return await call_next(request)

        await request.body()
        response = await call_next(request)
        if response.status_code != 200 or (await request.json())["screen_id"] != "menu":
            return response

        ordering = get_ordering_service(request)
        try:
            cart = await run_in_threadpool(ordering.cart, match.group(1))
        except OrderingError as exc:
            if exc.code == "session_expired":
                return JSONResponse({"detail": exc.code}, status_code=410)
            raise
        if not cart.items:
            return response

        payload = json.loads(b"".join([chunk async for chunk in response.body_iterator]))
        payload["support"] = {
            "preset": "large_button",
            "requires_confirmation": True,
            "decided_by": "jev",
        }
        return JSONResponse(payload)

    app.mount("/", StaticFiles(directory=frontend_dist, html=True))
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frontend_dist", type=Path, help="Path to a built frontend/dist directory")
    parser.add_argument("--port", type=int, default=18097)
    args = parser.parse_args()
    if not (args.frontend_dist / "index.html").is_file():
        parser.error("frontend_dist must contain index.html from npm run build")
    uvicorn.run(create_fixture_app(args.frontend_dist), host="127.0.0.1", port=args.port)
