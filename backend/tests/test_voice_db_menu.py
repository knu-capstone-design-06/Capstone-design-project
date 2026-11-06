"""Regression for a DB catalog outage during background voice processing."""

import asyncio
import unittest
from uuid import uuid4

from app.main import _database_voice_menu
from app.modules.ordering.repository import OrderingRepository
from app.modules.sessions.repository import SessionRepository
from app.modules.voice.interpreter import StubVoiceInterpreter
from app.modules.voice.repository import VoiceRepository
from app.modules.voice.schemas import VoiceRequestCreate
from app.modules.voice.service import VoiceService


class FailingCatalog:
    def products(self):
        raise ConnectionError("catalog unavailable")


class VoiceDatabaseMenuTests(unittest.TestCase):
    def test_catalog_failure_finishes_request_and_allows_next_attempt(self):
        sessions = SessionRepository()
        session_id = sessions.create().session_id
        service = VoiceService(
            sessions.exists, VoiceRepository(), StubVoiceInterpreter(),
            lambda: _database_voice_menu(FailingCatalog()), OrderingRepository(),
        )
        request = VoiceRequestCreate(text="아메리카노 하나", alternatives=[], screen_id="menu_list")

        first, created = service.accept(session_id, uuid4(), request)
        self.assertTrue(created)
        asyncio.run(service.process(session_id, first.request_id, request))
        result = service.get(session_id, first.request_id)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error.code, "ai_unavailable")

        second, created = service.accept(session_id, uuid4(), request)
        self.assertTrue(created)
        self.assertNotEqual(second.request_id, first.request_id)


if __name__ == "__main__":
    unittest.main()
