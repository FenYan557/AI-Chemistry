"""Conservative, logged field downgrades for demonstrated semantic failure classes."""
import argparse
import copy
import json
import re
from pathlib import Path
from quality_rules import fid,triage,dump_jsonl
from batch_extract import read,write

RESULT=re.compile(r"observed|revealed|showed|demonstrated|exhibited|increas|decreas|suppress|inhibit|accelerat|refin|shift|发现|表明|增加|降低|减小|抑制|观察|显示|变为",re.I)
PROTOCOL=re.compile(r"scan range|scan(?:ning)? (?:speed|rate)|frequency range|amplitude|scan.*cycles|test.*conducted|was (?:performed|carried out) at|测试.*(?:范围|频率|速度)|扫描.*(?:范围|速率|速度)|频率范围",re.I)
CALC=re.compile(r"software.*(?:used|determine|calculat|display)|was (?:calculated|plotted)|were (?:calculated|plotted)|采用.*计算|使用.*计算",re.I)
CAUSAL=re.compile(r"explain|leads? to|caus|induc|promot|inhibit|suppress|mechanism|解释|导致|抑制|促进|机理",re.I)

def weaken(raw,source):
    new=copy.deepcopy(raw);changes=[]
    quote=raw["quote"]
    if raw["statement"]=="observation" and not raw.get("outcomes") and PROTOCOL.search(quote) and not RESULT.search(quote):
        new["statement"]="reported_claim";new["relation"]="other";changes.append("protocol_not_observation")
    if raw["relation"]=="effect" and re.search(r"correlat|associated with|relationship between|相关|关联",quote,re.I):
        new["relation"]="other";changes.append("association_not_asserted_causation")
    if raw["relation"]=="effect" and re.search(r"effect$|behavior$|mechanism$|抑制效果|抑制效应",raw["subject"],re.I):
        new["relation"]="other";changes.append("event_or_location_not_causal_agent")
    if raw["relation"]=="mechanism" and not raw.get("outcomes") and CALC.search(quote) and not CAUSAL.search(quote):
        new["relation"]="other";changes.append("calculation_method_not_mechanism")
    if (raw["relation"]=="future_work" or raw["statement"]=="future_work") and re.search(r"上一节|下一节|本节|next section|this section|following section",source,re.I):
        new["relation"]="other";new["statement"]="reported_claim";changes.append("paper_section_plan_not_future_research")
    return new,changes

def build(run,out):
    run,out=Path(run),Path(out);out.mkdir(parents=True,exist_ok=True)
    rows=[json.loads(x) for x in (run/"quality/cases.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    candidates=[];old_flags={}
    original_ids={r["id"] for r in rows}
    for row in rows:
        raw,changes=weaken(row["raw"],row["source"])
        if not changes:continue
        old_flags[row["id"]]=changes
        ident=fid(row["unit_id"],raw)
        if ident in original_ids:continue
        candidate={**row,"id":ident,"raw":raw,"candidate_kind":"conservative_semantic_relabel",
                   "supersedes_id":row["id"],"changed_semantic_fields":changes}
        candidate["rule"]=triage(candidate);candidates.append(candidate)
    dump_jsonl(out/"cases.jsonl",candidates)
    write(out/"superseded_candidates.json",old_flags)
    from collections import Counter
    write(out/"summary.json",{"source_cases_requiring_weaker_expression":len(old_flags),"new_candidate_records":len(candidates),
        "rules":dict(Counter(x for flags in old_flags.values() for x in flags)),
        "numeric_values_units_quotes_and_participant_names_unchanged":True,
        "added_to_graph":0,"requires_AI_check":True})
    return candidates

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();build(a.run,a.out);print(json.dumps(read(a.out/"summary.json"),ensure_ascii=False))
