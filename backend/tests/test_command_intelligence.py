"""Behavior tests for the evidence-backed Nexus Command snapshot."""
from datetime import datetime, timezone
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from command_intelligence import assess_hypothesis_evidence, build_command_snapshot

NOW = datetime(2026, 8, 26, 22, 0, tzinfo=timezone.utc)


def event(event_id, source, confidence, *, event_type="ACTIVITY", hours_old=1, url=True, origin_id=None):
    item = {
        "id": event_id,
        "source": source,
        "confidence_score": confidence,
        "type": event_type,
        "desc": f"Evidence {event_id}",
        "timestamp": f"2026-08-26T{22-hours_old:02d}:00:00+00:00",
        "url": f"https://example.test/{event_id}" if url else "",
        "observed_facts": ["observed"],
        "model_inference": [],
    }
    if origin_id:
        item["provenance"] = {"origin_id": origin_id}
    return item


class TestHypothesisEvidenceAssessment(unittest.TestCase):
    def test_no_evidence_is_explicitly_insufficient(self):
        result = assess_hypothesis_evidence(
            {"id": "h1", "confidence": 80, "evidence_ids": []}, [], now=NOW
        )
        self.assertEqual(result["posture"], "INSUFFICIENT")
        self.assertLessEqual(result["recommended_confidence"], 25)
        self.assertIn("NO_EVIDENCE_ATTACHED", result["collection_gaps"])

    def test_independent_high_quality_sources_create_corroborated_posture(self):
        events = [event("e1", "Reuters", 92, origin_id="reuters"), event("e2", "BBC", 84, origin_id="bbc")]
        result = assess_hypothesis_evidence(
            {"id": "h1", "confidence": 60, "evidence_ids": ["e1", "e2"]},
            events,
            now=NOW,
        )
        self.assertEqual(result["posture"], "CORROBORATED")
        self.assertEqual(result["source_diversity"], 2)
        self.assertGreaterEqual(result["recommended_confidence"], 75)
        self.assertEqual(result["evidence"][0]["id"], "e1")
        self.assertEqual(result["evidence"][0]["source"], "Reuters")
        self.assertEqual(result["missing_evidence_ids"], [])

    def test_different_labels_from_same_origin_are_not_corroboration(self):
        events = [
            event("e1", "Wire Alpha", 90, origin_id="shared-wire"),
            event("e2", "Wire Beta", 88, origin_id="shared-wire"),
        ]
        result = assess_hypothesis_evidence(
            {"id": "h1", "confidence": 60, "evidence_ids": ["e1", "e2"]},
            events,
            now=NOW,
        )
        self.assertNotEqual(result["posture"], "CORROBORATED")
        self.assertEqual(result["source_diversity"], 1)
        self.assertIn("INDEPENDENT_CORROBORATION_REQUIRED", result["collection_gaps"])

    def test_recommended_confidence_is_always_bounded(self):
        result = assess_hypothesis_evidence(
            {"id": "h1", "confidence": -30, "evidence_ids": ["e1"]},
            [event("e1", "Unknown feed", -80)],
            now=NOW,
        )
        self.assertGreaterEqual(result["recommended_confidence"], 0)
        self.assertLessEqual(result["recommended_confidence"], 100)

    def test_missing_evidence_ids_are_never_silently_ignored(self):
        result = assess_hypothesis_evidence(
            {"id": "h1", "confidence": 70, "evidence_ids": ["e1", "missing"]},
            [event("e1", "Reuters", 80)],
            now=NOW,
        )
        self.assertEqual(result["missing_evidence_ids"], ["missing"])
        self.assertIn("MISSING_EVIDENCE", result["collection_gaps"])


class TestCommandSnapshot(unittest.TestCase):
    def test_snapshot_prioritizes_threats_and_surfaces_decision_gaps(self):
        events = [
            event("routine", "Feed A", 88, event_type="ACTIVITY"),
            event("critical", "Feed B", 81, event_type="CRITICAL"),
        ]
        hypotheses = [{
            "id": "h-open",
            "title": "Unverified escalation",
            "status": "OPEN",
            "confidence": 75,
            "evidence_ids": [],
            "updated_at": "2026-08-26T21:00:00+00:00",
        }]
        snapshot = build_command_snapshot(
            events=events,
            hypotheses=hypotheses,
            system={"postgres": {"connected": False}, "neo4j": {"connected": True}, "ai_runtime": {"available": True}},
            sitrep={"summary": "Current assessment", "watch_items": ["Monitor air activity"]},
            escalation={"theaters": []},
            now=NOW,
        )
        self.assertEqual(snapshot["priority_events"][0]["id"], "critical")
        queue_types = {item["type"] for item in snapshot["decision_queue"]}
        self.assertIn("SYSTEM_DEGRADED", queue_types)
        self.assertIn("EVIDENCE_GAP", queue_types)
        self.assertFalse(snapshot["integrity"]["evidence_backed"])

    def test_integrity_is_not_evidence_backed_when_inputs_or_collection_fail(self):
        snapshot = build_command_snapshot(
            events=[],
            hypotheses=[{"id": "h1", "evidence_ids": []}],
            system={"postgres": {"connected": True}},
            sitrep=None,
            escalation={"theaters": []},
            collection_errors=["events:unavailable"],
            now=NOW,
        )
        self.assertFalse(snapshot["integrity"]["evidence_backed"])
        self.assertFalse(snapshot["integrity"]["complete"])
        self.assertEqual(snapshot["integrity"]["collection_errors"], ["events:unavailable"])



if __name__ == "__main__":
    unittest.main()
