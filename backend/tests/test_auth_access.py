import importlib
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config as backend_config  # noqa: E402
import db_sqlite as backend_db_sqlite  # noqa: E402
import main as backend_main  # noqa: E402


class AuthAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["OSINT_DB_PATH"] = str(Path(cls.tmp.name) / "auth_test.db")
        os.environ["AUTH_DEFAULT_ADMIN_USER"] = "admin"
        os.environ["AUTH_DEFAULT_ADMIN_PASSWORD"] = "AdminPass123!"
        os.environ["AUTH_ADMIN_REQUIRE_PASSKEY"] = "0"
        global backend_main
        # Reload config → db_sqlite → main so all env-var changes propagate.
        importlib.reload(backend_config)
        importlib.reload(backend_db_sqlite)
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
        self.client = TestClient(backend_main.app)

    def tearDown(self) -> None:
        self.client.close()

    def _register(self, username: str, password: str, role: str = "viewer"):
        return self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password, "role": role},
        )

    def _login(self, username: str, password: str):
        return self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )

    def test_register_login_session_logout_requires_csrf(self):
        username = f"u{int(time.time() * 1000)}"
        password = "StrongPass123!"
        reg = self._register(username, password, "viewer")
        self.assertEqual(reg.status_code, 200)

        login = self._login(username, password)
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json().get("role"), "viewer")

        session = self.client.get("/api/auth/session")
        self.assertEqual(session.status_code, 200)
        self.assertTrue(session.json().get("authenticated"))
        csrf = session.json().get("csrf")
        self.assertTrue(isinstance(csrf, str) and len(csrf) > 10)

        logout_no_csrf = self.client.post("/api/auth/logout")
        self.assertEqual(logout_no_csrf.status_code, 403)

        logout = self.client.post("/api/auth/logout", headers={"x-csrf-token": csrf})
        self.assertEqual(logout.status_code, 200)
        self.assertTrue(logout.json().get("ok"))

        session_after = self.client.get("/api/auth/session")
        self.assertEqual(session_after.status_code, 200)
        self.assertFalse(session_after.json().get("authenticated"))

    def test_admin_role_and_delete_guards(self):
        login_admin = self._login("admin", "AdminPass123!")
        self.assertEqual(login_admin.status_code, 200)
        csrf = self.client.get("/api/auth/session").json().get("csrf", "")
        self.assertTrue(csrf)

        users = self.client.get("/api/admin/users")
        self.assertEqual(users.status_code, 200)
        self.assertGreaterEqual(len(users.json().get("items", [])), 1)

        demote_last_admin = self.client.patch(
            "/api/admin/users/admin/role",
            json={"role": "viewer"},
            headers={"x-csrf-token": csrf},
        )
        self.assertEqual(demote_last_admin.status_code, 400)

        target = f"viewer{int(time.time() * 1000)}"
        reg_target = self._register(target, "StrongPass123!", "viewer")
        self.assertEqual(reg_target.status_code, 200)

        promote = self.client.patch(
            f"/api/admin/users/{target}/role",
            json={"role": "analyst"},
            headers={"x-csrf-token": csrf},
        )
        self.assertEqual(promote.status_code, 200)
        self.assertEqual(promote.json().get("role"), "analyst")

        delete_target = self.client.delete(
            f"/api/admin/users/{target}",
            headers={"x-csrf-token": csrf},
        )
        self.assertEqual(delete_target.status_code, 200)
        self.assertTrue(delete_target.json().get("ok"))

        delete_self = self.client.delete(
            "/api/admin/users/admin",
            headers={"x-csrf-token": csrf},
        )
        self.assertEqual(delete_self.status_code, 400)

    def test_admin_password_requires_passkey_or_break_glass(self):
        prev_require = backend_main.AUTH_ADMIN_REQUIRE_PASSKEY
        prev_break = backend_main.AUTH_BREAK_GLASS_CODE
        backend_main.AUTH_ADMIN_REQUIRE_PASSKEY = True
        backend_main.AUTH_BREAK_GLASS_CODE = "emergency-123"
        try:
            blocked = self.client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "AdminPass123!"},
            )
            self.assertEqual(blocked.status_code, 401)

            allowed = self.client.post(
                "/api/auth/login",
                json={
                    "username": "admin",
                    "password": "AdminPass123!",
                    "break_glass_code": "emergency-123",
                },
            )
            self.assertEqual(allowed.status_code, 200)
        finally:
            backend_main.AUTH_ADMIN_REQUIRE_PASSKEY = prev_require
            backend_main.AUTH_BREAK_GLASS_CODE = prev_break


if __name__ == "__main__":
    unittest.main()
