"""Integration checks for tables required by live intelligence routes."""
import unittest
from urllib.parse import urlparse

import db_postgres
import v2_store


class DatabaseSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if urlparse(db_postgres.DATABASE_URL).path != "/osint_test":
            raise RuntimeError("Schema tests require POSTGRES_DB=osint_test")
        with db_postgres.get_pg_conn() as conn:
            db_postgres.init_pg_schema(conn)

    def test_events_v2_schema_supports_persistence_and_escalation_fields(self):
        status = v2_store.postgres_status(db_postgres.DATABASE_URL, db_postgres.psycopg)
        self.assertTrue(status["connected"])
        expected = {
            "time_precision", "geo_precision", "source_scale",
            "civilian_targeting", "acled_event_type", "acled_sub_event_type",
            "confidence_score",
        }
        with db_postgres.get_pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'events_v2'"
                )
                actual = {row["column_name"] for row in cur.fetchall()}
        self.assertTrue(expected.issubset(actual), expected - actual)

    def test_prediction_stats_parameterizes_the_interval_correctly(self):
        import prediction_tracker
        result = prediction_tracker.fetch_accuracy_stats(db_postgres.DATABASE_URL, db_postgres.psycopg)
        self.assertIn("scored", result, "Statistics query failed and returned its fallback")
        self.assertEqual(result["assessment_method"], "keyword_overlap_heuristic")

    def test_conflict_zones_table_exists_after_schema_initialization(self):
        conn = db_postgres.get_pg_conn()
        try:
            db_postgres.init_pg_schema(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.conflict_zones') AS table_name")
                row = cur.fetchone()
            self.assertEqual(row["table_name"], "conflict_zones")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
