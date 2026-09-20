import importlib
import os
import sys
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path

import psycopg
from fastapi import Response
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config as backend_config  # noqa: E402
import db_sqlite as backend_db_sqlite  # noqa: E402
import db_postgres as backend_db_postgres  # noqa: E402
import main as backend_main  # noqa: E402


def _ensure_test_database(dbname: str) -> None:
    """Create the isolated test Postgres database if it doesn't exist yet.

    main.init_db() always opens Postgres (db_ops.init_db ignores
    OSINT_DB_PATH), so this suite must point POSTGRES_DB at a database that
    is never the real app's database, or every run pollutes production data
    with test accounts.
    """
    host = os.getenv("POSTGRES_HOST", "postgres")
    user = os.getenv("POSTGRES_USER", "osint")
    password = urllib.parse.quote(os.getenv("POSTGRES_PASSWORD", ""), safe="")
    admin_conn = psycopg.connect(
        f"postgresql://{user}:{password}@{host}:5432/{user}", autocommit=True
    )
    try:
        with admin_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        admin_conn.close()


class AuthAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["OSINT_DB_PATH"] = str(Path(cls.tmp.name) / "auth_test.db")
        _ensure_test_database("osint_test")
        os.environ["POSTGRES_DB"] = "osint_test"
        os.environ["AUTH_DEFAULT_ADMIN_USER"] = "admin"
        os.environ["AUTH_DEFAULT_ADMIN_PASSWORD"] = "AdminPass123!"
        os.environ["AUTH_ADMIN_REQUIRE_PASSKEY"] = "0"
        os.environ["AUTH_IDLE_TIMEOUT_SEC"] = "900"
        os.environ["AUTH_BREAK_GLASS_CODE"] = "test-break-glass"
        global backend_main
        # Reload config → db_sqlite → main so all env-var changes propagate.
        importlib.reload(backend_config)
        importlib.reload(backend_db_sqlite)
        # db_postgres does `from config import DATABASE_URL` at module load —
        # a copied binding, not a live reference — so it must be reloaded
        # explicitly after config or it keeps pointing at the real database.
        importlib.reload(backend_db_postgres)
        backend_main = importlib.reload(backend_main)
        backend_main.app.router.on_startup.clear()
        backend_main.app.router.on_shutdown.clear()
        backend_main._db = backend_main.init_db()
        # Against a freshly-started CI Postgres, some CREATE TABLE statements
        # in init_pg_schema's single transaction have been observed missing
        # from information_schema immediately afterward (auth_sessions,
        # conflict_zones) even though later statements in the SAME commit
        # succeeded — looks like contention with the postgis image's own
        # background extension setup on a brand-new container. init_pg_schema
        # is idempotent (CREATE TABLE IF NOT EXISTS), so retry it directly
        # against the specific table this suite depends on until it's real.
        for _attempt in range(5):
            with backend_main._db.cursor() as _verify_cur:
                _verify_cur.execute(
                    "SELECT to_regclass('public.auth_sessions') IS NOT NULL AS ok"
                )
                if _verify_cur.fetchone()["ok"]:
                    break
            backend_db_postgres.init_pg_schema(backend_main._db)
            time.sleep(0.5)
        else:
            raise RuntimeError("auth_sessions table still missing after 5 schema-init retries")
        backend_main.ensure_default_admin()
        # NOTE: OSINT_DB_PATH above is vestigial — main.init_db() always opens
        # a real Postgres connection (db_ops.init_db -> db_postgres.get_pg_conn),
        # ignoring OSINT_DB_PATH entirely. This suite is NOT isolated: it runs
        # against whatever Postgres the container is pointed at. Every username
        # this class creates MUST be tracked here and deleted in tearDownClass,
        # or repeated runs leave junk accounts in a real database.
        cls.created_usernames = ["admin"]

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            if backend_main._db is not None:
                with backend_main._db.cursor() as cur:
                    for uname in cls.created_usernames:
                        cur.execute("DELETE FROM users WHERE username = %s", (uname.strip().lower(),))
                backend_main._db.commit()
        except Exception:
            pass
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
        type(self).created_usernames.append(username)
        return self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password, "role": role},
        )

    def _login(self, username: str, password: str):
        payload = {"username": username, "password": password}
        if username == "admin":
            payload["break_glass_code"] = "test-break-glass"
        return self.client.post("/api/auth/login", json=payload)

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

    def test_public_registration_forces_viewer_role(self):
        username = f"selfadmin{int(time.time() * 1000)}"
        response = self._register(username, "StrongPass123!", "admin")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("role"), "viewer")

    def test_role_change_invalidates_existing_session(self):
        username = f"rolefresh{int(time.time() * 1000)}"
        registered = self._register(username, "StrongPass123!", "viewer")
        self.assertEqual(registered.status_code, 200)

        user_client = TestClient(backend_main.app)
        login_user = user_client.post(
            "/api/auth/login",
            json={"username": username, "password": "StrongPass123!"},
        )
        self.assertEqual(login_user.status_code, 200)
        self.assertEqual(user_client.get("/api/auth/session").json().get("role"), "viewer")

        self.assertEqual(self._login("admin", "AdminPass123!").status_code, 200)
        csrf = self.client.get("/api/auth/session").json().get("csrf", "")
        promoted = self.client.patch(
            f"/api/admin/users/{username}/role",
            json={"role": "analyst"},
            headers={"x-csrf-token": csrf},
        )
        self.assertEqual(promoted.status_code, 200)
        refreshed = user_client.get("/api/auth/session")
        self.assertEqual(refreshed.status_code, 200)
        self.assertFalse(refreshed.json().get("authenticated"))

    def test_required_role_without_mfa_enrollment_is_rejected(self):
        username = f"nomfa{int(time.time() * 1000)}"
        registered = self._register(username, "StrongPass123!", "viewer")
        self.assertEqual(registered.status_code, 200)

        self.assertEqual(self._login("admin", "AdminPass123!").status_code, 200)
        csrf = self.client.get("/api/auth/session").json().get("csrf", "")
        promoted = self.client.patch(
            f"/api/admin/users/{username}/role",
            json={"role": "analyst"},
            headers={"x-csrf-token": csrf},
        )
        self.assertEqual(promoted.status_code, 200)

        analyst_client = TestClient(backend_main.app)
        response = analyst_client.post(
            "/api/auth/login",
            json={"username": username, "password": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("MFA enrollment required", response.json().get("detail", ""))

    def test_server_rejects_session_after_idle_timeout(self):
        username = f"idle{int(time.time() * 1000)}"
        self.assertEqual(self._register(username, "StrongPass123!").status_code, 200)
        self.assertEqual(self._login(username, "StrongPass123!").status_code, 200)
        token = self.client.cookies.get("osint_auth")
        verified = backend_main.auth_verify(token)
        self.assertIsNotNone(verified)
        sig = str(verified["sig"])

        with backend_main._db.cursor() as cur:
            cur.execute(
                "UPDATE auth_sessions SET last_seen_epoch = %s WHERE sig = %s",
                (int(time.time()) - backend_main.AUTH_IDLE_TIMEOUT_SEC - 1, sig),
            )
        backend_main._db.commit()

        session = self.client.get("/api/auth/session")
        self.assertFalse(session.json().get("authenticated"))

    def test_authenticated_request_refreshes_server_activity(self):
        username = f"active{int(time.time() * 1000)}"
        self.assertEqual(self._register(username, "StrongPass123!").status_code, 200)
        self.assertEqual(self._login(username, "StrongPass123!").status_code, 200)
        verified = backend_main.auth_verify(self.client.cookies.get("osint_auth"))
        sig = str(verified["sig"])
        stale = int(time.time()) - 30
        with backend_main._db.cursor() as cur:
            cur.execute("UPDATE auth_sessions SET last_seen_epoch = %s WHERE sig = %s", (stale, sig))
        backend_main._db.commit()

        self.assertTrue(self.client.get("/api/auth/session").json().get("authenticated"))
        with backend_main._db.cursor() as cur:
            cur.execute("SELECT last_seen_epoch FROM auth_sessions WHERE sig = %s", (sig,))
            refreshed = int(cur.fetchone()["last_seen_epoch"])
        self.assertGreater(refreshed, stale)

    def test_passkey_cookie_helper_registers_server_session(self):
        username = f"passkey{int(time.time() * 1000)}"
        self.assertEqual(self._register(username, "StrongPass123!").status_code, 200)
        backend_main._set_auth_cookies(Response(), username, "viewer")
        with backend_main._db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM auth_sessions WHERE username = %s", (username,))
            count = int(cur.fetchone()["c"])
        self.assertEqual(count, 1)

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
