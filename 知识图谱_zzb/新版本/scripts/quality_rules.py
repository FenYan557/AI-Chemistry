"""Precision-first triage. Rules detect risk; a low-risk label is not semantic gold."""
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

RULE_VERSION = "qa-rules-1"
NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
HEDGE = re.compile(r"\b(propos\w*|hypothes\w*|suggest\w*|may|might|could|expected|assum\w*|likely)\b", re.I)
INC = re.compile(r"\b(increas\w*|enhanc\w*|accelerat\w*|promot\w*|improv\w*)\b",re.I)
DEC = re.compile(r"\b(decreas\w*|reduc\w*|suppress\w*|inhibit\w*|retard\w*)\b",re.I)
STAGE = re.compile(r"\b(anneal\w*|after|before|post[- ]?\w*|heat treatment|as[- ]deposited)\b",re.I)

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def normalized(value):
    return re.sub(r"\s+", "", str(value).replace("−","-").replace("–","-").replace("µ","μ")).casefold()

def fid(block_id, raw):
    return "f:"+hashlib.sha256((block_id+"|"+json.dumps(raw,ensure_ascii=False,sort_keys=True)).encode("utf-8")).hexdigest()[:16]

def numbers(value):
    return set(NUMBER.findall(str(value).replace("−","-")))

def triage(row):
    f, text = row["raw"], row["source"]
    reasons, hard = [], []
    quote = f.get("quote","")
    if not quote or quote not in text:
        hard.append("fact_quote_not_in_source")
    if f.get("subject") not in quote or (f.get("target") and f["target"] not in quote):
        reasons.append("participant_outside_main_quote")
    subj = f.get("subject","").strip()
    if len(subj)>90 or re.search(r"mechanism|behavior of|effects? of|results? of|analysis of",subj,re.I):
        reasons.append("event_like_subject")
    if re.fullmatch(r"it|they|this|that|these|those|we|the results?",subj,re.I):
        reasons.append("unresolved_reference")
    if f.get("relation") in ("effect","adsorption") and not f.get("target"):
        reasons.append("missing_structured_target")
    if row.get("origin_kind") in ("table","equation"):
        reasons.append("table_or_equation_binding")
    if f.get("statement") in ("observation","calculation_result") and HEDGE.search(quote):
        reasons.append("certainty_or_statement_type")
    if f.get("relation") in ("effect","adsorption") and re.search(r"investigat|studied|study of|selected as|was employed|was used|characterized using",quote,re.I):
        reasons.append("study_intent_or_method_not_effect_proof")
    if f.get("relation")=="mechanism":
        reasons.append("mechanism_requires_semantic_check")
    if row.get("review_article") and f.get("statement")=="observation":
        reasons.append("review_as_direct_observation")
    if re.search(r"\[\s*\d+|et al\.", quote) and f.get("statement")=="observation":
        reasons.append("cited_result_attribution")
    cs, os = f.get("conditions",[]), f.get("outcomes",[])
    if len(cs)>1 or len(os)>1:
        reasons.append("multiple_conditions_or_outcomes")
    vals = " ".join(x.get("value","") for x in cs).lower()
    if ("low" in vals and "high" in vals) or re.search(r"low[- ]concentration.*high[- ]concentration",quote,re.I):
        reasons.append("concentration_regime_binding")
    if any(c.get("about")=="subject" for c in cs) and re.search("mechanism",subj,re.I):
        reasons.append("condition_bound_to_mechanism")
    for item in cs+os:
        evidence=item.get("quote","")
        if not evidence or evidence not in text:
            hard.append("nested_quote_not_in_source")
        if item.get("kind")=="numeric" or numbers(item.get("value","")):
            if not numbers(item.get("value","")).issubset(numbers(evidence)):
                reasons.append("numeric_value_not_local_to_evidence")
                if re.fullmatch(r"[-+]?\d+(?:\.\d+)?",str(item.get("value","")).strip()):
                    hard.append("scalar_value_not_anchored_to_its_quote")
            local_scalar=(f.get("relation")=="measurement" and len(os)==1 and not cs and
                item.get("kind")=="numeric" and len(numbers(evidence))==1 and
                bool(item.get("unit")) and normalized(item["unit"]) in normalized(evidence) and
                bool(item.get("indicator")) and normalized(item["indicator"]) in normalized(quote) and
                not STAGE.search(text) and not item.get("baseline"))
            if not local_scalar:reasons.append("quantitative_fact")
        unit=item.get("unit")
        if unit and normalized(unit) not in normalized(evidence):
            reasons.append("unit_not_local_to_evidence")
        if item.get("about")=="experiment":
            reasons.append("experiment_scope_requires_check")
    for outcome in os:
        evidence=outcome.get("quote",quote)
        direction=outcome.get("direction")
        if (direction=="increase" and DEC.search(evidence)) or (direction=="decrease" and INC.search(evidence)):
            reasons.append("possible_direction_mismatch")
        if "baseline" in outcome:
            reasons.append("comparison_baseline_binding")
            bq=outcome.get("baseline_quote","")
            if not bq or bq not in text:
                hard.append("baseline_quote_not_in_source")
            if not numbers(outcome["baseline"]).issubset(numbers(bq)):
                reasons.append("baseline_value_not_local")
                if re.fullmatch(r"[-+]?\d+(?:\.\d+)?",str(outcome["baseline"]).strip()):
                    hard.append("scalar_baseline_not_anchored_to_its_quote")
        if outcome.get("stage") or (outcome.get("kind")=="numeric" and STAGE.search(quote)):
            reasons.append("treatment_stage_binding")
    if f.get("relation")=="future_work" or f.get("statement")=="future_work":
        reasons.append("future_not_demonstrated")
    reasons, hard = sorted(set(reasons)),sorted(set(hard))
    return {"rule_version":RULE_VERSION,"tier":"hard_error" if hard else ("semantic_check" if reasons else "low_risk"),
            "reasons":reasons,"hard_errors":hard}

def load_cases(run):
    run=Path(run)
    manifest=read(run/"input_manifest.json")
    units={u["block"]["id"]:(d,u) for d in manifest["documents"] for u in d["units"]}
    rows={}
    statuses=Counter()
    for path in sorted((run/"units").glob("*.json")):
        checkpoint=read(path); statuses[checkpoint["status"]]+=1
        doc,unit=units[checkpoint["unit_id"]]
        for raw in checkpoint.get("response",{}).get("facts",[]):
            ident=fid(checkpoint["unit_id"],raw)
            row={"id":ident,"unit_id":checkpoint["unit_id"],"document_id":checkpoint["document_id"],
                 "title":doc["document"]["title"],"source":unit["block"]["text"],"context":unit.get("context",""),
                 "raw":raw,"origin_kind":unit["origin"]["kind"],"unit_status":checkpoint["status"],
                 "review_article":bool(re.search(r"\breview\b|progress|advances|perspective|综述",doc["document"]["title"],re.I))}
            row["rule"]=triage(row); rows[ident]=row
    return list(rows.values()),{"unit_statuses":dict(statuses),"source_fingerprint":manifest["input_fingerprint"]}

def select_audit(rows, n=120, seed=20261020):
    low=sorted((r for r in rows if r["rule"]["tier"]=="low_risk"),key=lambda r:r["id"])
    sample=random.Random(seed).sample(low,min(n,len(low)))
    selected={r["id"] for r in rows if r["rule"]["tier"]=="semantic_check"}
    selected.update(r["id"] for r in sample)
    return selected,{r["id"] for r in sample}

def dump_jsonl(path,rows):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8") as f:
        for row in rows: f.write(json.dumps(row,ensure_ascii=False)+"\n")
