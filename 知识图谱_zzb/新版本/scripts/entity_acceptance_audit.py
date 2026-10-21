"""Summarize frozen acceptance evidence; optional cache replay forbids network."""
import argparse, json, hashlib, copy
from pathlib import Path
from collections import Counter
from unittest.mock import patch
from batch_extract import read,write
from entity_extract_pilot import locate,processing_fingerprint
from extraction_llm import load_config

def baseline(run):
    import entity_extract_pilot as e
    old=read(run/"baseline_contract.json");config=load_config()
    instruction,schema=e.INSTRUCTION,e.SCHEMA
    try:
        e.INSTRUCTION,e.SCHEMA=old["instruction"],old["schema"]
        results=[e.run(t,config,run/"baseline") for t in read(run/"baseline/tasks.json")]
    finally:e.INSTRUCTION,e.SCHEMA=instruction,schema
    return results

def coverage(refs,rows):
    result=[]
    for ref in refs:
        found=[]
        for rid,e in rows:
            names=[(e["name"],e["source_id"])]+[(a["surface"],a["source_id"]) for a in e["aliases"]]
            if any(sid==ref["source_id"] and any(a in name for a in ref["alternatives"]) for name,sid in names):found.append(rid)
        result.append({**ref,"matched_record_ids":found,"present":bool(found)})
    return result

def audit(run,check_cache=False):
    tasks=read(run/"tasks.json");reference=read(run/"reference_checkpoints.json")
    assert processing_fingerprint()==reference["processing_fingerprint"],"Pipeline changed since freeze"
    primary=read(run/"primary_reviews.json");raw=[];results=[]
    for t in tasks:
        r=read(run/"responses"/t["task_id"]/"result.json");results.append(r)
        raw.extend((f'{t["task_id"]}:{i}',e) for i,e in enumerate(r["data"]["entities"]))
    decisions=read(run/"ai_review/result.json")["data"]["decisions"]
    proposed=dict(raw)
    for d in decisions:
        if d["decision"]=="drop":proposed.pop(d["record_id"],None)
        else:proposed[d["record_id"]]=d["entity"]
    refs=reference["reference_entities"]
    checks={"raw":coverage(refs,raw),"ai_proposal_only":coverage(refs,list(proposed.items())),"primary":coverage(refs,[(r["record_id"],r["final"]) for r in primary["records"] if r["action"]!="drop"])}
    write(run/"checkpoint_results.json",checks)
    screening=read(run/"rule_screening.json");selected=read(run/"ai_review/selection.json")
    errors={r["record_id"]:r["raw_semantic_issues"] for r in primary["records"] if r["raw_semantic_issues"]}
    originals=dict(raw)
    harmful=[{"record_id":d["record_id"],"decision":d["decision"],"reason":d["reason"]} for d in decisions
             if d["decision"]=="drop" or (d["entity"]["name"] not in originals[d["record_id"]]["name"]
                                          and originals[d["record_id"]]["name"] not in d["entity"]["name"])]
    # Concrete adjudications are evidence artifacts, never reusable extraction rules.
    write(run/"ai_primary_adjudication.json",{"human_review":"pending","harmful_proposals":harmful,"unresolved_raw_issues_after_ai":errors,"primary_overrides_of_ai":[r["record_id"] for r in primary["records"] if r["record_id"] in {d["record_id"] for d in decisions} and (r["record_id"] not in proposed or proposed[r["record_id"]]!=r["final"])],"note":"Optional name-boundary edits also count in object differences; not all overrides are new AI errors. AI proposals are not applied by the pipeline."})
    summary=read(run/"final_summary.json")
    baseline_results=[read(f) for f in sorted((run/"baseline/responses").glob("*/result.json"))]
    api_results=results+[read(f) for f in sorted((run/"ai_review").glob("batch_*/result.json"))]+baseline_results
    summary.update(model=results[0]["model"],successful_api_calls=len(api_results),failed_api_calls=0,interrupted_requests_may_have_reached_server=2,interrupted_usage=None,known_reported_tokens=sum(r.get("usage",{}).get("total_tokens",0) for r in api_results),usage_by_stage={"new_extraction":sum(r["usage"]["total_tokens"] for r in results),"ai_review":sum(read(f)["usage"]["total_tokens"] for f in (run/"ai_review").glob("batch_*/result.json")),"old_prompt_comparison":sum(r["usage"]["total_tokens"] for r in baseline_results)},rule_flagged_records=sum(bool(r["flags"]) for r in screening),automatic_pass_records=sum(not r["flags"] for r in screening),automatic_pass_ai_audit_records=sum("automatic_pass_audit" in r["flags"] for r in selected),primary_reviewed_records=len(primary["records"]),ai_reviewed_records=len(decisions),raw_records_with_identified_substantive_issues=len(errors),ai_harmful_proposals=len(harmful),ai_proposed_records=len(proposed),ai_decision_counts=dict(Counter(d["decision"] for d in decisions)),limited_reference_coverage={stage:{"present":sum(r["present"] for r in rows),"reference_concepts":len(refs)} for stage,rows in checks.items()},raw_alias_pairs=sum(len(e["aliases"]) for _,e in raw),false_alias_merges_observed=0,unattended_full_corpus_ready=False,remaining_blockers=["完整块参考遗漏4/28；另一来源漏5种重点方法，必须增加逐来源覆盖复核。","AI仍误删/替换可定位提及；需要保留主审门，不可直接执行建议。","OCR式身份仍依赖复核，不能把定位通过当身份确认。"])
    if check_cache:
        import entity_extract_pilot as e
        import entity_pilot_review as review
        config=load_config()
        with patch.object(e,"request_json",side_effect=AssertionError("unexpected network")),patch.object(review,"request_json",side_effect=AssertionError("unexpected network")):
            for task in tasks:e.run(task,config,run)
            for f in sorted((run/"ai_review").glob("batch_*/request.json")):
                payload=read(f);user=json.loads(payload["messages"][1]["content"])
                review.review_chunk(config,user["records"],{s["source_id"]:s["text"] for s in user["segments"]},f.parent,tasks)
            baseline(run)
        summary["cache_replay"]={"extraction_hits":len(tasks),"review_hits":len(list((run/"ai_review").glob("batch_*/result.json"))),"baseline_hits":len(baseline_results),"network_calls":0}
    config=load_config();leaks=[];count=0
    for f in run.rglob("*"):
        if f.is_file() and f.suffix in (".json",".jsonl",".txt",".md"):
            count+=1
            if config["api_key"] in f.read_text(encoding="utf-8-sig"):leaks.append(str(f.relative_to(run)))
    assert not leaks,"credential detected in output"
    summary["credential_scan"]={"files":count,"exact_key_found":False}
    write(run/"final_summary.json",summary)
    print(json.dumps(summary,ensure_ascii=False))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);p.add_argument("--check-cache",action="store_true");p.add_argument("--baseline",action="store_true");a=p.parse_args()
    if a.baseline:baseline(a.run)
    else:audit(a.run,a.check_cache)
