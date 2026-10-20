"""治理层测试：三档目录覆盖、复杂度预算、词表与契约一致性。"""
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_budget  # noqa: E402
import materialize as m  # noqa: E402
import validate as v  # noqa: E402


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def schema():
    return load("schema/records.schema.json")


class TierCatalogTests(unittest.TestCase):
    def test_every_validator_code_has_a_tier(self):
        src = (ROOT / "scripts/validate.py").read_text(encoding="utf-8")
        used = set(re.findall(r'(?:err|warn|add)\("([A-Z_]+)"', src))
        catalog = load("schema/constraints.json")
        tiered = {code for item in catalog["constraints"] for code in item["codes"]}
        self.assertEqual(used - tiered, set(), "校验器有未登记档位的错误码")
        self.assertEqual(tiered - used, set(), "目录里有校验器不再产生的错误码")

    def test_tiers_are_three_known_levels(self):
        catalog = load("schema/constraints.json")
        for item in catalog["constraints"]:
            self.assertIn(item["severity"], {"block", "review", "warn"})
            self.assertTrue(item["statement"])
            self.assertTrue(item["rationale"])

    def test_block_tier_means_rejection(self):
        result = v.validate(v.load(ROOT / "examples/literature_bundle.json"))
        self.assertTrue(result["valid"])
        self.assertEqual(result["tier_counts"]["block"], 0)
        self.assertEqual(result["errors"], [])


class BudgetTests(unittest.TestCase):
    def test_budget_not_exceeded(self):
        result = check_budget.check()
        self.assertTrue(result["ok"], result["exceeded"])
        self.assertGreater(result["actual"]["entity_types"], 0)

    def test_budget_is_enforced(self):
        inflated = dict(check_budget.actual_counts())
        inflated["entity_types"] = 10_000
        with mock.patch.object(check_budget, "actual_counts", return_value=inflated):
            result = check_budget.check()
        self.assertFalse(result["ok"])
        self.assertEqual(result["exceeded"][0]["metric"], "entity_types")


class RegistryTests(unittest.TestCase):
    def test_entity_types_are_instantiable_or_explicitly_blocked(self):
        registry = load("registry/entity_types.json")
        ids = [t["type_id"] for t in registry["types"]]
        self.assertEqual(len(ids), len(set(ids)))
        for item in registry["types"]:
            self.assertIn(item["status"], {"core", "proposed"})
            if item["status"] == "core":
                self.assertTrue(item["criteria"], item["type_id"] + " 缺判据却标 core")
                self.assertTrue(item["positive_examples"], item["type_id"] + " 缺正例")
                self.assertTrue(item["counterexamples"], item["type_id"] + " 缺反例")
                self.assertTrue(item["boundaries"], item["type_id"] + " 缺相近类型边界")
            else:
                self.assertTrue(item["blocked_reason"], item["type_id"] + " 缺未实例化原因")

    def test_all_example_types_are_registered(self):
        registry = {t["type_id"] for t in load("registry/entity_types.json")["types"]}
        for name in ("examples/literature_bundle.json", "examples/hard_cases.json"):
            for mention in load(name)["mentions"]:
                for type_id in mention["candidate_type_ids"]:
                    self.assertIn(type_id, registry)

    def test_relation_signatures_are_complete(self):
        registry = load("registry/relations.json")["relations"]
        ids = [r["relation_id"] for r in registry]
        self.assertEqual(len(ids), len(set(ids)))
        for item in registry:
            self.assertLessEqual(item["cardinality"]["min_participants"], item["cardinality"]["max_participants"])
            self.assertIn(item["direction"], {"directed"})
            if item["status"] == "core":
                self.assertTrue(item["domain_types"] and item["range_types"], item["relation_id"])
            else:
                self.assertTrue(item["blocked_reason"], item["relation_id"])

    def test_vocab_closed_sets_match_schema(self):
        vocab = load("registry/vocab.json")["closed_sets"]
        defs = schema()["$defs"]
        paths = {
            "quantity.value_kind": ("quantity", ["value_kind"]),
            "quantity.unit_status": ("quantity", ["unit_status"]),
            "fact.statement_type": ("fact", ["statement_type"]),
            "fact.source_scope": ("fact", ["source_scope"]),
            "fact.polarity": ("fact", ["polarity"]),
            "fact.modality": ("fact", ["modality"]),
            "outcome.direction": ("outcome", ["direction"]),
            "outcome.magnitude.qualifier": ("magnitude", ["qualifier"]),
            "outcome.comparison.status": ("comparison", ["status"]),
            "identity.status": ("identity", ["status"]),
            "identity_merge.relation": ("identity_merge", ["relation"]),
            "identity_merge.basis": ("identity_merge", ["basis"]),
            "review": ("fact", ["review"]),
        }
        self.assertEqual(set(vocab), set(paths))
        for key, (def_name, fields) in paths.items():
            node = defs[def_name]["properties"]
            for field in fields[:-1]:
                node = node[field]["properties"]
            self.assertEqual(vocab[key], node[fields[-1]]["enum"], key)

    def test_identity_merge_fields_match_schema(self):
        rules = load("registry/identity_rules.json")
        required = set(schema()["$defs"]["identity_merge"]["required"])
        self.assertEqual(set(rules["merge_protocol"]["record_fields"]), required)

    def test_bundles_declare_current_schema_version(self):
        current = schema()["properties"]["schema_version"]["const"]
        for name in ("examples/literature_bundle.json", "examples/hard_cases.json"):
            self.assertEqual(load(name)["schema_version"], current)


class ConsumerContractTests(unittest.TestCase):
    def test_retrieval_keys_implemented(self):
        contract = load("registry/consumer_contract.json")
        expected = {key["key"] for key in contract["retrieval_keys"]}
        bundle = m.materialize(v.load(ROOT / "examples/hard_cases.json"))
        keys = m.retrieval_keys(bundle)
        self.assertEqual(set(keys["edge_keys"][0]["keys"]), expected)
        self.assertEqual({row["keys"]["review"] for row in keys["edge_keys"]}, {"pending"})

    def test_uses_are_independent_of_review(self):
        contract = load("registry/consumer_contract.json")
        self.assertNotIn("ranking", contract)
        self.assertEqual(set(contract["capabilities"]), {"cite", "numeric_comparison", "candidate_advice", "mechanism_analysis"})
        self.assertTrue(contract["blocked_uses"])


class NavigationTests(unittest.TestCase):
    def test_schema_declares_nine_items(self):
        nav = schema().get("x-nine-items") or []
        self.assertGreaterEqual(len(nav), 9)
        for item in nav:
            for key in ("item", "title", "where", "mechanism"):
                self.assertTrue(item.get(key), str(item))
        titles = " ".join(item["title"] for item in nav)
        for phrase in ("实体类型", "关系定义域与值域", "标识与唯一性", "属性表示边界", "受控词表",
                       "约束与处置", "上下文与 n-ary", "溯源与可信度", "演化与治理",
                       "消费端契约", "复用成熟标准"):
            self.assertIn(phrase, titles)

    def test_navigation_points_to_existing_files(self):
        for item in schema().get("x-nine-items") or []:
            for part in item["where"].split("+"):
                part = part.strip().split("#")[0]
                for token in part.split():
                    if token in ("identity_merges", "facts", "edges"):
                        continue
                    if token.startswith(("registry/", "schema/")):
                        self.assertTrue((ROOT / token).exists(), token)


if __name__ == "__main__":
    unittest.main(verbosity=1)
