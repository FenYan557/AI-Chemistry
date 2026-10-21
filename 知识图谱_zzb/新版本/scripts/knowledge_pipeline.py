"""One entry for resumable extraction, precision checking, bounded recall and incremental reuse."""
import argparse
import hashlib
import json
import runpy
import sys
from pathlib import Path

from batch_extract import ROOT,prepare,Engine,read,write
from extraction_llm import load_config
from quality_rules import fid
from quality_verify import JUDGE_VERSION,INSTRUCTION as JUDGE_INSTRUCTION
from quality_focus import FOCUS

def reuse_checkpoints(old_run,new_run,manifest,profile,judge_model="qwen3.7-plus"):
    old_run,new_run=Path(old_run).resolve(),Path(new_run).resolve()
    if old_run==new_run:raise ValueError("reuse-from不能与当前run相同；同一run直接续跑即可")
    old_profile=read(old_run/"profile.json")
    if any(old_profile.get(k)!=profile.get(k) for k in ("model","enable_thinking","protocol")):
        raise ValueError("旧缓存的模型或抽取协议不兼容，不能复用")
    old_manifest=read(old_run/"input_manifest.json")
    old_docs={d["document"]["id"]:d for d in old_manifest["documents"]}
    allowed=set()
    for doc in manifest["documents"]:
        old=old_docs.get(doc["document"]["id"])
        if old and old["document"]["sha256"]==doc["document"]["sha256"]:
            old_ids={u["block"]["id"] for u in old["units"]}
            allowed.update(u["block"]["id"] for u in doc["units"] if u["block"]["id"] in old_ids)
    reused,fact_ids=0,set()
    for path in (old_run/"units").glob("*.json"):
        row=read(path)
        if row["unit_id"] not in allowed:continue
        dest=new_run/"units"/path.name
        if dest.exists():continue
        row["reused_from"]=str(old_run)
        write(dest,row);reused+=1
        fact_ids.update(fid(row["unit_id"],f) for f in row["response"]["facts"])
    glossary_reused=0
    for doc in manifest["documents"]:
        old=old_docs.get(doc["document"]["id"])
        if not old or old["document"]["sha256"]!=doc["document"]["sha256"]:continue
        for suffix in (".json",".source.json"):
            src=old_run/"glossaries"/(doc["key"]+suffix);dst=new_run/"glossaries"/src.name
            if src.exists() and not dst.exists():
                data=read(src);data["reused_from"]=str(old_run)
                write(dst,data);glossary_reused+=int(suffix==".json")
    judge_profile=hashlib.sha256((JUDGE_VERSION+JUDGE_INSTRUCTION+judge_model).encode("utf-8")).hexdigest()
    qa_reused=0
    focus_profile=hashlib.sha256((JUDGE_VERSION+JUDGE_INSTRUCTION+"\n"+FOCUS+judge_model).encode("utf-8")).hexdigest()
    profiles={"quality":judge_profile,"quality_focus":focus_profile}
    for directory,expected_profile in profiles.items():
        for src in (old_run/directory/"judgments").glob("*.json"):
            row=read(src)
            if row.get("profile")==expected_profile and row.get("id") in fact_ids:
                dst=new_run/directory/"judgments"/src.name
                if not dst.exists():
                    row["reused_from"]=str(old_run/directory);write(dst,row);qa_reused+=1
    proposals=old_run/"quality/primary_supplement_proposals.jsonl"
    if proposals.exists():
        selected=[json.loads(x) for x in proposals.read_text(encoding="utf-8").splitlines() if x.strip()]
        selected=[r for r in selected if r.get("unit_id") in allowed]
        from quality_rules import dump_jsonl
        dump_jsonl(new_run/"quality/primary_supplement_proposals.jsonl",selected)
    report={"source_run":str(old_run),"unit_checkpoints_reused":reused,"glossaries_reused":glossary_reused,
            "AI_judgments_reused":qa_reused,"source_identity_requirement":"same document id, SHA256 and unit id",
            "old_partial_failed_statuses_preserved":True,"no_credentials_copied":True}
    write(new_run/"reuse_report.json",report)
    return report

def invoke(script,args):
    previous=sys.argv
    try:
        sys.argv=[str(ROOT/"scripts"/script),*list(map(str,args))]
        runpy.run_path(str(ROOT/"scripts"/script),run_name="__main__")
    finally:sys.argv=previous

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--corpus",type=Path,default=ROOT.parents[1]/"清洗/02_清洗/out")
    p.add_argument("--workers",type=int,default=8)
    p.add_argument("--qa-workers",type=int,default=4)
    p.add_argument("--judge-model",default="qwen3.7-plus")
    p.add_argument("--reuse-from",type=Path)
    p.add_argument("--stage",choices=("all","extract","verify"),default="all")
    p.add_argument("--retry-failed",action="store_true")
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    plan={"run":str(a.run),"stage":a.stage,"extraction_credential":"dedicated local config only",
          "reuse_from":str(a.reuse_from) if a.reuse_from else None,"automatic_stages":["extract","rule triage","AI verification","bounded recall check"],
          "publication_automatic":False,"primary_sample_review_required":True}
    if a.dry_run:
        print(json.dumps(plan,ensure_ascii=False));return
    if a.stage in ("all","extract"):
        a.run.mkdir(parents=True,exist_ok=True)
        manifest=prepare(a.corpus,a.run);config=load_config()
        engine=Engine(config,manifest,a.run,workers=a.workers,retry_failed=a.retry_failed)
        if a.reuse_from:
            print(json.dumps(reuse_checkpoints(a.reuse_from,a.run,manifest,read(a.run/"profile.json"),a.judge_model),ensure_ascii=False))
            engine=Engine(config,manifest,a.run,workers=a.workers,retry_failed=a.retry_failed)
        if not engine.execute():raise SystemExit("抽取阶段出现运行错误，先恢复检查点")
    if a.stage in ("all","verify"):
        invoke("quality_verify.py",["--run",a.run,"--out",a.run/"quality","--model",a.judge_model,"--workers",a.qa_workers])
        invoke("quality_focus.py",["--cases",a.run/"quality/cases.jsonl","--out",a.run/"quality_focus","--model",a.judge_model,"--workers",a.qa_workers])
        invoke("quality_recall.py",["--run",a.run,"--out",a.run/"recall_check","--model",a.judge_model])
        invoke("format_ground.py",["--run",a.run,"--out",a.run/"format_recovery"])
        invoke("semantic_weaken.py",["--run",a.run,"--out",a.run/"semantic_relabel"])
        invoke("quality_supplement.py",["--run",a.run,"--out",a.run/"quality_supplement","--model",a.judge_model,"--workers",a.qa_workers])
        invoke("finalize_quality.py",["--run",a.run])
    write(a.run/"automatic_pipeline_complete.json",{**plan,"automatic_stages_finished":True,
          "primary_sample_review_required":True,"precision_not_claimed_from_format_or_AI_pass_rate":True})

if __name__=="__main__":main()
