"""One bounded retry of transport-failed tasks only; never rerun invalid responses."""
import argparse
from pathlib import Path
import entity_corpus_reuse as reuse
from batch_extract import read,write,now
from extraction_llm import load_config

def retry(out):
    out=out.resolve();config=load_config();plan=read(out/"plan.json")
    if plan["pipeline_sha256"]!=reuse.checksum(reuse.__file__):raise ValueError("original request runner changed")
    tasks=read(out/"tasks.json");selected=[]
    for task in tasks:
        path=out/"responses"/task["task_id"]/"result.json"
        if not path.exists():continue
        result=read(path)
        if result.get("status")!="failed" or result.get("error_class")!="ExtractionAPIError":continue
        archive=path.with_name("transport_attempt_1.json")
        if archive.exists():continue
        selected.append((task,path,archive))
    write(out/"transport_recovery_plan.json",{"created_at":now(),"selected_document_ids":[t["document_id"] for t,p,a in selected],"additional_call_limit":len(selected),"concurrency":1,"invalid_responses_retried":0,"failed_requests_usage":"unknown unless server reported"})
    for task,path,archive in selected:
        path.replace(archive)
        reuse.execute_task(task,config,out)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);retry(p.parse_args().run)
