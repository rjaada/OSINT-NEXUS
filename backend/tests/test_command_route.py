"""Focused access and composition tests for the Nexus Command route."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routes_command


class TestCommandSnapshotRoute(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(routes_command.router)
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_viewer_is_rejected_by_analyst_dependency(self):
        def reject(_request):
            raise HTTPException(status_code=403, detail="Analyst or admin role required")

        fake_main = SimpleNamespace(require_analyst_or_admin=reject)
        with patch.dict(sys.modules, {"main": fake_main}):
            response = self.client.get("/api/v2/command/snapshot")
        self.assertEqual(response.status_code, 403)

    def test_referenced_evidence_is_loaded_beyond_recent_window(self):
        recent = {"id": "recent", "source": "feed", "confidence_score": 70}
        old = {"id": "old-evidence", "source": "archive", "confidence_score": 85}
        fake_main = SimpleNamespace(
            fetch_recent_v2_events_pg=lambda limit: [recent],
            events_history=[],
        )
        hypotheses = [{"id": "h1", "evidence_ids": ["old-evidence"]}]
        with (
            patch.dict(sys.modules, {"main": fake_main}),
            patch.object(routes_command, "_fetch_hypotheses", return_value=hypotheses),
            patch.object(routes_command, "_fetch_system", return_value={}),
            patch.object(routes_command, "_fetch_sitrep", return_value={}),
            patch.object(routes_command, "_fetch_escalation", return_value={}),
            patch.object(routes_command, "_fetch_events_by_ids", return_value=[old], create=True) as fetch_ids,
        ):
            inputs = routes_command._collect_command_inputs()
        self.assertEqual({event["id"] for event in inputs["events"]}, {"recent", "old-evidence"})
        fetch_ids.assert_called_once_with(fake_main, ["old-evidence"])

    def test_authenticated_route_builds_one_snapshot(self):
        self.app.dependency_overrides[routes_command._require_analyst_or_admin] = lambda: {
            "username": "analyst", "role": "analyst"
        }
        inputs = {
            "events": [{"id": "critical", "type": "CRITICAL", "source": "wire", "confidence_score": 80}],
            "hypotheses": [],
            "system": {"postgres": {"connected": True}},
            "sitrep": {"summary": "Assessment"},
            "escalation": {"theaters": []},
            "collection_errors": [],
        }
        with patch.object(routes_command, "_collect_command_inputs", return_value=inputs):
            response = self.client.get("/api/v2/command/snapshot")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["priority_events"][0]["id"], "critical")
        self.assertTrue(body["integrity"]["evidence_backed"])
        self.assertEqual(body["integrity"]["collection_errors"], [])


if __name__ == "__main__":
    unittest.main()
