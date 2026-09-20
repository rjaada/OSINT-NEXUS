"""Regressions found during the September code review; no live services required."""
import asyncio
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
import routes_v2
import routes_auth
import auth_security


class RuntimeRouteTests(unittest.TestCase):
    def test_dashboard_reads_ingestion_state_not_legacy_state(self):
        fake = SimpleNamespace(
            require_analyst_or_admin=lambda request: {}, _watchdog_check=lambda: [],
            postgres_status=lambda: {"connected": True}, _start_time=time.time(),
            metrics={"adsblol_polls": 27}, events_history=[{"id": "real"}], events_buffer=[],
            _media_jobs=asyncio.Queue(), _media_job_state={}, seen_articles={"one"},
            seen_telegram_posts=set(), utc_now_iso=lambda: "now",
            ENABLE_ADSBLOL=True, ADSBLOL_API_URL="https://example.test",
            ENABLE_AISSTREAM=True, AISSTREAM_API_KEY="", ENABLE_FIRMS=True,
            FIRMS_MAP_KEY="configured", FIRMS_BBOX="bbox",
        )
        with patch.dict(sys.modules, {"main": fake}):
            result = asyncio.run(routes_v2.v2_ops_dashboard(None))
        self.assertEqual(result["metrics"]["adsblol_polls"], 27)
        self.assertEqual(result["queues"]["events_history"], 1)
        self.assertTrue(result["connectors"]["firms"]["configured"])
        self.assertFalse(result["connectors"]["ais"]["configured"])

    def test_graph_reads_live_graph_store(self):
        graph = {"nodes": [{"id": "live"}], "edges": []}
        store = SimpleNamespace(status=lambda: {"connected": True}, get_graph_data=lambda limit: graph)
        fake = SimpleNamespace(require_analyst_or_admin=lambda request: {}, _graph_store=store, utc_now_iso=lambda: "now")
        with patch.dict(sys.modules, {"main": fake}):
            result = asyncio.run(routes_v2.v2_event_graph(None))
        self.assertEqual(result["nodes"], graph["nodes"])

    def test_session_outage_is_not_reported_as_logout(self):
        def unavailable(request):
            raise HTTPException(503, "Database unavailable")
        with patch.dict(sys.modules, {"main": SimpleNamespace(auth_user_from_request=unavailable)}):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(routes_auth.auth_session(None))
        self.assertEqual(error.exception.status_code, 503)

    def test_press_brief_can_use_local_fallback_without_groq_key(self):
        fake = SimpleNamespace(require_analyst_or_admin=lambda request: {}, utc_now_iso=lambda: "now")
        with patch.dict(sys.modules, {"main": fake}), patch('groq_client.groq_available', return_value=False), patch('groq_client.chat', return_value='{"headline":"Local analysis"}') as chat:
            result = asyncio.run(routes_v2.v2_ai_press_brief({"text": "Test transcript"}, None))
        self.assertEqual(result["analysis"]["headline"], "Local analysis")
        chat.assert_called_once()


class SessionIdentityTests(unittest.TestCase):
    def test_simultaneous_logins_have_independent_session_ids(self):
        expires = int(time.time()) + 3600
        first = auth_security.auth_sign("test-secret", "analyst", "analyst", expires)
        second = auth_security.auth_sign("test-secret", "analyst", "analyst", expires)
        self.assertNotEqual(first, second)
        self.assertEqual(auth_security.auth_verify("test-secret", first)["username"], "analyst")
        self.assertIsNone(auth_security.auth_verify("wrong-secret", first))

    def test_legacy_signed_tokens_remain_verifiable(self):
        import base64, hashlib, hmac
        payload = f"analyst|analyst|{int(time.time()) + 3600}"
        sig = hmac.new(b"test-secret", payload.encode(), hashlib.sha256).hexdigest()
        token = base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()
        self.assertEqual(auth_security.auth_verify("test-secret", token)["username"], "analyst")


class CalibrationEvidenceTests(unittest.TestCase):
    def test_missing_evidence_does_not_score_a_prediction_as_false(self):
        from datetime import datetime, timezone, timedelta
        from unittest.mock import Mock
        import calibration_engine
        result = calibration_engine._resolve_single({
            "id": 1, "stated_prob": 0.9, "_window": "24h",
            "created_at": datetime.now(timezone.utc) - timedelta(days=3),
        }, Mock())
        self.assertIsNone(result)

    def test_sensor_query_excludes_self_and_requires_matching_type(self):
        from datetime import datetime, timezone, timedelta
        from unittest.mock import Mock
        import calibration_engine
        cur = Mock()
        cur.fetchone.side_effect = [(32.0, 35.0, "STRIKE"), ({},)]
        cur.fetchall.return_value = []
        result = calibration_engine._resolve_single({
            "id": 1, "event_id": "original", "stated_prob": 0.9, "_window": "24h",
            "created_at": datetime.now(timezone.utc) - timedelta(days=3),
        }, cur)
        self.assertIsNone(result)
        query, params = cur.execute.call_args_list[1].args
        self.assertIn("id <> %s AND type = %s", query)
        self.assertEqual(params[1:3], ("original", "STRIKE"))


class ImageryHonestyTests(unittest.TestCase):
    def test_cloud_metadata_never_claims_ground_change_or_smoke(self):
        import sentinel_imagery
        flags = sentinel_imagery._flags(0.8, [{"cloud_cover": 0}], [{"cloud_cover": 40}])
        self.assertNotIn("SIGNIFICANT_CHANGE_DETECTED", flags)
        self.assertNotIn("SMOKE_OR_CLOUD_SIGNATURE", flags)
        self.assertIn("CLOUD_COVER_INCREASE", flags)
