"""Run via check-local.ps1 inside the backend container; no external services."""
import asyncio
import httpx
from app.common.config.settings import Settings
from app.infrastructure.external.ai_client import AiServerClient
from app.infrastructure.external.ai_schemas import AnalyzeRequest


async def main():
    settings = Settings()
    async with httpx.AsyncClient(base_url=settings.ai_server_url, trust_env=False) as http:
        ai = AiServerClient(http, settings.ai_server_timeout_seconds)
        health = await ai.health()
        assert health is not None and health.service == "ai-server", "AI health failed"
        payload = {
            "session_id": "local-smoke-test", "screen_id": "menu_list",
            "window_start": "2026-10-01T10:00:00Z",
            "window_end": "2026-10-01T10:00:03Z",
            "touch": {"tap_count": 6, "miss_tap_count": 3,
                      "repeat_tap_count": 2, "back_count": 0, "dwell_ms": 3000},
        }
        result = await ai.analyze(AnalyzeRequest.model_validate(payload))
        assert result is not None and result.measurable and result.states, "Analysis failed"
        assert result.model_version == "dummy-0.1", "Update this test for the real model"
        assert set(result.states) == {"normal", "touch_difficulty", "navigation_difficulty",
                                      "visual_difficulty", "hesitation"}
        assert all(0 <= value <= 1 for value in result.states.values())
        payload["touch"] = {"tap_count": 0, "miss_tap_count": 0,
                            "repeat_tap_count": 0, "back_count": 0, "dwell_ms": 3000}
        result = await ai.analyze(AnalyzeRequest.model_validate(payload))
        assert result is not None and not result.measurable and result.states is None
        invalid = await http.post("/v1/analyze", json={}, timeout=2)
        assert invalid.status_code == 422, invalid.status_code
        print("PASS: backend -> AI health, analysis, unmeasurable, 422")


asyncio.run(main())
