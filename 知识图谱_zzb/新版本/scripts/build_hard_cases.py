"""困难样例：用真实原文片段检验协议的表达力边界。\n\n所有 quote 均为 4 个快照块的逐字子串；不含编造文献内容。\n目的是暴露协议缺口，不是展示抽取效果。\n"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import materialize


def span(block, quote):
    text = next(b["text"] for b in base["blocks"] if b["id"] == block["id"])
    start = text.index(quote)
    return {"kind": "block", "block_id": block["id"], "start": start, "end": start + len(quote), "quote": quote}


def q(raw, unit=None, status="not_applicable", kind="qualitative"):
    return {"value_raw": raw, "value_kind": kind, "unit_raw": unit, "unit_status": status}


base = json.loads((ROOT / "examples/literature_bundle.json").read_text(encoding="utf-8"))
base["role_assignments"] = []
base["facts"] = []
base["mentions"] = []
base["identities"] = []
base["identity_links"] = []
b0, b2, b3 = base["blocks"][0], base["blocks"][2], base["blocks"][3]
doc_ado, doc_film, doc_cmp = b0["document_id"], b2["document_id"], b3["document_id"]


def mention(mid, block, surface, types=None):
    base["mentions"].append({"id": mid, "document_id": block["document_id"], "surface": surface,
                             "evidence": span(block, surface), "candidate_type_ids": types or []})


mention("m:dft", b0, "density functional theory calculations", ["t22"])
mention("m:md", b0, "molecular dynamics (MD) simulation", ["t22"])
mention("m:eftir", b0, "electrochemical in situ Fourier transform infrared (E-FTIR) spectroscopy tests", ["t23"])
mention("m:ado", b0, "ADO", ["t1"])
mention("m:grain_refine", b0, "grain refinement effect", ["t34"])
mention("m:plane002", b0, "Co hcp (002) crystalline plane", ["t9"])
mention("m:saccharin", b2, "saccharin", ["t1"])
mention("m:grain_size", b2, "grain size", ["t14"])
mention("m:stone_forest", b2, "“stone forest” structure", ["t13"])
mention("m:purity", b2, "purity of cobalt coating", ["t16"])
mention("m:c_sites", b2, "specific c-sites on the cobalt dense crystal plane", ["t8"])
mention("m:stacking", b2, "the growth of abc stacking arrangement", ["t11"])
mention("m:facet002", b2, "(002) facet", ["t9"])
mention("m:texture_hcp002", b2, "HCP (002) texture", ["t12"])
mention("m:na", b3, "NA", ["t1"])
mention("m:post_cmp", b3, "post CMP cleaning", ["t30"])

facts = []


def fact(fid, block, relation_raw, definition, participants, quote, statement_type, *, scope="this_study",
         polarity="asserted", modality="explicit", conditions=None, outcomes=None, notes=None, group=None,
         relation_id=None):
    facts.append({
        "id": fid, "document_id": block["document_id"], "group_id": group,
        "relation": {"raw": relation_raw, "definition": definition, "candidate_relation_id": relation_id},
        "participants": [{"mention_id": m, "role": r} for m, r in participants],
        "conditions": conditions or [], "outcomes": outcomes or [],
        "statement_type": statement_type, "source_scope": scope, "polarity": polarity,
        "modality": modality, "evidence": [span(block, quote)], "review": "pending",
        "extraction": {"method": "deterministic_protocol_example_mapping", "model": None,
                       "protocol_version": "v3-hardcases-1"},
        "notes": notes or ["真实片段按协议手工映射，用于检验表达力；不是模型抽取或金标。"],
    })


# 1) 计算/模拟结果：三种方法共同研究的对象与现象
fact("h:methods", b0, "was investigated using",
     "以多种方法研究同一吸附行为；方法为手段而非结论。",
     [("m:ado", "studied_substance"), ("m:dft", "method"), ("m:md", "method"), ("m:eftir", "method")],
     "The adsorption behavior of ADO on the cobalt surface was investigated using density functional theory calculations, molecular dynamics (MD) simulation, and electrochemical in situ Fourier transform infrared (E-FTIR) spectroscopy tests.",
     "calculation_result")

# 2) 一句双结果：晶粒细化与 (002) 择优取向；两项可分别验证
fact("h:surface_two_outcomes", b0, "Surface analysis revealed that",
     "同一研究的两项并列观测，分别可核。",
     [("m:ado", "agent"), ("m:grain_refine", "observed_effect"), ("m:plane002", "observed_effect")],
     "Surface analysis revealed that ADO exhibited a grain refinement effect, and crystal analysis showed that the Co hcp (002) crystalline plane was preferentially formed.",
     "observation",
     outcomes=[{"indicator_raw": "grain refinement", "value": q(None, kind="absent"), "direction": "unknown",
                "stage_raw": None, "evidence": [span(b0, "grain refinement effect")]},
               {"indicator_raw": "preferred crystalline plane", "value": q("Co hcp (002)"),
                "direction": "unknown", "stage_raw": None,
                "evidence": [span(b0, "Co hcp (002) crystalline plane was preferentially formed")]}])

# 3) 无论文数值的定性观测：不得自动变成数值或方向
fact("h:stone_forest", b2, "was observed",
     "定性形貌观测，原文无数值。",
     [("m:saccharin", "agent"), ("m:grain_size", "affected_property"), ("m:stone_forest", "observed_structure")],
     "the grain size was gradually refined and a “stone forest” structure was observed",
     "observation")

# 4) 带保留措辞的定性结论 + 结构化程度限定：slightly / to a certain extent
fact("h:purity_hedged", b2, "slightly improves",
     "作者用保留措辞描述纯度改善；程度未量化，用 magnitude 保留原措辞。",
     [("m:saccharin", "agent"), ("m:purity", "affected_property")],
     "The addition of saccharin also slightly improves the purity of cobalt coating to a certain extent.",
     "observation", modality="hedged",
     outcomes=[{"indicator_raw": "purity of cobalt coating",
                "value": q("slightly improves"),
                "direction": "increase", "stage_raw": None,
                "magnitude": {"raw": "slightly", "qualifier": "slight"},
                "comparison": {"status": "not_stated", "baseline_raw": None,
                               "baseline_mention_id": None, "basis_raw": None},
                "evidence": [span(b2, "slightly improves the purity of cobalt coating to a certain extent")]}])

# 5) 作者机理假说：非直接观测
fact("h:adsorption_mechanism", b2, "can adsorb to",
     "作者提出的吸附与生长抑制机理假说。",
     [("m:saccharin", "proposed_agent"), ("m:c_sites", "proposed_site"), ("m:stacking", "inhibited_process")],
     "saccharin molecules can adsorb to specific c-sites on the cobalt dense crystal plane, inhibiting the growth of abc stacking arrangement",
     "author_interpretation")

# 5b) 已登记关系 r11 的正例：域(t1)→值域(t8)，用于验证签名检查不会误伤合规边
fact("h:adsorption", b2, "can adsorb to",
     "糖精分子在钴密排晶面特定位点吸附（已登记关系 r11 的签名正例）。",
     [("m:saccharin", "adsorbate"), ("m:c_sites", "site")],
     "saccharin molecules can adsorb to specific c-sites on the cobalt dense crystal plane",
     "author_interpretation", relation_id="r11")

# 6) 预测性收益：will help，不是已验证结果
fact("h:post_cmp_prediction", b3, "will help to improve",
     "作者预测未来清洗收益，非已观测结果。",
     [("m:na", "agent"), ("m:post_cmp", "predicted_benefit")],
     "Its physical adsorption on cobalt surface will help to improve the inhibitor removal effect in post CMP cleaning.",
     "future_work", modality="speculative")

base["facts"] = facts
for _k in ("experiments", "runs", "samples"):
    base.setdefault(_k, [])
base["role_assignments"] = [
    {"id": "hard:role:ado:unknown", "fact_id": "h:surface_two_outcomes", "subject_mention_id": "m:ado",
     "functional_role": "unknown", "role_raw": None, "role_basis": "unknown",
     "evidence": [span(b0, "grain refinement effect")],
     "note": "摘要未给功能角色名称；观测到细化不等于整平剂。"},
    {"id": "hard:role:saccharin:unknown", "fact_id": "h:stacking" if False else "h:purity_hedged",
     "subject_mention_id": "m:saccharin", "functional_role": "unknown", "role_raw": None,
     "role_basis": "unknown", "evidence": [span(b2, "saccharin")],
     "note": "原文只称 additive，未给受控角色。"},
    {"id": "hard:role:na:other", "fact_id": "h:post_cmp_prediction", "subject_mention_id": "m:na",
     "functional_role": "other", "role_raw": "an effective potential inhibitor for Co CMP",
     "role_basis": "author_explicit",
     "evidence": [span(b3, "NA is suggested to be an effective potential inhibitor for Co CMP")],
     "note": "CMP语境；不并入电沉积suppressor。"},
]
# 6b) 标识与合并：同一密勒指数的晶面/取向提及，跨块不同层次，只能记候选或拒并
def _distinctions():
    return {k: None for k in ["charge", "salt_form", "hydrate", "stereochemistry", "specification"]}


base["identities"] = [
    {"id": "identity:doc:plane002", "canonical_label": "Co hcp (002) crystalline plane",
     "scope": "document", "document_id": doc_ado, "status": "candidate", "external_refs": [],
     "distinctions": _distinctions()},
    {"id": "identity:doc:facet002", "canonical_label": "(002) facet",
     "scope": "document", "document_id": doc_film, "status": "candidate", "external_refs": [],
     "distinctions": _distinctions()},
    {"id": "identity:doc:texture002", "canonical_label": "HCP (002) texture",
     "scope": "document", "document_id": doc_film, "status": "candidate", "external_refs": [],
     "distinctions": _distinctions()},
]
base["identity_links"] = [
    {"mention_id": "m:plane002", "identity_id": "identity:doc:plane002", "basis": "author_explicit",
     "review": "pending", "evidence": [span(b0, "Co hcp (002) crystalline plane")], "external_ref": None},
    {"mention_id": "m:facet002", "identity_id": "identity:doc:facet002", "basis": "name_candidate",
     "review": "pending", "evidence": [span(b2, "(002) facet")], "external_ref": None},
    {"mention_id": "m:texture_hcp002", "identity_id": "identity:doc:texture002", "basis": "name_candidate",
     "review": "pending", "evidence": [span(b2, "HCP (002) texture")], "external_ref": None},
]
base["identity_merges"] = [
    {"id": "merge:plane-facet", "from_identity_id": "identity:doc:plane002",
     "to_identity_id": "identity:doc:facet002", "relation": "same_as", "basis": "name_candidate",
     "review": "pending",
     "evidence": [span(b0, "Co hcp (002) crystalline plane"), span(b2, "(002) facet")],
     "rationale": "两篇都指 (002) 密排面，但一处讲晶面偏好、一处讲取向；跨篇是否同一身份未核，只记候选。",
     "note": "pending 合并只留痕，不改变 entities.identity_id。"},
    {"id": "merge:plane-texture", "from_identity_id": "identity:doc:plane002",
     "to_identity_id": "identity:doc:texture002", "relation": "distinct_from",
     "basis": "author_explicit", "review": "pending",
     "evidence": [span(b0, "Co hcp (002) crystalline plane"), span(b2, "HCP (002) texture")],
     "rationale": "晶面与织构是不同层次，密勒指数相同也不合并；拒并同样留痕。",
     "note": "split/refuse 记录，便于后续审计。"},
]

# 7) 表格单元格锚点 + Run 条件继承 + 样品处理前后状态
TABLE_ID = "糖精对镀钴层结构_导电能力的改变__p2_0"


def cell(row, col, raw):
    return {"kind": "table_cell", "table_id": TABLE_ID, "row": row, "col": col, "cell_raw": raw}


mention("m:film", b2, "cobalt film")
mention("m:anneal", b2, "annealing treatment")
amount_quote = "the amount of saccharin was 3 mg·L –1"

base["experiments"] = [{
    "id": "e:pretreatment", "document_id": doc_film,
    "label": "表1 前处理流程（只取一个单元格作锚点示例，未核对全表工艺）",
    "shared_note": "该表为前处理步骤表；本轮不据此推断电镀工艺。",
    "evidence": [cell(0, 0, "Step")],
}]
base["runs"] = [
    {"id": "r:pretreat", "document_id": doc_film, "experiment_id": "e:pretreatment",
     "label": "前处理第1步（脱脂）",
     "conditions": [{"parameter_raw": "temperature",
                     "value": {"value_raw": "80 °C, 15 min", "value_kind": "qualitative",
                               "unit_raw": None, "unit_status": "not_applicable"},
                     "evidence": [cell(1, 2, "80 °C, 15 min")]}],
     "evidence": [cell(1, 0, "Degreasing")]},
    {"id": "r:saccharin-amount", "document_id": doc_film, "experiment_id": None,
     "label": "糖精用量条件（正文报道）",
     "conditions": [{"parameter_raw": "amount of saccharin",
                     "value": {"value_raw": "3 mg·L –1", "value_kind": "numeric",
                               "unit_raw": "mg·L–1", "unit_status": "reported"},
                     "evidence": [span(b2, amount_quote)]}],
     "evidence": [span(b2, amount_quote)]},
]
base["samples"] = [
    {"id": "s:film", "document_id": doc_film, "label": "镀态钴膜", "material_raw": "cobalt",
     "form_raw": "film", "state_raw": "as-deposited", "treatment_raw": None,
     "derived_from_sample_id": None, "evidence": [span(b2, "cobalt film")]},
    {"id": "s:film-annealed", "document_id": doc_film, "label": "退火后钴膜", "material_raw": "cobalt",
     "form_raw": "film", "state_raw": "annealed", "treatment_raw": "annealing treatment",
     "derived_from_sample_id": "s:film", "evidence": [span(b2, "after the annealing treatment")]},
]
anneal_quote = "further decreased to 10.7 μΩ·cm after the annealing treatment"
base["facts"].append({
    "id": "h:annealed_resistivity", "document_id": doc_film, "group_id": "group:film:resistivity",
    "run_id": "r:saccharin-amount",
    "relation": {"raw": "further decreased to",
                 "definition": "退火后电阻率进一步下降；只记录条件与归属，不推断机理。",
                 "candidate_relation_id": None},
    "participants": [{"mention_id": "m:film", "role": "measured_object"},
                     {"mention_id": "m:anneal", "role": "treatment"},
                     {"mention_id": "m:saccharin", "role": "additive_under_test"}],
    "conditions": [{"parameter_raw": "amount of saccharin", "candidate_parameter": None,
                    "about_mention_ids": ["m:saccharin"],
                    "value": {"value_raw": "3 mg·L –1", "value_kind": "numeric",
                              "unit_raw": "mg·L–1", "unit_status": "reported"},
                    "scope_status": "explicit", "inherited": True,
                    "evidence": [span(b2, amount_quote)]}],
    "outcomes": [{"indicator_raw": "resistivity",
                  "value": {"value_raw": "10.7", "value_kind": "numeric", "unit_raw": "μΩ·cm",
                            "unit_status": "reported"},
                  "direction": "decrease", "stage_raw": "after the annealing treatment",
                  "magnitude": {"raw": None, "qualifier": "unknown"},
                  "comparison": {"status": "explicit", "baseline_raw": "14.4 μΩ·cm",
                                 "baseline_mention_id": None, "basis_raw": None},
                  "sample_id": "s:film-annealed", "evidence": [span(b2, anneal_quote)]}],
    "cited_work": {"raw": None, "document_id": None, "reference_raw": None},
    "statement_type": "observation", "source_scope": "this_study", "polarity": "asserted",
    "modality": "explicit", "evidence": [span(b2, anneal_quote)], "review": "pending",
    "extraction": {"method": "deterministic_protocol_example_mapping", "model": None,
                   "protocol_version": "v2-hardcases-1"},
    "notes": ["条件由 Run 继承，结果绑定退火后样品；不把改善归因于糖精。"],
})

for _f in base["facts"]:
    _f.setdefault("run_id", None)
    _f.setdefault("cited_work", {"raw": None, "document_id": None, "reference_raw": None})
    for _c in _f["conditions"]:
        _c.setdefault("inherited", False)
    for _o in _f["outcomes"]:
        _o.setdefault("sample_id", None)
        _o.setdefault("magnitude", {"raw": None, "qualifier": "unknown"})
        _o.setdefault("comparison", {"status": "not_stated", "baseline_raw": None,
                                     "baseline_mention_id": None, "basis_raw": None})

from migrate_v4 import upgrade
base = upgrade(base)

out = ROOT / "examples/hard_cases.json"
out.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"facts": len(base["facts"]), "mentions": len(base["mentions"]),
                  "roles": len(base["role_assignments"]), "identities": len(base["identities"]),
                  "merges": len(base["identity_merges"]), "entities": len(base["entities"]),
                  "edges": len(base["edges"])}, ensure_ascii=False))
