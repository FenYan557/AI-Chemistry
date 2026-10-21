"""Merge evidence-screened facts and preserve an independent holdout before primary edits."""
import argparse
import hashlib
import json
import random
from collections import Counter,defaultdict
from pathlib import Path

from batch_extract import read,write,empty_bundle,now
from quality_rules import dump_jsonl
from extraction import ingest
from materialize import materialize
from validate import validate

def lines(path):
    p=Path(path)
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []

def make_holdout(rows,excluded_units,out):
    out=Path(out)
    if (out/"holdout_blind.jsonl").exists():return
    groups=defaultdict(list)
    for r in rows:
        if r["unit_id"] in excluded_units:continue
        group="supplement" if r.get("supplemental") else ("rule" if r.get("acceptance_method")=="rule_low_risk_not_semantic_gold" else "AI")
        groups[group].append(r)
    n_rule=min(8,len(groups["rule"]));n_supp=min(8,len(groups["supplement"]))
    quotas={"rule":n_rule,"supplement":n_supp,"AI":min(32-n_rule-n_supp,len(groups["AI"]))}
    chosen=[]
    for group in ("rule","AI","supplement"):
        ordered=sorted(groups[group],key=lambda r:hashlib.sha256(("holdout-9357|"+group+"|"+r["id"]).encode()).hexdigest())
        for row in ordered[:quotas[group]]:
            chosen.append({**row,"sampling_stratum":group,"stratum_population":len(ordered)})
    random.Random(959).shuffle(chosen)
    dump_jsonl(out/"holdout_sample.jsonl",chosen)
    dump_jsonl(out/"holdout_blind.jsonl",[{k:r[k] for k in ("id","unit_id","document_id","source","raw")} for r in chosen])
    write(out/"holdout_design.json",{"selected":len(chosen),"stratum_populations":{k:len(v) for k,v in groups.items()},
        "quotas":quotas,"excluded_calibration_units":sorted(excluded_units),
        "frozen_before_primary_labels":True,"not_human_expert_gold":True,"seed":"holdout-9357"})

def primary_edits(decisions,rows,review_path,protected=None):
    if not Path(review_path).exists():return []
    case_map={r["id"]:r for r in rows};applied=[]
    reviews=read(review_path).get("reviews",[])
    for review in reviews:
        ident=review["id"]
        if ident not in decisions or ident not in case_map:continue
        verdict=review["verdict"]
        if verdict not in ("supported","unsupported","unclear"):raise ValueError("主侧标签无效")
        if not isinstance(review.get("reason"),str) or not review["reason"].strip():raise ValueError("主侧复查需给理由")
        evidence=review.get("evidence_quote")
        if evidence is not None and evidence not in case_map[ident]["source"]:raise ValueError("主侧证据不在源文中")
        accepted=verdict=="supported" and case_map[ident].get("rule",{}).get("tier")!="hard_error" and ident not in (protected or set())
        old=decisions[ident].copy()
        decisions[ident]={**old,"decision":"accept" if accepted else "quarantine","method":"primary_agent_review",
                          "primary_verdict":verdict,"primary_reason":review["reason"],"previous_method":old["method"]}
        applied.append(ident)
    return applied

def holdout_statistics(out,current_ids,sample_name="holdout_sample.jsonl",review_name="holdout_review.json"):
    sample=lines(Path(out)/sample_name)
    path=Path(out)/review_name
    reviews=read(path).get("reviews",[]) if path.exists() else []
    by_id={r["id"]:r for r in reviews}
    expected={r["id"] for r in sample}
    complete=bool(expected) and expected.issubset(by_id) and expected.issubset(current_ids) and len(by_id)==len(reviews)
    strata={}
    for row in sample:
        group=row["sampling_stratum"];entry=strata.setdefault(group,{"sampled":0,"reviewed":0,"supported":0,"unsupported":0,"unclear":0})
        entry["sampled"]+=1
        if row["id"] in by_id:
            verdict=by_id[row["id"]].get("verdict")
            if verdict in ("supported","unsupported","unclear"):
                entry["reviewed"]+=1;entry[verdict]+=1
            else:complete=False
        else:complete=False
    counts=Counter(by_id[k]["verdict"] for k in expected & by_id.keys())
    return {"complete":complete,"sampled":len(sample),"reviewed":sum(counts.values()),"verdicts":dict(counts),"strata":strata,
            "measures":"source support of frozen pre-primary-edit accepted sample","not_human_expert_gold":True,
            "not_global_corpus_precision":True}

def merge(run):
    run=Path(run);out=run/"quality"
    if not (out/"AI_phase_complete.json").exists():raise ValueError("基础AI核验未结束")
    rows=lines(out/"cases.jsonl");by_id={r["id"]:r for r in rows}
    decisions=read(out/"decisions.json")
    focus=run/"quality_focus"
    if (focus/"selection.json").exists() and not (focus/"summary.json").exists():raise ValueError("定向核验未结束")
    for path in (focus/"judgments").glob("*.json"):
        j=read(path);ident=j["id"]
        if ident in decisions and j["verdict"]!="supported":
            decisions[ident]={**decisions[ident],"decision":"quarantine","method":"focused_semantic_check","focus_verdict":j["verdict"]}
    protected=set()
    weak=run/"semantic_relabel/superseded_candidates.json"
    if weak.exists():
        for ident,reasons in read(weak).items():
            if ident in decisions:
                protected.add(ident)
                decisions[ident]={**decisions[ident],"decision":"quarantine","method":"conservative_semantic_relabel",
                                  "reasons":reasons}
    primary_edits(decisions,rows,out/"calibration_review.json",protected)
    base_graph=read(run/"knowledge_graph.json")
    original_facts=list(base_graph["facts"]);supplement_facts=[]
    docs={d["id"]:d for d in base_graph["documents"]};blocks={b["id"]:b for b in base_graph["blocks"]}
    selected={k for k,v in decisions.items() if v["decision"]=="accept"}
    base_graph["facts"]=[f for f in base_graph["facts"] if f["id"] in selected]
    mention_map={m["id"]:m for m in base_graph["mentions"]}
    supplemental=[]
    sup_folder=run/"quality_supplement"
    if (sup_folder/"cases.jsonl").exists() and not (sup_folder/"summary.json").exists():raise ValueError("补充核验未结束")
    for row in lines(sup_folder/"verified_candidates.jsonl"):
        if row["id"] in selected:continue
        unit=blocks.get(row["unit_id"])
        if unit is None or unit["text"]!=row["source"]:raise ValueError("补充候选来源已变化")
        bundle=ingest(empty_bundle(docs[row["document_id"]],[unit]),unit["id"],{"facts":[row["raw"]]},None)
        fact=bundle["facts"][0]
        fact["extraction"]={"method":"source_format_alignment_or_primary_mapping_then_AI_check",
                            "model":None,"protocol_version":"v4-precision-supplement-1"}
        fact["notes"].append("QA补充来源: "+row.get("candidate_kind","unknown")+"; 核验模型 "+row.get("verification_model","qwen3.7-plus")+"; 原始抽取保留")
        if row.get("supersedes_id"):fact["notes"].append("替代原记录: "+row["supersedes_id"])
        base_graph["facts"].append(fact);supplement_facts.append(fact)
        for m in bundle["mentions"]:mention_map.setdefault(m["id"],m)
        supplemental.append({**row,"supplemental":True,"acceptance_method":"supplemental_AI_and_source_checks"})
        decisions[row["id"]]={"id":row["id"],"decision":"accept","method":"supplemental_AI_and_source_checks",
                              "candidate_kind":row.get("candidate_kind"),"supersedes_id":row.get("supersedes_id")}
        selected.add(row["id"])
    accepted_rows=[{**r,"acceptance_method":decisions[r["id"]]["method"]} for r in rows if decisions[r["id"]]["decision"]=="accept"]+supplemental
    # Calibration discoveries cannot be counted as independent post-fix precision evidence.
    calibration=read(out/"calibration_review.json") if (out/"calibration_review.json").exists() else {"reviews":[]}
    excluded_units={by_id[r["id"]]["unit_id"] for r in calibration["reviews"] if r["id"] in by_id}
    for r in lines(out/"primary_supplement_proposals.jsonl"):excluded_units.add(r["unit_id"])
    make_holdout(accepted_rows,excluded_units,out)
    all_rows=rows+supplemental
    from precision_guard import flags as guard_flags
    guard={r["id"]:guard_flags(r) for r in all_rows if guard_flags(r)}
    write(out/"precision_guard_flags.json",guard)
    for ident,reasons in guard.items():
        protected.add(ident)
        decisions[ident]={**decisions[ident],"decision":"quarantine","method":"precision_guard","guard_reasons":reasons}
    primary_edits(decisions,all_rows,out/"holdout_review.json",protected)
    primary_edits(decisions,all_rows,out/"uncertain_review.json",protected)
    primary_edits(decisions,all_rows,out/"confirmation_review.json",protected)
    base_graph["facts"]=[f for f in original_facts+supplement_facts if decisions[f["id"]]["decision"]=="accept"]
    used=set()
    def collect(v):
        if isinstance(v,dict):
            for k,x in v.items():
                if (k=="mention_id" or k.endswith("_mention_id")) and isinstance(x,str):used.add(x)
                elif k=="about_mention_ids" and isinstance(x,list):used.update(x)
                else:collect(x)
        elif isinstance(v,list):
            for x in v:collect(x)
    collect(base_graph["facts"])
    base_graph["mentions"]=[m for k,m in mention_map.items() if k in used]
    base_graph["identity_links"]=[x for x in base_graph["identity_links"] if x["mention_id"] in used]
    base_graph["role_assignments"]=[x for x in base_graph["role_assignments"] if not x.get("fact_id") or decisions.get(x["fact_id"],{}).get("decision")=="accept"]
    materialize(base_graph);report=validate(base_graph)
    if not report["valid"]:raise ValueError("最终筛选图谱校验失败")
    write(out/"precision_graph.json",base_graph)
    dump_jsonl(out/"accepted_facts.jsonl",base_graph["facts"])
    write(out/"final_decisions.json",decisions)
    primary_supported=[f for f in base_graph["facts"] if decisions[f["id"]].get("primary_verdict")=="supported"]
    dump_jsonl(out/"primary_reviewed_facts.jsonl",primary_supported)
    write(out/"primary_reviewed_summary.json",{"facts":len(primary_supported),"not_human_expert_gold":True,
        "definition":"accepted facts with explicit source-supported primary-agent verdict",
        "references_resolve_against":"precision_graph.json","not_a_global_precision_estimate":True})
    dump_jsonl(out/"quarantine.jsonl",[{"case":r,"decision":decisions[r["id"]]} for r in rows if decisions[r["id"]]["decision"]!="accept"])
    holdout=holdout_statistics(out,{r["id"] for r in all_rows})
    write(out/"holdout_summary.json",holdout)
    confirmation=holdout_statistics(out,{r["id"] for r in all_rows},"confirmation_sample.jsonl","confirmation_review.json")
    write(out/"confirmation_summary.json",confirmation)
    rejected_supplements=[]
    for r in lines(sup_folder/"cases.jsonl"):
        if decisions.get(r["id"],{}).get("decision")!="accept":
            rejected_supplements.append({"case":r,"decision":decisions.get(r["id"],{"decision":"quarantine","method":"supplemental_not_supported_or_hard_rule"})})
    dump_jsonl(out/"supplement_quarantine.jsonl",rejected_supplements)
    summary={"updated_at":now(),"raw_facts":len(rows),"accepted_original_facts":sum(decisions[r["id"]]["decision"]=="accept" for r in rows),
        "accepted_supplemental_facts":sum(decisions[r["id"]]["decision"]=="accept" for r in supplemental),
        "accepted_total":len(base_graph["facts"]),"supplemental_candidates":len(lines(sup_folder/"cases.jsonl")),"quarantined_supplemental_candidates":len(rejected_supplements),"mention_entities":len(base_graph["entities"]),"edges":len(base_graph["edges"]),
        "quarantined_original_facts":sum(decisions[r["id"]]["decision"]!="accept" for r in rows),
        "decision_routes":dict(Counter(d["method"] for d in decisions.values())),"valid":True,
        "primary_holdout_finished":holdout["complete"],"not_human_expert_gold":True,
        "raw_extraction_unchanged":True}
    write(out/"final_summary.json",summary)
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);p.add_argument("--wait",action="store_true");a=p.parse_args()
    if a.wait:
        import time
        while not (a.run/"quality/AI_phase_complete.json").exists():time.sleep(20)
    print(json.dumps(merge(a.run),ensure_ascii=False))
