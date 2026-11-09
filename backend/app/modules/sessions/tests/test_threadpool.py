"""Synchronous DB checks must not run on the async feature endpoint's loop."""

import asyncio
import threading
import unittest

from app.modules.sessions.schemas import FeatureWindowRequest
from app.modules.sessions.service import SessionService


class TrackingSessions:
    def __init__(self):
        self.threads = []

    def exists(self, session_id):
        self.threads.append(threading.get_ident())
        return True


class TrackingOrdering:
    def __init__(self):
        self.threads = []

    def is_completed(self, session_id):
        self.threads.append(threading.get_ident())
        return False


class NoAiResult:
    async def analyze(self, request):
        return None


class FeatureThreadpoolTests(unittest.TestCase):
    def test_database_checks_run_outside_event_loop(self):
        sessions = TrackingSessions()
        ordering = TrackingOrdering()
        service = SessionService(sessions, ordering)
        window = FeatureWindowRequest.model_validate({
            "screen_id": "menu_list",
            "window_start": "2026-10-01T10:00:00Z",
            "window_end": "2026-10-01T10:00:03Z",
            "touch": {"tap_count": 1, "miss_tap_count": 0, "repeat_tap_count": 0,
                      "back_count": 0, "dwell_ms": 3000},
        })

        async def run():
            loop_thread = threading.get_ident()
            result = await service.analyze("session-1", window, NoAiResult())
            return loop_thread, result

        loop_thread, result = asyncio.run(run())
        self.assertFalse(result.ai_available)
        self.assertEqual(len(sessions.threads), 1)
        self.assertEqual(len(ordering.threads), 2)
        self.assertTrue(all(t != loop_thread for t in sessions.threads + ordering.threads))


if __name__ == "__main__":
    unittest.main()
