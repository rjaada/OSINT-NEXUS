import importlib
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import auth_security as authsec  # noqa: E402
import main as backend_main  # noqa: E402


class RuntimeHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["OSINT_DB_PATH"] = str(Path(cls.tmp.name) / "runtime_hardening.db")
        os.environ["AUTH_DEFAULT_ADMIN_USER"] = "admin"
        os.environ["AUTH_DEFAULT_ADMIN_PASSWORD"] = "AdminPass123!"
        os.environ["AUTH_ADMIN_REQUIRE_PASSKEY"] = "0"
        global backend_main
        backend_main = importlib.reload(backend_main)
        backend_main.app.router.on_startup.clear()
        backend_main.app.router.on_shutdown.clear()
        backend_main._db = backend_main.init_db()
        backend_main.ensure_default_admin()

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            if backend_main._db is not None:
                backend_main._db.close()
        except Exception:
            pass
        cls.tmp.cleanup()

    def setUp(self) -> None:
        backend_main._rate_limit.clear()
        backend_main._failed_logins.clear()
        backend_main._media_job_state.clear()

    def test_rate_limit_store_prunes_stale_and_caps(self):
        now = time.time()
        store = {
            "k1": [now - 1200],  # stale
            "k2": [now - 20, now - 10],  # fresh
            "k3": [],  # empty
            "k4": [now - 5],
            "k5": [now - 4],
        }
        authsec.prune_rate_limit_store(store, window_sec=60, max_buckets=2)
        self.assertNotIn("k1", store)
        self.assertNotIn("k3", store)
        self.assertLessEqual(len(store), 2)
        for values in store.values():
            self.assertTrue(all(now - t <= 60 for t in values))

    def test_prune_failed_logins_removes_stale_entries(self):
        now = time.time()
        backend_main._failed_logins.update(
            {
                "stale": {"count": 0, "lock_until": now - (backend_main.AUTH_LOGIN_LOCK_SEC * 2)},
                "fresh": {"count": 1, "lock_until": now + 30},
            }
        )
        backend_main._prune_failed_logins()
        self.assertNotIn("stale", backend_main._failed_logins)
        self.assertIn("fresh", backend_main._failed_logins)

    def test_prune_media_job_state_keeps_recent_and_caps(self):
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
        recent_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        backend_main._media_job_state["old_done"] = {"status": "done", "updated_at": old_ts}
        backend_main._media_job_state["recent_done"] = {"status": "done", "updated_at": recent_ts}
        backend_main._media_job_state["running"] = {"status": "running", "updated_at": old_ts}
        backend_main._prune_media_job_state()
        self.assertNotIn("old_done", backend_main._media_job_state)
        self.assertIn("recent_done", backend_main._media_job_state)
        self.assertIn("running", backend_main._media_job_state)


if __name__ == "__main__":
    unittest.main()

