"""Conservative source-format alignment. Never changes case, chemistry, digits or word order."""
import argparse
import copy
import json
import unicodedata
from pathlib import Path
from batch_extract import read,write,empty_bundle
from extraction import ingest
from quality_rules import fid,triage,dump_jsonl

class GroundError(ValueError):pass

def normalized_with_map(text):
    chars=[];positions=[]
    for index,char in enumerate(text):
        for new in unicodedata.normalize("NFKC",char):
            if new.isspace() or new in "\u00ad\u200b":continue
            if new in "−–":new="-"
            chars.append(new);positions.append(index)
    return "".join(chars),positions

def locate(needle,source):
    if not isinstance(needle,str) or not needle:raise GroundError("empty string")
    if needle in source:return needle
    target,_=normalized_with_map(needle);haystack,positions=normalized_with_map(source)
    if len(target)<3:raise GroundError("too short for normalized matching")
    found=[];start=haystack.find(target)
    while start>=0:
        found.append(start);start=haystack.find(target,start+1)
    if len(found)!=1:raise GroundError("normalized quote absent or ambiguous")
    start=found[0]
    return source[positions[start]:positions[start+len(target)-1]+1]

def repair(raw,source):
    raw=copy.deepcopy(raw);changes=[]
    # Full evidence quote first, then participants and nested source quotes.
    q=locate(raw["quote"],source)
    if q!=raw["quote"]:changes.append("quote");raw["quote"]=q
    for field in ("subject","target"):
        if field not in raw:continue
        before=raw[field]
        scope=raw["quote"] if normalized_with_map(before)[0] in normalized_with_map(raw["quote"])[0] else source
        raw[field]=locate(before,scope)
        if before!=raw[field]:changes.append(field)
    for group in ("conditions","outcomes"):
        for index,item in enumerate(raw.get(group,[])):
            for field in ("quote","baseline_quote"):
                if field not in item:continue
                before=item[field]
                item[field]=locate(before,source)
                if before!=item[field]:changes.append(f"{group}/{index}/{field}")
    if not changes:raise GroundError("no eligible format-only change")
    return raw,changes

def scan(run,out):
    run,out=Path(run),Path(out);out.mkdir(parents=True,exist_ok=True)
    m=read(run/"input_manifest.json")
    lookup={u["block"]["id"]:(d,u) for d in m["documents"] for u in d["units"]}
    candidates={};attempted=0
    for path in (run/"units").glob("*.json"):
        row=read(path)
        d,u=lookup[row["unit_id"]]
        for error in row.get("errors",[]):
            for rejected in error.get("rejected",[]):
                raw=rejected.get("fact")
                if not isinstance(raw,dict):continue
                attempted+=1
                try:
                    corrected,changes=repair(raw,u["block"]["text"])
                    ingest(empty_bundle(d["document"],[u["block"]]),u["block"]["id"],{"facts":[corrected]},"format_alignment_candidate")
                except Exception:continue
                ident=fid(u["block"]["id"],corrected)
                case={"id":ident,"unit_id":u["block"]["id"],"document_id":d["document"]["id"],
                    "title":d["document"]["title"],"source":u["block"]["text"],"context":u.get("context",""),
                    "raw":corrected,"origin_kind":u["origin"]["kind"],"original_rejected_fact":raw,
                    "changed_source_fields":changes,"status":"candidate_not_accepted"}
                case["rule"]=triage(case);candidates[ident]=case
    dump_jsonl(out/"candidates.jsonl",list(candidates.values()))
    report={"rejected_facts_attempted":attempted,"format_only_groundable_candidates":len(candidates),
            "added_to_graph":0,"requires_semantic_verification":True,
            "allowed_changes":"NFKC, whitespace, zero-width/soft-hyphen and minus glyphs only; literal source text replaces formatted spans"}
    write(out/"summary.json",report)
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();scan(a.run,a.out)
