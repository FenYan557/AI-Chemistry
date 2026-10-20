"""可重复构造人工规则化的协议映射，不是模型抽取，不作金标。
只读现有4块；保存片段偏移和当前语料对齐报告。
"""
import hashlib
import json
from pathlib import Path
from profile_corpus import ROOT, REPO
import materialize

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def magnitude(raw=None, qualifier="unknown"):
    return {"raw": raw, "qualifier": qualifier}

def comparison(status="not_stated", baseline_raw=None, mention=None, basis=None):
    return {"status": status, "baseline_raw": baseline_raw, "baseline_mention_id": mention, "basis_raw": basis}

def normalize(bundle):
    """补齐可选字段默认值，保证生成结果与契约一致。"""
    for fact in bundle["facts"]:
        fact.setdefault("run_id", None)
        fact.setdefault("cited_work", {"raw": None, "document_id": None, "reference_raw": None})
        for outcome in fact["outcomes"]:
            outcome.setdefault("sample_id", None)
            outcome.setdefault("magnitude", magnitude())
            outcome.setdefault("comparison", comparison())
        for condition in fact["conditions"]:
            condition.setdefault("inherited", False)
    for key in ("experiments", "runs", "samples", "identity_merges"):
        bundle.setdefault(key, [])


def build():
    snapshot = ROOT / "data/source_blocks.jsonl"
    rows = [json.loads(s) for s in snapshot.read_text(encoding="utf-8").splitlines() if s.strip()]
    bundle = {k: [] for k in ["documents","blocks","mentions","identities","identity_links","external_records","facts"]}
    bundle["schema_version"] = "4.0.0-draft"
    docs, alignment = {}, []
    for row in rows:
        did = row["doc_id"]
        file = REPO / "清洗/02_清洗/out/blocks" / (did + ".jsonl")
        actual = {b["block_id"]: b for b in (json.loads(s) for s in file.read_text(encoding="utf-8").splitlines() if s.strip())}
        alignment.append({"block_id": row["block_id"], "current_text_matches_snapshot": actual.get(row["block_id"], {}).get("text") == row["text"],
                          "pdf_semantics_reviewed": False})
        if did not in docs:
            meta = json.loads(file.with_suffix(".meta.json").read_text(encoding="utf-8"))
            docs[did] = {"id": did, "title": meta["title"], "source_file": file.relative_to(REPO).as_posix(),
                         "sha256": hashlib.sha256(file.read_bytes()).hexdigest(), "source_kind": "cleaned_text"}
        bundle["blocks"].append({"id": row["block_id"], "document_id": did, "page": row["page"], "section": row["section"], "text": row["text"]})
    bundle["documents"] = list(docs.values())

    def span(i, quote):
        row = rows[i]
        start = row["text"].index(quote)
        return {"kind":"block","block_id": row["block_id"], "start": start, "end": start+len(quote), "quote": quote}
    def mention(mid, i, surface, types=None):
        bundle["mentions"].append({"id":mid,"document_id":rows[i]["doc_id"],"surface":surface,"evidence":span(i,surface),"candidate_type_ids":types or []})
        return mid
    mention("m:adenosine",0,"Adenosine",["t1"])
    mention("m:ado",0,"ADO",["t1"])
    mention("m:deposition",0,"cobalt deposition")
    mention("m:mechanism",0,"intramolecular synergistic acceleration–suppression mechanism")
    mention("m:saccharin",2,"saccharin",["t1"])
    mention("m:film",2,"cobalt film")
    mention("m:anneal",2,"annealing treatment")
    mention("m:na",3,"NA")
    mention("m:other_components",3,"other slurry components")
    # 一次篇内括注映射；未做跨篇或外部身份确认。
    bundle["identities"] = [{"id":"identity:doc:ado","canonical_label":"Adenosine","scope":"document",
                            "document_id":rows[0]["doc_id"],"status":"candidate","external_refs":[],
                            "distinctions":{k:None for k in ["charge","salt_form","hydrate","stereochemistry","specification"]}}]
    for mid in ["m:adenosine","m:ado"]:
        bundle["identity_links"].append({"mention_id":mid,"identity_id":"identity:doc:ado","basis":"author_explicit","review":"pending",
                                        "evidence":[span(0,"Adenosine (ADO)")],"external_ref":None})
    def quantity(raw, unit=None, status="not_applicable"):
        return {"value_raw":raw,"value_kind":"numeric","unit_raw":unit,"unit_status":status}
    def fact(fid,i,raw,definition,parts,evidence,kind="reported_claim",group=None,conditions=None,outcomes=None):
        item={"id":fid,"document_id":rows[i]["doc_id"],"group_id":group,
              "relation":{"raw":raw,"definition":definition,"candidate_relation_id":None},
              "participants":[{"mention_id":m,"role":r} for m,r in parts],
              "conditions":conditions or [],"outcomes":outcomes or [],
              "statement_type":kind,"source_scope":"this_study","polarity":"asserted",
              "modality":"hedged" if kind=="future_work" else "explicit",
              "evidence":[span(i,evidence)],"review":"pending",
              "extraction":{"method":"deterministic_protocol_example_mapping","model":None,"protocol_version":"v3-example-1"},
              "notes":["主智能体拟定的协议映射；需人工作者回原PDF核对，不是金标或模型性能结果。"]}
        bundle["facts"].append(item)
        return item
    effect="effects of low-concentration acceleration but high-concentration suppression in cobalt deposition"
    for name,raw,cond,direction in [("low","acceleration","low-concentration","increase"),("high","suppression","high-concentration","decrease")]:
        fact("f:ado:"+name,0,raw,"ADO在对应浓度条件下对钴沉积的作用；不外推数值范围。",
             [("m:ado","agent"),("m:deposition","affected_process")],effect,group="group:ado:concentration",
             conditions=[{"parameter_raw":"concentration","candidate_parameter":None,"about_mention_ids":["m:ado"],
                          "value":quantity(cond),"scope_status":"explicit","evidence":[span(0,cond)]}],
             outcomes=[{"indicator_raw":"cobalt deposition","value":quantity(raw),"direction":direction,"stage_raw":None,
                        "evidence":[span(0,effect)]}])
    mechanism="an intramolecular synergistic acceleration–suppression mechanism was proposed to explain the effects of low-concentration acceleration but high-concentration suppression in cobalt deposition"
    fact("f:ado:interpretation",0,"was proposed to explain","作者提出的分子内作用解释，非多个添加剂间已验证协同。",
         [("m:mechanism","explanation"),("m:ado","involved_substance"),("m:deposition","explained_process")],
         mechanism,"author_interpretation",group="group:ado:concentration")
    numeric="The resistivity of the cobalt film decreased to 14.4 μΩ·cm, and further decreased to 10.7 μΩ·cm after the annealing treatment."
    for name,value,stage in [("reported","14.4",None),("annealed","10.7","after the annealing treatment")]:
        parts=[("m:film","measured_object"),("m:saccharin","additive_under_test")]
        if stage:parts.append(("m:anneal","treatment"))
        amount="When the amount of saccharin was 3 mg·L –1"
        baseline = comparison("explicit","14.4 μΩ·cm") if stage else comparison()
        fact("f:resistivity:"+name,2,"decreased to" if not stage else "further decreased to",
             "记录钴膜电阻率；处理后变化不自动归因于糖精。",
             parts,numeric,"observation",group="group:film:resistivity",
             conditions=[{"parameter_raw":"amount of saccharin","candidate_parameter":None,
                          "about_mention_ids":["m:saccharin"],
                          "value":quantity("3 mg·L –1","mg·L–1","reported"),
                          "scope_status":"explicit","evidence":[span(2,amount)]}],
             outcomes=[{"indicator_raw":"resistivity","value":quantity(value,"μΩ·cm","reported"),"direction":"decrease",
                        "stage_raw":stage,"magnitude":magnitude(),"comparison":baseline,
                        "evidence":[span(2,numeric)]}])
    future="support for subsequent researches of exploring synergistic effect of NA and other slurry components"
    fact("f:cmp:future",3,"exploring synergistic effect","未来研究方向，不是已发生或已验证的协同作用。",
         [("m:na","prospective_participant"),("m:other_components","prospective_participant")],future,"future_work")
    # L2功能角色：受控多选，绑定使用性事实与条件；不产生无条件永久角色。
    role_assignments = [
        {"id":"role:ado:low","fact_id":"f:ado:low","subject_mention_id":"m:ado",
         "functional_role":"accelerator","role_raw":"leveling additive","role_basis":"effect_inference",
         "evidence":[span(0,"acceleration")],
         "note":"原文称其为整平剂，低浓度下观察为加速；按作用方向记候选，二者不互相替代。"},
        {"id":"role:ado:high","fact_id":"f:ado:high","subject_mention_id":"m:ado",
         "functional_role":"suppressor","role_raw":"leveling additive","role_basis":"effect_inference",
         "evidence":[span(0,"suppression")],
         "note":"与低浓度分条记录；条件不同不可合并为单一角色。"},
        {"id":"role:ado:leveler","fact_id":"f:ado:low","subject_mention_id":"m:ado",
         "functional_role":"leveler","role_raw":"Adenosine (ADO) was selected as a leveling additive",
         "role_basis":"author_explicit",
         "evidence":[span(0,"Adenosine (ADO) was selected as a leveling additive")],
         "note":"作者显式定位；不因效果为加速而改写。"},
        {"id":"role:cmp:na","fact_id":"f:cmp:future","subject_mention_id":"m:na",
         "functional_role":"other","role_raw":"an effective potential inhibitor for Co CMP",
         "role_basis":"author_explicit",
         "evidence":[span(3,"an effective potential inhibitor for Co CMP")],
         "note":"CMP语境缓蚀角色，初期不并入电沉积suppressor。"},
        {"id":"role:saccharin:unknown","fact_id":"f:resistivity:annealed","subject_mention_id":"m:saccharin",
         "functional_role":"unknown","role_raw":None,"role_basis":"unknown",
         "evidence":[span(2,"the saccharin additive")],
         "note":"摘要未给出糖精的功能角色名称，保持未知，不据常识补填。"},
    ]
    bundle["role_assignments"] = role_assignments
    normalize(bundle)
    from migrate_v4 import upgrade
    bundle = upgrade(bundle)
    return bundle, alignment

if __name__ == "__main__":
    result, alignment = build()
    write(ROOT/"examples/literature_bundle.json",result)
    write(ROOT/"reports/source_alignment.json",{"blocks":alignment,"all_current_text_matches":all(x["current_text_matches_snapshot"] for x in alignment),
                                             "not_pdf_semantic_validation":True})
    print(json.dumps({"documents":len(result["documents"]),"blocks":len(result["blocks"]),"mentions":len(result["mentions"]),
                      "facts":len(result["facts"]),"entities":len(result["entities"]),"edges":len(result["edges"]),
                      "aligned":all(x["current_text_matches_snapshot"] for x in alignment)},ensure_ascii=False))
