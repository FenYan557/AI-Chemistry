"""物化层测试：实体/边可由记录层确定地重建，且不新增语义。"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import materialize as m  # noqa: E402
import validate as v  # noqa: E402


def base_bundle():
    return v.load(ROOT / "examples/literature_bundle.json")


def hard():
    return v.load(ROOT / "examples/hard_cases.json")


class MaterializeTests(unittest.TestCase):
    def test_materialize_is_deterministic(self):
        first = m.materialize(copy.deepcopy(hard()))
        second = m.materialize(copy.deepcopy(hard()))
        self.assertEqual(json.dumps(first["entities"], sort_keys=True, ensure_ascii=False),
                         json.dumps(second["entities"], sort_keys=True, ensure_ascii=False))
        self.assertEqual(json.dumps(first["edges"], sort_keys=True, ensure_ascii=False),
                         json.dumps(second["edges"], sort_keys=True, ensure_ascii=False))

    def test_entity_ids_are_derived_from_mentions(self):
        bundle = m.materialize(copy.deepcopy(hard()))
        self.assertEqual({e["id"] for e in bundle["entities"]},
                         {"ent:" + mention["id"] for mention in bundle["mentions"]})

    def test_edge_ids_are_stable_format(self):
        bundle = m.materialize(copy.deepcopy(hard()))
        for edge in bundle["edges"]:
            self.assertTrue(edge["id"].startswith("edge:" + edge["fact_id"] + ":"))

    def test_pending_identity_link_is_not_applied(self):
        bundle = m.materialize(copy.deepcopy(base_bundle()))
        self.assertTrue(all(e["identity_id"] is None for e in bundle["entities"]))

    def test_reviewed_identity_link_is_applied(self):
        data = copy.deepcopy(base_bundle())
        data["identities"][0]["status"] = "reviewed"
        for link in data["identity_links"]:
            link["review"] = "reviewed"
        bundle = m.materialize(data)
        linked = {e["from_mention_id"]: e["identity_id"] for e in bundle["entities"]}
        self.assertEqual(linked.get("m:ado"), "identity:doc:ado")
        self.assertEqual(linked.get("m:adenosine"), "identity:doc:ado")

    def test_edges_carry_no_new_semantics(self):
        bundle = m.materialize(copy.deepcopy(hard()))
        facts = {f["id"]: f for f in bundle["facts"]}
        for edge in bundle["edges"]:
            fact = facts[edge["fact_id"]]
            self.assertEqual(edge["qualifiers"]["conditions"], fact["conditions"])
            self.assertEqual(edge["qualifiers"]["modality"], fact["modality"])
            self.assertEqual(edge["evidence"], fact["evidence"])
            self.assertEqual(edge["review"], fact["review"])
            self.assertEqual(edge["relation"], fact["relation"])

    def test_materialize_clears_previous_view(self):
        bundle = m.materialize(copy.deepcopy(hard()))
        before = len(bundle["edges"])
        bundle["edges"] = bundle["edges"] + [{"stale": True}]
        m.materialize(bundle)
        self.assertEqual(len(bundle["edges"]), before)


class RetrievalKeyTests(unittest.TestCase):
    def test_keys_match_consumer_contract(self):
        contract = json.loads((ROOT / "registry/consumer_contract.json").read_text(encoding="utf-8"))
        expected = {key["key"] for key in contract["retrieval_keys"]}
        bundle = m.materialize(copy.deepcopy(hard()))
        keys = m.retrieval_keys(bundle)
        self.assertEqual(len(keys["edge_keys"]), len(bundle["edges"]))
        self.assertEqual(keys["edges_without_fact"], [])
        for row in keys["edge_keys"]:
            self.assertEqual(set(row["keys"]), expected)

    def test_edge_keys_are_derived_not_asserted(self):
        bundle = m.materialize(copy.deepcopy(hard()))
        keys = m.retrieval_keys(bundle)
        facts = {f["id"]: f for f in bundle["facts"]}
        for row in keys["edge_keys"]:
            fact_id = row["edge_id"][len("edge:"):].rsplit(":", 1)[0]
            self.assertIn(fact_id, facts)
            self.assertEqual(row["keys"]["review"], facts[fact_id]["review"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
