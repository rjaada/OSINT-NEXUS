"""Tests for TOTP replay protection, confidence math, claim alignment, and cluster bucketing."""
import sqlite3
import sys
import unittest
from pathlib import Path

import pyotp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mfa_totp
import intel_utils


def _make_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    mfa_totp.ensure_table(db)
    return db


class TestTOTPReplay(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.secret = pyotp.random_base32()
        self.user = "testuser"

    def test_same_code_rejected_second_time(self):
        code = pyotp.TOTP(self.secret).now()
        first = mfa_totp.verify_and_consume(self.db, self.user, self.secret, code)
        second = mfa_totp.verify_and_consume(self.db, self.user, self.secret, code)
        self.assertTrue(first, "First use of valid code should be accepted")
        self.assertFalse(second, "Replayed code should be rejected")

    def test_different_code_accepted(self):
        """A different valid code (different user, same secret) should be accepted."""
        code = pyotp.TOTP(self.secret).now()
        mfa_totp.verify_and_consume(self.db, self.user, self.secret, code)
        # A different username with same code is a distinct (username, code) pair
        result = mfa_totp.verify_and_consume(self.db, "otheruser", self.secret, code)
        self.assertTrue(result, "Same code for a different user should be accepted")

    def test_invalid_code_rejected(self):
        result = mfa_totp.verify_and_consume(self.db, self.user, self.secret, "000000")
        self.assertFalse(result, "Invalid TOTP code should be rejected")


SOURCE_RELIABILITY = {"TestSource": 70}


class TestAssessConfidence(unittest.TestCase):
    def _event(self, **kwargs):
        base = {"desc": "[TestSource] something happened", "type": "CLASH"}
        base.update(kwargs)
        return base

    def _nearby(self, sources):
        return [{"desc": f"[{s}] nearby event"} for s in sources]

    def test_corroborating_sources_increase_score(self):
        event = self._event()
        nearby_none = self._nearby([])
        nearby_two = self._nearby(["SourceB", "SourceC"])
        score_none, _, _ = intel_utils.assess_confidence(event, nearby_none, 10, SOURCE_RELIABILITY)
        score_two, _, _ = intel_utils.assess_confidence(event, nearby_two, 10, SOURCE_RELIABILITY)
        self.assertGreater(score_two, score_none, "Corroborating sources should increase score")

    def test_fresh_event_gets_freshness_bonus(self):
        event = self._event()
        score_fresh, reasons_fresh, _ = intel_utils.assess_confidence(event, [], 2, SOURCE_RELIABILITY)
        score_stale, reasons_stale, _ = intel_utils.assess_confidence(event, [], 60, SOURCE_RELIABILITY)
        self.assertGreater(score_fresh, score_stale, "Fresh event should score higher than stale")
        self.assertIn("fresh update", reasons_fresh)
        self.assertNotIn("fresh update", reasons_stale)

    def test_insufficient_evidence_reduces_score(self):
        event_ok = self._event()
        event_weak = self._event(insufficient_evidence=True)
        score_ok, _, _ = intel_utils.assess_confidence(event_ok, [], 10, SOURCE_RELIABILITY)
        score_weak, reasons, _ = intel_utils.assess_confidence(event_weak, [], 10, SOURCE_RELIABILITY)
        self.assertGreater(score_ok, score_weak, "insufficient_evidence flag should reduce score")
        self.assertIn("limited geolocation evidence", reasons)


class TestEvaluateClaimAlignment(unittest.TestCase):
    def test_strong_overlap_likely_related(self):
        desc = "explosion strike attack missile drone rocket airstrike forces"
        ocr = ["explosion strike attack missile drone rocket airstrike forces"]
        label, _ = intel_utils.evaluate_claim_alignment(desc, ocr, [])
        self.assertEqual(label, "LIKELY_RELATED")

    def test_no_media_unverified_visual(self):
        label, msg = intel_utils.evaluate_claim_alignment("some event happened", [], [])
        self.assertEqual(label, "UNVERIFIED_VISUAL")
        self.assertIn("No OCR/STT", msg)

    def test_low_overlap_mismatch(self):
        desc = "airstrike in northern city"
        ocr = ["completely unrelated content here"]
        label, _ = intel_utils.evaluate_claim_alignment(desc, ocr, [])
        self.assertEqual(label, "MISMATCH")


class TestClusterEventsForMap(unittest.TestCase):
    def _ev(self, eid, lat, lng, t="CLASH"):
        return {"id": eid, "lat": lat, "lng": lng, "type": t}

    def test_nearby_events_cluster_together(self):
        events = [
            self._ev("a", 32.00, 35.00),
            self._ev("b", 32.05, 35.05),  # ~6 km away — within 0.1°
        ]
        clusters = intel_utils.cluster_events_for_map(events)
        self.assertEqual(len(clusters), 1, "Nearby events should merge into one cluster")
        self.assertEqual(clusters[0]["count"], 2)
        self.assertIn("a", clusters[0]["members"])
        self.assertIn("b", clusters[0]["members"])

    def test_far_apart_events_stay_separate(self):
        events = [
            self._ev("x", 32.0, 35.0),
            self._ev("y", 34.0, 37.0),  # 2° apart — separate buckets
        ]
        clusters = intel_utils.cluster_events_for_map(events)
        self.assertEqual(len(clusters), 2, "Far-apart events should remain separate clusters")


if __name__ == "__main__":
    unittest.main()
