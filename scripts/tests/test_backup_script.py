import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


class BackupScriptTests(unittest.TestCase):
    def test_pg_dump_failure_does_not_publish_or_prune(self):
        repo = Path(__file__).resolve().parents[2]
        script = repo / "scripts" / "backup.sh"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup_dir = root / "backups"
            bin_dir = root / "bin"
            backup_dir.mkdir()
            bin_dir.mkdir()

            pg_dump = bin_dir / "pg_dump"
            pg_dump.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
            pg_dump.chmod(0o755)

            old_backup = backup_dir / "postgres_existing.sql.gz"
            old_backup.write_bytes(b"valid-existing-backup")
            old = time.time() - 40 * 24 * 60 * 60
            os.utime(old_backup, (old, old))

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}:{env['PATH']}",
                    "BACKUP_DIR": str(backup_dir),
                    "POSTGRES_PASSWORD": "test-only",
                    "RETENTION_DAYS": "1",
                }
            )
            result = subprocess.run(
                ["/bin/sh", str(script)],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(old_backup.exists())
            self.assertEqual(list(backup_dir.glob("postgres_*.sql.gz")), [old_backup])
            self.assertFalse(list(backup_dir.glob("*.tmp")))

    def test_concurrent_backups_do_not_share_temporary_files(self):
        repo = Path(__file__).resolve().parents[2]
        script = repo / "scripts" / "backup.sh"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup_dir = root / "backups"
            bin_dir = root / "bin"
            backup_dir.mkdir()
            bin_dir.mkdir()

            pg_dump = bin_dir / "pg_dump"
            pg_dump.write_text(
                "#!/bin/sh\nprintf 'dump-%s\\n' \"$$\"\nsleep 1\n",
                encoding="utf-8",
            )
            pg_dump.chmod(0o755)
            env = os.environ.copy()
            env.update({
                "PATH": f"{bin_dir}:{env['PATH']}",
                "BACKUP_DIR": str(backup_dir),
                "POSTGRES_PASSWORD": "test-only",
            })

            first = subprocess.Popen(
                ["/bin/sh", str(script)], cwd=repo, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            time.sleep(0.1)
            started = time.monotonic()
            second = subprocess.run(
                ["/bin/sh", str(script)], cwd=repo, env=env,
                capture_output=True, text=True, timeout=10, check=False,
            )
            second_elapsed = time.monotonic() - started
            first_out, first_err = first.communicate(timeout=10)

            self.assertEqual(first.returncode, 0, first_err)
            self.assertEqual(second.returncode, 1)
            self.assertLess(second_elapsed, 0.5)
            self.assertIn("backup already in progress", second.stderr.lower())
            self.assertNotIn("no such file", first_err.lower())
            self.assertEqual(len(list(backup_dir.glob("postgres_*.sql.gz"))), 1)
            self.assertFalse(list(backup_dir.glob("*.tmp")))
            self.assertFalse((backup_dir / ".backup.lock").exists())


if __name__ == "__main__":
    unittest.main()
