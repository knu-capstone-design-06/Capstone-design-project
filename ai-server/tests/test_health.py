import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class HealthTests(unittest.TestCase):
    def test_health_matches_contract_example(self):
        with TestClient(create_app()) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "ai-server"})

    def test_operation_ids_match_contract(self):
        paths = create_app().openapi()["paths"]
        self.assertEqual(paths["/health"]["get"]["operationId"], "getAiHealth")
        self.assertEqual(paths["/v1/analyze"]["post"]["operationId"], "analyzeWindow")


if __name__ == "__main__":
    unittest.main()
