"""Bounded missed-fact inspection; never reports corpus recall from a convenience sample."""
import argparse
import json
import random
import re
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from batch_extract import read,write,now
from extraction_llm import load_config,request_json
from quality_verify import content_json,wait_for_first_pass

SIGNAL=re.compile(r"(?:\d[\d.]*\s*(?:mM|μM|µM|mg|mol|nm|µm|μm|mV|°C|%|μΩ|µΩ))|(?:adsorp|inhibit|suppress|accelerat|resistiv|grain|coordination)",re.I)

def sample_units(run):
    run=Path(run);manifest=read(run/"input_manifest.json")
    checkpoints={}
    for p in (run/"units").glob("*.json"):
        row=read(p);checkpoints[row["unit_id"]]=row
    groups=defaultdict(list)
    for doc in manifest["documents"]:
        for unit in doc["units"]:
            c=checkpoints.get(unit["block"]["id"])
            if c is None:continue
            text=unit["block"]["text"]
            if len(text)<80 or not SIGNAL.search(text):continue
            if c["status"] in ("empty","failed"):
                group="empty_or_failed_scientific_text"
            elif len(c["response"]["facts"])==8:
                group="fact_cap_reached"
            else:group="ordinary_nonempty"
            groups[group].append({"unit_id":unit["block"]["id"],"document_id":doc["document"]["id"],
                "source":text,"existing_facts":c["response"]["facts"],"sample_group":group,"origin_kind":unit["origin"]["kind"]})
    rng=random.Random(91406);selected=[]
    for group in sorted(groups):
        selected.extend(rng.sample(groups[group],min(12,len(groups[group]))))
    rng.shuffle(selected)
    return selected,{g:len(v) for g,v in groups.items()}

def cached_request(out,batch,payload):
    """Cache by all logical inputs; migrate legacy results only for an identical request."""
    import hashlib
    out=Path(out)
    ident=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
    path=out/(ident+".json")
    legacy=hashlib.sha256("|".join(u["unit_id"] for u in batch).encode()).hexdigest()[:16]
    old=out/(legacy+".json");request=out/(legacy+".request.json")
    if not path.exists() and old.exists() and request.exists() and read(request)==payload:
        write(path,read(old));write(out/(ident+".request.json"),payload)
    return ident,path

def check(run,out,model="qwen3.7-plus",workers=2):
    run,out=Path(run),Path(out);out.mkdir(parents=True,exist_ok=True)
    units,sizes=sample_units(run)
    write(out/"sample_units.json",units)
    write(out/"sampling.json",{"groups":sizes,"selected":len(units),"seed":91406,"corpus_recall_estimate":False})
    config=load_config(model=model);config["enable_thinking"]=False
    instruction=('仅检查给定source中是否存在现有facts没有覆盖的、对化学/材料/工艺有用的实质结论。'
        '不要把改写、同义词、重复机理解释当遗漏，不抽作者单位或图中看不见的数据。'
        '只输出JSON {"results":[{"unit_id":"原id","misses":[{"quote":"原文连续完整片段","description":"遗漏了什么，最多80字","importance":"high/medium"}]}]}。'
        '每单元最多3项，无遗漏就空misses。这个任务只生成待核查线索，不改原图谱。')
    batches=[units[i:i+3] for i in range(0,len(units),3)]
    def task(batch):
        payload={"model":model,"temperature":0,"enable_thinking":False,"max_tokens":2048,"response_format":{"type":"json_object"},
            "messages":[{"role":"system","content":instruction},{"role":"user","content":json.dumps(
                [{"unit_id":u["unit_id"],"source":u["source"],"existing_facts":u["existing_facts"]} for u in batch],ensure_ascii=False)}]}
        ident,path=cached_request(out,batch,payload)
        if path.exists():return read(path)
        write(out/(ident+".request.json"),payload)
        result={"ids":[u["unit_id"] for u in batch],"candidates":[],"model":model}
        try:
            data,elapsed=request_json(config,"/chat/completions",payload,timeout=100)
            choice=data["choices"][0];text=choice["message"]["content"]
            (out/(ident+".response.txt")).write_text(text,encoding="utf-8")
            result.update(elapsed_seconds=elapsed,usage=data.get("usage",{}),finish_reason=choice.get("finish_reason"))
            if choice.get("finish_reason")=="length":raise ValueError("输出截断")
            parsed=content_json(text);sources={u["unit_id"]:u for u in batch}
            for row in parsed.get("results",[]):
                source=sources.get(row.get("unit_id"))
                if source is None:continue
                for miss in row.get("misses",[])[:3]:
                    if not isinstance(miss,dict) or not isinstance(miss.get("quote"),str):continue
                    if miss["quote"] and miss["quote"] in source["source"]:
                        result["candidates"].append({**miss,"unit_id":source["unit_id"],"document_id":source["document_id"],
                            "source":source["source"],"existing_facts":source["existing_facts"],"status":"candidate_not_confirmed"})
        except Exception as exc:result["error"]=str(exc)[:250]
        write(path,result);return result
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results=list(pool.map(task,batches))
    candidates=[c for r in results for c in r["candidates"]]
    write(out/"recall_candidates.json",candidates)
    report={"completed_at":now(),"sampled_units":len(units),"potential_missing_items":len(candidates),
            "failed_batches":sum("error" in r for r in results),"added_to_graph":0,"corpus_recall_estimate":False}
    write(out/"summary.json",report)
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--wait",action="store_true");p.add_argument("--model",default="qwen3.7-plus");a=p.parse_args()
    if a.wait:wait_for_first_pass(a.run)
    check(a.run,a.out,a.model)
