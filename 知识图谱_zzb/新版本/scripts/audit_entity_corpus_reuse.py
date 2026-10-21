"""Final read-only checks and bounded evidence for corpus entity reuse."""
import argparse,json
from pathlib import Path
from collections import Counter
from unittest.mock import patch
import entity_corpus_reuse as reuse
from batch_extract import ROOT,read,write
from extraction_llm import load_config

def reference_coverage(refs,rows):
    output=[]
    for ref in refs:
        hits=[r for r in rows if r["source_id"]==ref["source_id"] and any(s in r["surface"] for s in ref["alternatives"])]
        output.append({**ref,"present":bool(hits),"matched_candidate_ids":[r["id"] for r in hits]})
    return output

def audit(out,check_cache=False):
    out=out.resolve();folder=out/"normalized";summary=read(folder/"summary.json");plan=read(out/"plan.json")
    graph=read(reuse.BASE/"quality/precision_graph.json");preview=read(folder/"entity_pool_preview.json")
    current_rows=reuse.lines(folder/"enriched_pool.jsonl");base_rows=[{"id":m["id"],"surface":m["surface"],"source_id":m["evidence"]["block_id"]} for m in graph["mentions"]]
    before_rows=reuse.lines(out/"reused_pool.jsonl");refs=read(ROOT/"reports/entity_acceptance_20261021/reference_checkpoints.json")["reference_entities"]
    coverage={"curated_baseline":reference_coverage(refs,base_rows),"zero_call_reused_pool":reference_coverage(refs,before_rows),"enriched_pool":reference_coverage(refs,current_rows)}
    write(folder/"limited_reference_recheck.json",{"basis":"previous limited references, reused for diagnostics, not independent holdout or expert gold","stages":coverage})
    assert reuse.checksum(reuse.BASE/"quality/precision_graph.json")==plan["production_sha256"]
    assert not preview["facts"] and not preview["edges"]
    assert all(e["identity_id"] is None for e in preview["entities"])
    assert all(l["review"]=="pending" for l in preview["identity_links"])
    base_ids={m["id"] for m in graph["mentions"]};present={m["id"] for m in preview["mentions"]}
    assert base_ids<=present
    failures=list((out/"responses").glob("*/failure_*.json"));tasks=read(out/"tasks.json")
    raw_results=[read(out/"responses"/t["task_id"]/"result.json") for t in tasks]
    summary.update(raw_response_statuses=dict(Counter(r["status"] for r in raw_results)),transport_failures_recorded=len(failures),transport_attempts=len(tasks)+len(list((out/"responses").glob("*/transport_attempt_1.json"))),failed_request_reported_usage="unknown",limited_reference_presence={stage:{"present":sum(x["present"] for x in checks),"reference_concepts":len(refs)} for stage,checks in coverage.items()},full_corpus_entity_coverage_claimed=False,primary_review_scope="154 prior reviewed records reused; new corpus records machine proposed, not all primary checked")
    if check_cache:
        config=load_config()
        with patch.object(reuse,"request_json",side_effect=AssertionError("cache replay attempted network")):
            for task in tasks:reuse.execute_task(task,config,out)
        summary["cache_replay"]={"tasks":len(tasks),"network_calls":0}
    key=load_config()["api_key"];checked=0;leaks=[]
    for path in out.rglob("*"):
        if path.is_file() and path.suffix in (".json",".jsonl",".txt",".md"):
            checked+=1
            if key in path.read_text(encoding="utf-8-sig"):leaks.append(str(path.relative_to(out)))
    assert not leaks,"credential detected in output"
    summary["security_check"]={"output_files_checked":checked,"exact_credential_found":False}
    summary["review_groups"]=len(reuse.lines(folder/"review_groups.jsonl"))
    summary["alias_review_queue"]=len(reuse.lines(folder/"alias_review_queue.jsonl"))
    write(folder/"summary.json",summary);print(json.dumps(summary,ensure_ascii=False))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);p.add_argument("--check-cache",action="store_true");a=p.parse_args();audit(a.run,a.check_cache)
