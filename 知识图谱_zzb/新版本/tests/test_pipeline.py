"""两个真实根因的离线回归测试：
1) resolve_entities_llm 仅校验 ID+reason 后 union —— JGB/SPS 列表与理由矛盾仍被合并。
2) extraction schema 禁止 modality/polarity/source_scope，条件全部硬编码 qualitative。
不联网、不依赖 .local 配置；构建入口即本 package/scripts。
"""
import copy
import json
import sys
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG / "scripts"))
sys.path.insert(0, str(PKG / "construction"))

import merge_validation
import resolve_entities_llm
from condition_values import classify_condition, parse_numeric, parse_range
from extraction import ingest, prompt

WORK = PKG.parent
BLOCK_TEXT = (
    "The most commonly used accelerator is bis-(sodium sulfopropyl)- disulfide (SPS), "
    "and the leveler is Janus Green B (JGB). At 25 degC and a current density of 2 A/dm2, "
    "the deposit roughness was 0.8 um. SPS performs best at 10-20 ppm. "
    "The cathodic potential shifted by 42 mV. "
    "Additives at low and high concentration behaved differently. "
    "Bis-(sodium sulfopropyl)- disulfide accelerated deposition at 5 ppm."
)


def make_bundle():
    return {
        "schema_version": "4.0.0-draft",
        "documents": [{"id": "doc1", "title": "t", "source_file": "f", "sha256": "a" * 64,
                        "source_kind": "other"}],
        "blocks": [{"id": "blk1", "document_id": "doc1", "text": BLOCK_TEXT,
                     "page": 1, "section": "s"}],
        "mentions": [], "facts": [], "edges": [], "entities": [],
        "identities": [], "identity_links": [], "identity_merges": [],
        "role_assignments": [], "experiments": [], "runs": [], "samples": [],
    }


class MergeGateTests(unittest.TestCase):
    def setUp(self):
        self.jgb_context = (
            "6 The most commonly used accelerator, suppressor, and leveler is "
            "bis-(sodium sulfopropyl)- disulfide (SPS), polyethylene glycol (PEG), "
            "and Janus Green B (JGB). 17 During electroplating, density functional theory (DF")
        self.sps_context = (
            "etry (MS) and DFT calculations demonstrate that the azo group of JGB competes with "
            "the reduction of Cu ^2 + to obtain electrons, leading to dissociation 24,25")
        self.rows = [
            {"id": "n05903", "document_id": "d4", "label": "JGB",
             "canonical_label": "Janus Green B (JGB)", "kind": "chemical",
             "distinctions": [], "contexts": [
                 {"source_id": "blk:a", "start": 801, "text": "the azo group of JGB competes"}]},
            {"id": "n05934", "document_id": "d4",
             "label": "bis-(sodium sulfopropyl)- disulfide",
             "canonical_label": "Bis-(sodium sulfopropyl) disulfide", "kind": "chemical",
             "distinctions": [], "contexts": [
                 {"source_id": "blk:b", "start": 1, "text": self.jgb_context}]},
        ]
        self.indexed = {r["id"]: r for r in self.rows}

    def _apply(self, proposals):
        return resolve_entities_llm.apply_merges(copy.deepcopy(self.rows), proposals, "document")

    # ---- 根因1：JGB/SPS 列表与理由矛盾必须拒收，不得 union ----
    def test_jgb_sps_contradictory_reason_rejected(self):
        proposal = {"ids": ["n05903", "n05934"], "decision": "merge",
                    "reason": ("n05934 is the full chemical name for SPS, but n05903 is JGB. "
                               "Wait, n05903 is JGB. These are different chemicals."),
                    "evidence": [{"source_id": "blk:b",
                                  "quote": "bis-(sodium sulfopropyl)- disulfide (SPS), polyethylene glycol (PEG), and Janus Green B (JGB)"}]}
        groups, accepted, rejected, not_merged = self._apply([proposal])
        self.assertEqual(accepted, [])
        self.assertEqual(len(groups), 2, "矛盾提案不得改变分组")
        self.assertTrue(any("矛盾" in r.get("rejection", "") or "拒收" in r.get("rejection", "")
                            or "措辞" in r.get("rejection", "") for r in rejected), rejected)

    def test_reason_names_member_as_different_rejected(self):
        proposal = {"ids": ["n05903", "n05934"], "decision": "merge",
                    "reason": "n05903 is JGB and n05934 is SPS; these are different chemicals, do not merge",
                    "evidence": [{"source_id": "blk:b", "quote": self.jgb_context[3:60]}]}
        groups, accepted, rejected, _ = self._apply([proposal])
        self.assertEqual(accepted, [])
        self.assertEqual(len(groups), 2)

    # ---- keep_separate / uncertain 不 union ----
    def test_keep_separate_no_union(self):
        proposal = {"ids": ["n05903", "n05934"], "decision": "keep_separate",
                    "reason": "不同物质，保留独立"}
        groups, accepted, rejected, not_merged = self._apply([proposal])
        self.assertEqual(accepted, [])
        self.assertEqual(rejected, [])
        self.assertEqual(len(not_merged), 1)
        self.assertEqual(len(groups), 2)

    def test_uncertain_no_union(self):
        proposal = {"ids": ["n05903", "n05934"], "decision": "uncertain",
                    "reason": "证据不足，待核"}
        groups, accepted, rejected, not_merged = self._apply([proposal])
        self.assertEqual(accepted, [])
        self.assertEqual(len(groups), 2)

    # ---- 未知 ID / 缺证据 / 伪证据拒绝 ----
    def test_unknown_id_rejected(self):
        proposal = {"ids": ["n05903", "n99999"], "decision": "merge",
                    "reason": "同一物质",
                    "evidence": [{"source_id": "blk:b", "quote": "SPS"}]}
        groups, accepted, rejected, _ = self._apply([proposal])
        self.assertEqual(accepted, [])
        self.assertTrue(any("未知ID" in r.get("rejection", "") for r in rejected), rejected)

    def test_missing_evidence_rejected(self):
        proposal = {"ids": ["n05903", "n05934"], "decision": "merge",
                    "reason": "同一物质"}
        groups, accepted, rejected, _ = self._apply([proposal])
        self.assertEqual(accepted, [])
        self.assertTrue(any("证据" in r.get("rejection", "") for r in rejected), rejected)

    def test_fabricated_evidence_rejected(self):
        proposal = {"ids": ["n05903", "n05934"], "decision": "merge",
                    "reason": "同一物质",
                    "evidence": [{"source_id": "blk:b", "quote": "SPS and JGB are the same molecule"}]}
        groups, accepted, rejected, _ = self._apply([proposal])
        self.assertEqual(accepted, [])
        self.assertTrue(any("不对应" in r.get("rejection", "") for r in rejected), rejected)

    def test_wrong_source_id_rejected(self):
        proposal = {"ids": ["n05903", "n05934"], "decision": "merge",
                    "reason": "同一物质",
                    "evidence": [{"source_id": "blk:zzz", "quote": "SPS"}]}
        groups, accepted, rejected, _ = self._apply([proposal])
        self.assertEqual(accepted, [])

    # ---- 旧式无 decision 提案不得默默 merge ----
    def test_legacy_shape_pending_not_merged(self):
        proposal = {"ids": ["n05903", "n05934"], "reason": "same normalized label"}
        groups, accepted, rejected, _ = self._apply([proposal])
        self.assertEqual(accepted, [])
        self.assertEqual(len(groups), 2)

    # ---- 可信定义同义通过：全称(缩写) 定义句逐字在 contexts 中 ----
    def test_credible_defined_synonym_merge_passes(self):
        n1 = {"id": "n00001", "document_id": "d4", "label": "SPS",
              "canonical_label": "SPS", "kind": "chemical", "distinctions": [],
              "contexts": [{"source_id": "blk:b", "start": 1, "text": self.jgb_context}]}
        n2 = {"id": "n00002", "document_id": "d4", "label": "bis-(sodium sulfopropyl)- disulfide",
              "canonical_label": "Bis-(sodium sulfopropyl) disulfide", "kind": "chemical",
              "distinctions": [],
              "contexts": [{"source_id": "blk:b", "start": 1, "text": self.jgb_context}]}
        proposal = {"ids": ["n00001", "n00002"], "decision": "merge", "basis": "source_definition",
                    "reason": "作者明确定义全称缩写：bis-(sodium sulfopropyl)- disulfide (SPS)",
                    "evidence": [{"source_id": "blk:b",
                                  "quote": "bis-(sodium sulfopropyl)- disulfide (SPS)"}]}
        groups, accepted, rejected, _ = resolve_entities_llm.apply_merges([n1, n2], [proposal], "document")
        self.assertEqual(len(accepted), 1, rejected)
        self.assertEqual(len(groups), 1)

    # ---- cross 阶段同样覆盖：decision=merge 无证据拒收 ----
    def test_cross_phase_gate(self):
        ok, why = merge_validation.gate_proposal(
            {"ids": ["n05903", "n05934"], "decision": "merge", "reason": "同一概念"},
            self.indexed, ["n05903", "n05934"], phase="cross")
        self.assertFalse(ok)
        self.assertIn("证据", why)

    # ---- 原有 incompatible 约束保留：规格冲突拒收 ----
    def test_incompatible_distinction_still_rejected(self):
        n1 = dict(self.rows[0], distinctions=[{"variant:mw": "8000"}])
        n2 = dict(self.rows[1], distinctions=[{"variant:mw": "20000"}])
        rows = [n1, n2]
        proposal = {"ids": ["n05903", "n05934"], "decision": "merge",
                    "reason": "同一物质",
                    "evidence": [{"source_id": "blk:b", "quote": self.jgb_context[3:60]}]}
        groups, accepted, rejected, _ = resolve_entities_llm.apply_merges(rows, [proposal], "document")
        self.assertEqual(accepted, [])


class ConditionValueTests(unittest.TestCase):
    def test_single_number_with_unit(self):
        q = classify_condition("2", "a current density of 2 A/dm2", "A/dm2")
        self.assertEqual(q["value_kind"], "numeric")
        self.assertEqual(q["unit_raw"], "A/dm2")
        self.assertEqual(q["unit_status"], "reported")

    def test_range(self):
        q = classify_condition("10-20", "SPS performs best at 10-20 ppm", "ppm")
        self.assertEqual(q["value_kind"], "range")
        self.assertEqual(q["unit_raw"], "ppm")
        self.assertEqual(q["value_raw"], "10-20")

    def test_potential_noun_no_unit_stays_qualitative(self):
        # 电势名词但原文无单位（仅数字）：不推断省略单位
        q = classify_condition("42", "The cathodic potential shifted by 42", None)
        self.assertEqual(q["value_kind"], "qualitative")

    def test_potential_with_unit_numeric(self):
        q = classify_condition("42", "The cathodic potential shifted by 42 mV", "mV")
        self.assertEqual(q["value_kind"], "numeric")
        self.assertEqual(q["unit_raw"], "mV")

    def test_multi_value_kept_qualitative(self):
        # 多浓度/逐浓度表保持原样
        q = classify_condition("low and high", "Additives at low and high concentration", None)
        self.assertEqual(q["value_kind"], "qualitative")
        self.assertEqual(q["value_raw"], "low and high")

    def test_unit_not_verbatim_dropped(self):
        q = classify_condition("2", "a current density of 2", "A/dm2")
        self.assertNotEqual(q["unit_raw"], "A/dm2")

    def test_parse_numeric_rejects_multiple(self):
        self.assertIsNone(parse_numeric("10 and 20", "at 10 and 20 ppm"))

    def test_parse_range_rejects_multiple_ranges(self):
        self.assertIsNone(parse_range("10-20 and 30-40", "at 10-20 and 30-40 ppm"))


class ExtractionSemanticTests(unittest.TestCase):
    def test_semantic_fields_land_in_fact(self):
        response = {"facts": [{
            "subject": "SPS", "relation": "effect", "statement": "observation",
            "modality": "explicit", "polarity": "asserted", "source_scope": "this_study",
            "quote": "SPS performs best at 10-20 ppm",
            "conditions": [{"parameter": "concentration", "value": "10-20", "unit": "ppm",
                             "kind": "range", "about": "subject",
                             "quote": "SPS performs best at 10-20 ppm"}],
            "outcomes": []}]}
        result = ingest(make_bundle(), "blk1", response, model="test-model")
        fact = result["facts"][0]
        self.assertEqual(fact["modality"], "explicit")
        self.assertEqual(fact["polarity"], "asserted")
        self.assertEqual(fact["source_scope"], "this_study")
        cond = fact["conditions"][0]
        self.assertEqual(cond["value"]["value_kind"], "range")
        self.assertEqual(cond["value"]["unit_raw"], "ppm")
        self.assertEqual(cond["value"]["value_raw"], "10-20")

    def test_old_response_defaults_unknown(self):
        response = {"facts": [{
            "subject": "Bis-(sodium sulfopropyl)- disulfide", "relation": "effect", "statement": "observation",
            "quote": "Bis-(sodium sulfopropyl)- disulfide accelerated deposition at 5 ppm"}]}
        result = ingest(make_bundle(), "blk1", response, model="m")
        fact = result["facts"][0]
        self.assertEqual(fact["modality"], "unknown")
        self.assertEqual(fact["polarity"], "unknown")
        self.assertEqual(fact["source_scope"], "unknown")

    def test_condition_numeric_lands(self):
        response = {"facts": [{
            "subject": "Bis-(sodium sulfopropyl)- disulfide", "relation": "effect", "statement": "observation",
            "quote": "Bis-(sodium sulfopropyl)- disulfide accelerated deposition at 5 ppm",
            "conditions": [{"parameter": "current density", "value": "2", "unit": "A/dm2",
                             "kind": "numeric", "about": "experiment",
                             "quote": "a current density of 2 A/dm2"}],
            "outcomes": [{"indicator": "roughness", "value": "0.8", "kind": "numeric",
                           "unit": "um", "quote": "the deposit roughness was 0.8 um"}]}]}
        result = ingest(make_bundle(), "blk1", response, model="m")
        cond = result["facts"][0]["conditions"][0]
        self.assertEqual(cond["value"]["value_kind"], "numeric")
        self.assertEqual(cond["value"]["unit_raw"], "A/dm2")

    def test_condition_multi_value_kept(self):
        response = {"facts": [{
            "subject": "Bis-(sodium sulfopropyl)- disulfide", "relation": "effect", "statement": "observation",
            "quote": "Additives at low and high concentration behaved differently",
            "conditions": [{"parameter": "concentration", "value": "low and high",
                             "quote": "Additives at low and high concentration"}],
            "outcomes": []}]}
        result = ingest(make_bundle(), "blk1", response, model="m")
        cond = result["facts"][0]["conditions"][0]
        self.assertEqual(cond["value"]["value_kind"], "qualitative")
        self.assertEqual(cond["value"]["value_raw"], "low and high")

    def test_prompt_advertises_semantic_fields(self):
        text = prompt({"text": BLOCK_TEXT})
        for token in ("modality", "polarity", "source_scope", "kind"):
            self.assertIn(token, text)

    def test_bundle_still_validates_after_ingest(self):
        response = {"facts": [{
            "subject": "Bis-(sodium sulfopropyl)- disulfide", "relation": "effect", "statement": "observation",
            "quote": "Bis-(sodium sulfopropyl)- disulfide accelerated deposition at 5 ppm",
            "conditions": [{"parameter": "concentration", "value": "5", "unit": "ppm",
                             "quote": "accelerated deposition at 5 ppm"}],
            "outcomes": []}]}
        result = ingest(make_bundle(), "blk1", response, model="m")
        self.assertTrue(result["facts"][0]["conditions"][0]["value"]["value_kind"] in
                        ("numeric", "qualitative"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
