"""v4实际风险回归：出处、投影、便宜模型输入和回答接口。"""
import copy
import json
import sys
import unittest
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate import validate, load
from materialize import materialize, retrieval_keys
from answer_context import build_context
from extraction import ingest
from migrate_v4 import upgrade


def hard():
    return load(ROOT / "examples/hard_cases.json")


def codes(b):
    return {e["code"] for e in validate(b)["errors"]}


class V4Tests(unittest.TestCase):
    def test_reverse_edge_rejected(self):
        b = hard()
        edge = next(e for e in b["edges"] if e["fact_id"] == "h:adsorption")
        edge["from_entity_id"], edge["to_entity_id"] = edge["to_entity_id"], edge["from_entity_id"]
        self.assertIn("EDGE_DERIVATION_MISMATCH", codes(b))

    def test_participant_reordering_has_no_semantic_effect(self):
        b = hard()
        edges = copy.deepcopy(b["edges"])
        for f in b["facts"]:
            f["participants"].reverse()
        self.assertEqual(edges, materialize(b)["edges"])

    def test_forged_baseline_rejected(self):
        b = hard()
        f = next(f for f in b["facts"] if f["id"] == "h:annealed_resistivity")
        f["outcomes"][0]["comparison"]["baseline_raw"] = "99999 invented baseline"
        self.assertIn("COMPARISON_BASELINE_NOT_LITERAL", codes(b))

    def test_absent_condition_does_not_crash(self):
        b = load(ROOT / "examples/literature_bundle.json")
        f = next(f for f in b["facts"] if f["conditions"])
        f["conditions"][0]["value"].update(value_raw=None, value_kind="absent")
        materialize(b)
        self.assertTrue(validate(b)["valid"])

    def test_table_outcome_has_no_quote_key(self):
        b = hard()
        f = b["facts"][0]
        cell = {"kind": "table_cell", "table_id": "糖精对镀钴层结构_导电能力的改变__p2_0",
                "row": 1, "col": 2, "cell_raw": "80 °C, 15 min"}
        doc = next(d["id"] for d in b["documents"] if d["id"].startswith("糖精"))
        f["document_id"] = doc
        f["participants"] = [{"mention_id": "m:saccharin", "role": "subject"}]
        f["relation"]["candidate_relation_id"] = None
        f["evidence"] = [cell]
        f["outcomes"] = [{"indicator_raw": "raw cell", "value": {
            "value_raw": "80", "value_kind": "numeric", "unit_raw": "°C", "unit_status": "reported"},
            "evidence": [cell]}]
        materialize(b)
        self.assertTrue(validate(b)["valid"])

    def test_sparse_record_gets_defaults_without_claiming_absence(self):
        b = load(ROOT / "examples/literature_bundle.json")
        for f in b["facts"]:
            for key in ["review", "notes", "extraction", "modality", "group_id", "cited_work", "source_scope", "polarity", "run_id"]:
                f.pop(key, None)
        b.pop("edges")
        self.assertTrue(validate(b)["valid"])
        self.assertNotIn("review", b["facts"][0])  # 校验不改调用者原数据

    def test_missing_block_evidence_field_is_structure_error(self):
        b = hard()
        b["facts"][0]["evidence"][0].pop("quote")
        self.assertIn("STRUCTURE", codes(b))

    def test_ambiguous_type_not_first_candidate(self):
        b = hard()
        b["mentions"][0]["candidate_type_ids"] = ["t1", "t22"]
        self.assertIsNone(materialize(b)["entities"][0]["type_id"])

    def test_open_facts_have_retrieval_keys(self):
        b = hard()
        keys = retrieval_keys(b)
        self.assertEqual(len(keys["fact_keys"]), len(b["facts"]))
        self.assertIn("h:methods", {r["fact_id"] for r in keys["fact_keys"]})

    def test_answer_does_not_leak_governance(self):
        context = build_context(hard())
        content = json.dumps(context, ensure_ascii=False)
        for term in ["ENTITY_UNTYPED", "tier_counts", "semantic_review_pending", '"review"']:
            self.assertNotIn(term, content)
        self.assertEqual(len(context["evidence"]), 8)
        self.assertIn("h:methods", {r["fact_id"] for r in context["references"].values()})
        self.assertNotIn("future_work", json.dumps(context["evidence"], ensure_ascii=False))
        self.assertEqual(context["evidence"][0]["citation"], "S1")
        self.assertIn("audit", build_context(hard(), audit=True))

    def test_bad_bundle_cannot_reach_answer_model(self):
        b = hard()
        b["facts"][0]["evidence"][0]["quote"] = "invented"
        with self.assertRaises(ValueError):
            build_context(b)

    def test_unknown_selected_fact_rejected(self):
        with self.assertRaises(ValueError):
            build_context(hard(), ["missing"])

    def test_migration_is_idempotent(self):
        b = hard()
        self.assertEqual(upgrade(b), upgrade(upgrade(b)))

    def test_minimal_extraction_ingested_and_deduplicated(self):
        b = load(ROOT / "examples/literature_bundle.json")
        block = b["blocks"][0]
        quote = "effects of low-concentration acceleration but high-concentration suppression in cobalt deposition"
        raw = {"facts": [{"subject": "ADO", "target": "cobalt deposition", "relation": "effect",
                          "statement": "reported_claim", "quote": quote,
                          "conditions": [{"parameter": "concentration", "value": "low-concentration",
                                          "quote": quote, "about": "subject"}]}]}
        result = ingest(b, block["id"], raw, model="test")
        self.assertEqual(len(result["facts"]), len(b["facts"]) + 1)
        self.assertEqual(ingest(result, block["id"], raw, model="test"), result)
        self.assertTrue(validate(result)["valid"])

    def test_extraction_fabricated_value_rejected(self):
        b = load(ROOT / "examples/literature_bundle.json")
        block = b["blocks"][2]
        raw = {"facts": [{"subject": "saccharin", "relation": "measurement", "statement": "observation",
                          "quote": "saccharin", "outcomes": [{"indicator": "resistivity", "value": "99999",
                                      "kind": "numeric", "quote": "saccharin", "unit": "μΩ·cm"}]}]}
        with self.assertRaises(ValueError):
            ingest(b, block["id"], raw)

    def test_compact_schema_has_no_governance_required(self):
        schema = load(ROOT / "schema/extraction.schema.json")
        Draft202012Validator.check_schema(schema)
        required = schema["properties"]["facts"]["items"]["required"]
        self.assertEqual(set(required), {"subject", "relation", "statement", "quote"})


if __name__ == "__main__":
    unittest.main()
