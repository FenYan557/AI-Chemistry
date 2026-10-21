import copy
import json
import sys
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import refine_v2_relations as r
from extraction import ingest


class IncrementTests(unittest.TestCase):
    def setUp(self):
        self.g = r.materialize(r.read(ROOT / "examples/literature_bundle.json"))

    def test_empty_patch_replays_and_preserves_ids(self):
        self.g["entities"][0]["id"] = "entity:import"
        self.g = r.materialize(self.g)
        patch = {"base_content_sha256": r.digest(self.g), "replace_fact_ids": []}
        result = r.apply_change_set(self.g, patch)
        patch["result_content_sha256"] = r.digest(result)
        self.assertEqual(result, r.apply_change_set(result, patch))
        self.assertEqual(self.g, result)

    def test_patch_rejects_wrong_fingerprint(self):
        with self.assertRaisesRegex(ValueError, "指纹"):
            r.apply_change_set(self.g, {"base_content_sha256": "bad", "replace_fact_ids": []})

    def test_conflicting_fact_id_rejected(self):
        fact = copy.deepcopy(self.g["facts"][0])
        fact["statement_type"] = "unknown"
        with self.assertRaisesRegex(ValueError, "ID"):
            r.apply_change_set(self.g, {"base_content_sha256": r.digest(self.g), "replace_fact_ids": [], "add_facts": [fact]})

    def test_cross_document_endpoint_rejected(self):
        fact = copy.deepcopy(self.g["facts"][0])
        fact["id"] = "f:cross"
        fact["document_id"] = "absent-document"
        with self.assertRaisesRegex(ValueError, "引用/来源/结构"):
            r.apply_change_set(self.g, {"base_content_sha256": r.digest(self.g), "replace_fact_ids": [], "add_facts": [fact]})

    def test_cache_changes_with_prompt_model_and_source(self):
        task = {"document_id": "d", "blocks": [], "old_facts": [], "entity_hints": [], "source_fingerprint": "x"}
        _, first = r.request_spec(task, {"model": "a"})
        _, other = r.request_spec(task, {"model": "b"})
        self.assertNotEqual(first, other)
        task["source_fingerprint"] = "new"
        self.assertNotEqual(first, r.request_spec(task, {"model": "a"})[1])

    def test_anchored_mention_reused(self):
        g = copy.deepcopy(self.g)
        b = g["blocks"][0]
        # A small source-local candidate exercises non-generated imported mention IDs.
        mention = next(m for m in g["mentions"] if m["evidence"].get("block_id") == b["id"])
        raw = {"subject": mention["surface"], "relation": "other", "statement": "unknown", "quote": b["text"]}
        result = ingest(g, b["id"], {"facts": [raw]})
        self.assertEqual(result["facts"][-1]["participants"][0]["mention_id"], mention["id"])

    def test_truncated_output_not_imported(self):
        with self.assertRaisesRegex(ValueError, "上限"):
            r.decode({"raw": {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}})

    def test_failure_resume_and_cache_avoid_second_success_call(self):
        task = {"id": "development-one", "split": "development", "document_id": "d", "blocks": [],
                "old_facts": [], "entity_hints": [], "source_fingerprint": "source"}
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            r.write(run / "tasks.json", [task])
            with patch.object(r, "baseline", return_value=self.g), patch.object(r, "load_config", return_value={"model": "test"}):
                with patch.object(r, "request_json", side_effect=r.ExtractionAPIError("timeout")):
                    self.assertEqual(r.run_tasks(run, "development", 1)[0]["status"], "transport_failed")
                with patch.object(r, "request_json", return_value=({"usage": {"total_tokens": 12}}, .01)) as call:
                    self.assertFalse(r.run_tasks(run, "development", 1)[0]["cached"])
                    self.assertTrue(r.run_tasks(run, "development", 1)[0]["cached"])
                    self.assertEqual(call.call_count, 1)
                self.assertEqual(r.usage(run)["failed_attempts"], 1)

    def test_open_coordination_and_single_object_measurement_no_edges(self):
        b = self.g["blocks"][0]
        mention = next(m for m in self.g["mentions"] if m["evidence"].get("block_id") == b["id"])
        for relation in ["mechanism", "measurement"]:
            result = ingest(self.g, b["id"], {"facts": [{"subject": mention["surface"], "relation": relation,
                            "statement": "author_interpretation", "quote": b["text"]}]})
            added = result["facts"][-1]
            self.assertFalse(any(e["fact_id"] == added["id"] for e in result["edges"]))
            self.assertEqual(added["statement_type"], "author_interpretation")


if __name__ == "__main__":
    unittest.main()
