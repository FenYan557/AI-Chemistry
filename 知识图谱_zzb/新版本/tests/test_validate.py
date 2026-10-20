"""契约与校验规则测试；只验证结构与本地规则，不验证化学语义正确性。"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate as v  # noqa: E402


def base_bundle():
    return v.load(ROOT / "examples/literature_bundle.json")


def hard():
    return v.load(ROOT / "examples/hard_cases.json")


def codes(result):
    return {e["code"] for e in result["errors"]}


def warn_codes(result):
    return {w["code"] for w in result["warnings"]}


def all_codes(result):
    return codes(result) | warn_codes(result)


def anneal(bundle):
    return next(f for f in bundle["facts"] if f["id"] == "h:annealed_resistivity")


class ContractTests(unittest.TestCase):
    def test_example_bundle_is_valid(self):
        result = v.validate(base_bundle())
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["valid"])
        self.assertFalse(result["semantics_verified"])

    def test_quote_must_be_literal(self):
        b = base_bundle()
        b["mentions"][0]["evidence"]["quote"] = "Adenosine (a modified spelling)"
        self.assertIn("QUOTE_MISMATCH", codes(v.validate(b)))

    def test_mention_surface_must_match_quote(self):
        b = base_bundle()
        b["mentions"][0]["surface"] = "adenosine"
        result = v.validate(b)
        self.assertIn("MENTION_SURFACE_MISMATCH", codes(result))

    def test_name_only_merge_is_rejected(self):
        b = base_bundle()
        b["identities"][0]["status"] = "reviewed"
        b["identity_links"][0]["review"] = "reviewed"
        b["identity_links"][0]["basis"] = "name_candidate"
        self.assertIn("NAME_ONLY_IDENTITY_MERGE", codes(v.validate(b)))

    def test_document_alias_cannot_become_global_identity(self):
        b = base_bundle()
        b["identities"][0]["scope"] = "global"
        b["identities"][0]["document_id"] = None
        b["identities"][0]["status"] = "reviewed"
        b["identity_links"][0]["review"] = "reviewed"
        self.assertIn("GLOBAL_ALIAS_NEEDS_IDENTITY_EVIDENCE", codes(v.validate(b)))

    def test_unit_state_must_be_consistent(self):
        b = base_bundle()
        b["facts"][0]["conditions"][0]["value"]["unit_status"] = "reported"
        b["facts"][0]["conditions"][0]["value"]["unit_raw"] = None
        self.assertIn("UNIT_STATE_INCONSISTENT", codes(v.validate(b)))

    def test_outcome_value_must_exist_in_cited_evidence(self):
        b = base_bundle()
        b["facts"][3]["outcomes"][0]["value"]["value_raw"] = "99.9"
        self.assertIn("OUTCOME_VALUE_NOT_LITERAL", codes(v.validate(b)))

    def test_other_role_requires_raw_wording(self):
        b = base_bundle()
        role = next(r for r in b["role_assignments"] if r["functional_role"] == "other")
        role["role_raw"] = None
        self.assertIn("ROLE_OTHER_NEEDS_RAW", warn_codes(v.validate(b)))

    def test_unknown_role_requires_unknown_basis(self):
        b = base_bundle()
        role = next(r for r in b["role_assignments"] if r["functional_role"] == "unknown")
        role["role_basis"] = "author_explicit"
        role["role_raw"] = "some role"
        self.assertIn("ROLE_UNKNOWN_BASIS", warn_codes(v.validate(b)))

    def test_role_subject_must_participate_in_fact(self):
        b = base_bundle()
        b["role_assignments"][0]["subject_mention_id"] = "m:na"
        self.assertIn("ROLE_SUBJECT_NOT_PARTICIPANT", codes(v.validate(b)))

    def test_duplicate_role_is_rejected(self):
        b = base_bundle()
        b["role_assignments"].append(copy.deepcopy(b["role_assignments"][0]))
        b["role_assignments"][-1]["id"] = "role:duplicate"
        self.assertIn("ROLE_DUPLICATE", codes(v.validate(b)))

    def test_condition_split_keeps_both_directions(self):
        b = base_bundle()
        result = v.validate(b)
        roles = {(r["fact_id"], r["functional_role"]) for r in b["role_assignments"]}
        self.assertIn(("f:ado:low", "accelerator"), roles)
        self.assertIn(("f:ado:high", "suppressor"), roles)
        self.assertEqual(result["roles"].get("accelerator"), 1)
        self.assertEqual(result["roles"].get("suppressor"), 1)

    def test_future_work_role_is_retained_with_warning(self):
        result = v.validate(base_bundle())
        self.assertTrue(result["valid"])
        self.assertIn("ROLE_ON_FUTURE_WORK", warn_codes(result))

    def test_unknown_role_is_not_reported_as_comparison_ready(self):
        result = v.validate(base_bundle())
        for fact in result["facts"]:
            self.assertEqual(fact["recommendation"], "not_assessed")

    def test_review_tier_retains_record_without_blocking(self):
        b = base_bundle()
        role = next(r for r in b["role_assignments"] if r["functional_role"] == "other")
        role["role_raw"] = None
        result = v.validate(b)
        self.assertTrue(result["valid"])
        self.assertEqual(result["tier_counts"]["block"], 0)
        self.assertGreaterEqual(result["tier_counts"]["review"], 1)


class TableRunSampleTests(unittest.TestCase):
    def test_hard_cases_are_valid(self):
        self.assertEqual(v.validate(hard())["errors"], [])

    def test_table_cell_must_match_real_csv(self):
        b = hard()
        b["runs"][0]["conditions"][0]["evidence"][0]["cell_raw"] = "80 °C, 15 min (wrong)"
        self.assertIn("TABLE_CELL_MISMATCH", codes(v.validate(b)))

    def test_table_cell_out_of_range(self):
        b = hard()
        b["runs"][0]["conditions"][0]["evidence"][0].update({"row": 999})
        self.assertIn("TABLE_CELL_OUT_OF_RANGE", codes(v.validate(b)))

    def test_inherited_condition_requires_run(self):
        b = hard()
        anneal(b)["run_id"] = None
        self.assertIn("INHERITED_CONDITION_WITHOUT_RUN", codes(v.validate(b)))

    def test_inherited_condition_value_must_match_run(self):
        b = hard()
        anneal(b)["conditions"][0]["value"]["value_raw"] = "5 mg·L –1"
        self.assertIn("INHERITED_CONDITION_VALUE_MISMATCH", codes(v.validate(b)))

    def test_inherited_condition_must_exist_on_run(self):
        b = hard()
        anneal(b)["conditions"][0]["parameter_raw"] = "pH"
        self.assertIn("INHERITED_CONDITION_NOT_IN_RUN", codes(v.validate(b)))

    def test_sample_binding_must_exist(self):
        b = hard()
        anneal(b)["outcomes"][0]["sample_id"] = "s:missing"
        self.assertIn("SAMPLE_MISSING", codes(v.validate(b)))

    def test_sample_parent_must_exist(self):
        b = hard()
        b["samples"][1]["derived_from_sample_id"] = "s:missing"
        self.assertIn("SAMPLE_PARENT_MISSING", codes(v.validate(b)))


class GraphLayerTests(unittest.TestCase):
    def test_entities_cover_mentions(self):
        b = hard()
        self.assertEqual(len(b["entities"]), len(b["mentions"]))
        self.assertEqual({e["from_mention_id"] for e in b["entities"]}, {m["id"] for m in b["mentions"]})

    def test_open_facts_do_not_become_assertion_edges(self):
        b = hard()
        edged = {e["fact_id"] for e in b["edges"]}
        self.assertIn("h:adsorption", edged)
        self.assertNotIn("h:methods", edged)
        self.assertNotIn("h:post_cmp_prediction", edged)

    def test_edge_copies_fact_qualifiers(self):
        b = hard()
        facts = {f["id"]: f for f in b["facts"]}
        for edge in b["edges"]:
            fact = facts[edge["fact_id"]]
            self.assertEqual(edge["qualifiers"]["statement_type"], fact["statement_type"])
            self.assertEqual(edge["qualifiers"]["polarity"], fact["polarity"])
            self.assertEqual(edge["qualifiers"]["conditions"], fact["conditions"])

    def test_edge_semantics_drift_is_blocked(self):
        b = hard()
        edge = next(e for e in b["edges"] if e["fact_id"] == "h:adsorption")
        edge["qualifiers"]["polarity"] = "negated"
        self.assertIn("EDGE_SEMANTICS_DRIFT", codes(v.validate(b)))

    def test_edge_relation_drift_is_blocked(self):
        b = hard()
        edge = next(e for e in b["edges"] if e["fact_id"] == "h:adsorption")
        edge["relation"]["raw"] = "some other wording"
        self.assertIn("EDGE_SEMANTICS_DRIFT", codes(v.validate(b)))

    def test_entity_label_mismatch_is_blocked(self):
        b = hard()
        b["entities"][0]["label"] = "not the surface"
        self.assertIn("ENTITY_LABEL_MISMATCH", codes(v.validate(b)))

    def test_missing_edge_is_audited(self):
        b = hard()
        b["edges"] = [e for e in b["edges"] if e["fact_id"] != "h:adsorption"]
        self.assertIn("EDGE_COVERAGE_GAP", warn_codes(v.validate(b)))

    def test_relation_range_mismatch_is_review(self):
        b = hard()
        fact = next(f for f in b["facts"] if f["id"] == "h:adsorption")
        edge = next(e for e in b["edges"] if e["fact_id"] == "h:adsorption")
        fact["relation"]["candidate_relation_id"] = "r7"
        fact["participants"] = [{"mention_id": "m:saccharin", "role": "agent"},
                                 {"mention_id": "m:anneal", "role": "affected_property"}]
        next(m for m in b["mentions"] if m["id"] == "m:anneal")["candidate_type_ids"] = ["t29"]
        from materialize import materialize
        materialize(b)
        result = v.validate(b)
        self.assertIn("EDGE_RANGE_MISMATCH", warn_codes(result))
        self.assertEqual(result["tier_counts"]["block"], 0)

    def test_relation_cardinality_is_review(self):
        b = hard()
        fact = next(f for f in b["facts"] if f["id"] == "h:adsorption")
        edge = next(e for e in b["edges"] if e["fact_id"] == "h:adsorption")
        fact["relation"]["candidate_relation_id"] = "r5"
        edge["relation"]["candidate_relation_id"] = "r5"
        self.assertIn("EDGE_CARDINALITY", warn_codes(v.validate(b)))

    def test_proposed_relation_is_review(self):
        b = hard()
        fact = next(f for f in b["facts"] if f["id"] == "h:adsorption")
        edge = next(e for e in b["edges"] if e["fact_id"] == "h:adsorption")
        fact["relation"]["candidate_relation_id"] = "r1"
        edge["relation"]["candidate_relation_id"] = "r1"
        self.assertIn("EDGE_RELATION_PROPOSED", warn_codes(v.validate(b)))

    def test_untyped_entity_is_audited(self):
        b = hard()
        entity = next(e for e in b["entities"] if e["from_mention_id"] == "m:method"
                      ) if any(e["from_mention_id"] == "m:method" for e in b["entities"]) else b["entities"][0]
        entity["type_id"] = None
        self.assertIn("ENTITY_UNTYPED", warn_codes(v.validate(b)))

    def test_proposed_type_is_review(self):
        b = hard()
        entity = next(e for e in b["entities"] if e["from_mention_id"] == "m:grain_refine")
        self.assertIsNone(entity["type_id"])
        mention = next(m for m in b["mentions"] if m["id"] == "m:grain_refine")
        self.assertEqual(mention["candidate_type_ids"], ["t34"])
        entity["type_id"] = "t34"
        self.assertIn("ENTITY_TYPE_UNDERSPECIFIED", warn_codes(v.validate(b)))

    def test_unknown_entity_type_is_review(self):
        b = hard()
        b["entities"][0]["type_id"] = "t999"
        self.assertIn("ENTITY_TYPE_UNKNOWN", warn_codes(v.validate(b)))

    def test_merge_same_as_requires_reviewed_identities(self):
        b = hard()
        merge = next(m for m in b["identity_merges"] if m["id"] == "merge:plane-facet")
        merge["review"] = "reviewed"
        self.assertIn("MERGE_UNVERIFIED_SAME_AS", codes(v.validate(b)))

    def test_merge_same_as_cross_document_is_blocked(self):
        b = hard()
        b["identities"][0]["status"] = "reviewed"
        b["identities"][1]["status"] = "reviewed"
        merge = next(m for m in b["identity_merges"] if m["id"] == "merge:plane-facet")
        merge["basis"] = "author_explicit"
        merge["review"] = "reviewed"
        self.assertIn("MERGE_CROSS_DOCUMENT_UNREVIEWED", codes(v.validate(b)))

    def test_merge_contradiction_is_blocked(self):
        b = hard()
        extra = copy.deepcopy(next(m for m in b["identity_merges"] if m["id"] == "merge:plane-texture"))
        extra.update({"id": "merge:contradiction", "relation": "distinct_from"})
        extra["from_identity_id"] = "identity:doc:facet002"
        extra["to_identity_id"] = "identity:doc:plane002"
        b["identity_merges"].append(extra)
        self.assertIn("MERGE_CONTRADICTION", codes(v.validate(b)))

    def test_merge_self_is_blocked(self):
        b = hard()
        merge = next(m for m in b["identity_merges"] if m["id"] == "merge:plane-facet")
        merge["to_identity_id"] = merge["from_identity_id"]
        self.assertIn("MERGE_SELF", codes(v.validate(b)))

    def test_merge_identity_missing_is_blocked(self):
        b = hard()
        b["identity_merges"][0]["to_identity_id"] = "identity:missing"
        self.assertIn("MERGE_IDENTITY_MISSING", codes(v.validate(b)))


class ContextTests(unittest.TestCase):
    def test_magnitude_requires_raw(self):
        b = hard()
        outcome = next(o for f in b["facts"] for o in f["outcomes"] if o["magnitude"]["qualifier"] == "slight")
        outcome["magnitude"]["raw"] = None
        self.assertIn("MAGNITUDE_WITHOUT_RAW", codes(v.validate(b)))

    def test_magnitude_raw_not_literal_is_audited(self):
        b = hard()
        outcome = next(o for f in b["facts"] for o in f["outcomes"] if o["magnitude"]["qualifier"] == "slight")
        outcome["magnitude"]["raw"] = "somewhat"
        self.assertIn("MAGNITUDE_RAW_NOT_LITERAL", warn_codes(v.validate(b)))

    def test_comparison_baseline_required(self):
        b = hard()
        anneal(b)["outcomes"][0]["comparison"]["baseline_raw"] = None
        self.assertIn("COMPARISON_BASELINE_MISSING", codes(v.validate(b)))

    def test_comparison_baseline_must_be_absent_when_not_stated(self):
        b = hard()
        anneal(b)["outcomes"][0]["comparison"]["status"] = "not_stated"
        self.assertIn("COMPARISON_BASELINE_MISSING", codes(v.validate(b)))

    def test_comparison_mention_must_be_a_participant(self):
        b = hard()
        anneal(b)["outcomes"][0]["comparison"]["baseline_mention_id"] = "m:na"
        self.assertIn("COMPARISON_MENTION_NOT_PARTICIPANT", warn_codes(v.validate(b)))

    def test_cited_work_missing_is_review(self):
        b = hard()
        fact = next(f for f in b["facts"] if f["id"] == "h:purity_hedged")
        fact["source_scope"] = "cited_study"
        self.assertIn("CITED_WORK_MISSING", warn_codes(v.validate(b)))

    def test_cited_work_unexpected_is_review(self):
        b = hard()
        fact = next(f for f in b["facts"] if f["id"] == "h:purity_hedged")
        fact["cited_work"] = {"raw": "Smith et al. 2010", "document_id": None, "reference_raw": None}
        self.assertIn("CITED_WORK_UNEXPECTED", warn_codes(v.validate(b)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
