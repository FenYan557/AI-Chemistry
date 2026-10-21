"""Generic source-bound supplemental verification; corpus-specific proposals are data."""
import argparse
import json
from pathlib import Path
import quality_verify as qa
from quality_focus import FOCUS
from semantic_weaken import weaken
from batch_extract import read,write,now,empty_bundle
from quality_rules import fid,triage,dump_jsonl
from extraction import ingest

def build(run):
    run=Path(run);manifest=read(run/"input_manifest.json")
    lookup={u["block"]["id"]:(d,u) for d in manifest["documents"] for u in d["units"]}
    original={r["id"] for r in (json.loads(x) for x in (run/"quality/cases.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())}
    rows=[]
    for name in ("quality/primary_supplement_proposals.jsonl","format_recovery/candidates.jsonl","semantic_relabel/cases.jsonl"):
        path=run/name
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row=json.loads(line)
                    if "candidate_kind" not in row:row["candidate_kind"]="format_recovery"
                    rows.append(row)
    candidates={};excluded=[]
    for row in rows:
        uid=row["unit_id"]
        if uid not in lookup or row.get("source")!=lookup[uid][1]["block"]["text"]:
            excluded.append({"id":row.get("id"),"reason":"source_snapshot_mismatch"});continue
        doc,unit=lookup[uid]
        raw,changes=weaken(row["raw"],row["source"])
        row={**row,"raw":raw,"id":fid(uid,raw)}
        if changes:row["additional_semantic_weakening"]=changes
        if row["id"] in original:continue
        try:
            ingest(empty_bundle(doc["document"],[unit["block"]]),uid,{"facts":[raw]},"supplemental_source_mapping")
        except Exception as exc:
            excluded.append({"id":row["id"],"reason":str(exc)[:250]});continue
        row["rule"]=triage(row);candidates[row["id"]]=row
    write(run/"quality_supplement/source_exclusions.json",excluded)
    return list(candidates.values())

def main():
    p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--model",default="qwen3.7-plus");p.add_argument("--workers",type=int,default=2)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    rows=build(a.run);dump_jsonl(a.out/"cases.jsonl",rows)
    original=qa.INSTRUCTION
    try:
        qa.INSTRUCTION=original+"\n"+FOCUS
        verifier=qa.Verifier(a.out,a.model,workers=a.workers)
        candidates=[r for r in rows if r["rule"]["tier"]!="hard_error"]
        verifier.run(sorted(candidates,key=lambda r:(r["unit_id"],r["id"])))
        if verifier.stop.is_set():raise SystemExit("补充核验认证或路由失败，保留检查点")
        accepted=[r for r in rows if r["rule"]["tier"]!="hard_error" and verifier.decisions.get(r["id"],{}).get("verdict")=="supported"]
        accepted=[{**r,"verification_model":a.model} for r in accepted]
        dump_jsonl(a.out/"verified_candidates.jsonl",accepted)
        write(a.out/"summary.json",{"completed_at":now(),"candidates":len(rows),"supported_candidates":len(accepted),
            "hard_rule_quarantine":len(rows)-len(candidates),"added_to_graph":0,
            "note":"requires final merge and primary holdout audit; original raw extraction remains unchanged"})
        print(json.dumps(read(a.out/"summary.json"),ensure_ascii=False),flush=True)
    finally:qa.INSTRUCTION=original

if __name__=="__main__":main()
