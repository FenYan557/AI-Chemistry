"""Build an isolated schema-conforming preview from explicitly recorded primary-agent reviews."""
import argparse,json,hashlib,copy
from pathlib import Path
from collections import Counter
from jsonschema import Draft202012Validator
from batch_extract import read,write
from entity_extract_pilot import locate,ground

def ident(prefix,*values):
    return prefix+":"+hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:20]

def identity_key(entity,approved_group=None):
    return {**({"primary_approved_group":approved_group} if approved_group else {"label":entity["name"]}),"kind":entity["kind"],
            "distinctions":sorted((d["kind"],d["value"]) for d in entity["distinctions"])}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--run",type=Path,required=True);a=ap.parse_args()
    root=Path(__file__).resolve().parents[1]
    reviews=read(a.run/"primary_reviews.json"); tasks=read(a.run/"tasks.json")
    taskmap={t["task_id"]:t for t in tasks}; source={s["source_id"]:s["text"] for t in tasks for s in t["segments"]}
    graphpath=root/"reports/full_extraction_20261020/quality/precision_graph.json"
    graph=read(graphpath); original_sha=hashlib.sha256(graphpath.read_bytes()).hexdigest()
    assert original_sha==read(a.run/"reference_checkpoints.json")["production_graph_sha256"]
    delta={k:[] for k,v in graph.items() if isinstance(v,list)}
    delta["schema_version"]=graph["schema_version"]
    docs={t["document_id"] for t in tasks}
    delta["documents"]=[d for d in graph["documents"] if d["id"] in docs]
    delta["blocks"]=[b for b in graph["blocks"] if b["id"] in source]
    assert len(delta["blocks"])==len(source)
    for b in delta["blocks"]: assert b["text"]==source[b["id"]]
    records=[]; identities={};mentions={};entities={};links={};held=[]
    for r in reviews["records"]:
        if r["action"]=="drop":held.append(r);continue
        e=r["final"]; task=taskmap[r["task_id"]]; doc=task["document_id"]
        grounded,rejected=ground({"entities":[e]},task["segments"]);assert not rejected
        if e["category"]!="chemical":assert e["kind"]=="not_chemical"
        if e["kind"]=="metal_ion":assert e["category"]=="chemical"
        identity_id=None
        if e["category"]=="chemical":
            key=identity_key(e,r.get("identity_group"))
            identity_id=ident("identity",doc,key)
            if identity_id not in identities:
                identities[identity_id]={"id":identity_id,"canonical_label":r.get("canonical_label",e["name"]),"scope":"document",
                    "document_id":doc,"status":r.get("identity_status","candidate"),"external_refs":[],
                    "distinctions":dict.fromkeys(["charge","salt_form","hydrate","stereochemistry","specification"])}
            i=identities[identity_id]
            for d in e["distinctions"]:
                slot={"salt_form":"salt_form","hydration":"hydrate","charge":"charge","molecular_weight":"specification","grade":"specification","other":"specification"}[d["kind"]]
                old=i["distinctions"][slot]
                if not old:i["distinctions"][slot]=d["value"]
                elif d["value"] not in old:i["distinctions"][slot]=old+"; "+d["value"]
            if r.get("identity_status")=="unresolved":i["status"]="unresolved"
        names=[{"surface":e["name"],"source_id":e["source_id"],"alias":False}]+[{**x,"alias":True} for x in e["aliases"]]
        for n in names:
            mid=ident("mention",doc,n["source_id"],n["surface"])
            ev={"kind":"block",**locate(n["surface"],n["source_id"],source)}
            mentions[mid]={"id":mid,"document_id":doc,"surface":n["surface"],"evidence":ev,
                "candidate_type_ids":r.get("candidate_type_ids",[])}
            entities[mid]={"id":ident("entity",mid),"document_id":doc,"label":n["surface"],"type_id":r.get("type_id"),
                "identity_id":None,"from_mention_id":mid,"evidence":[ev]}
            if identity_id:
                block=source[n["source_id"]]
                support={"kind":"block","block_id":n["source_id"],"start":0,"end":len(block),"quote":block}
                links[(mid,identity_id)]={"mention_id":mid,"identity_id":identity_id,
                    "basis":"author_explicit" if n["alias"] or e["aliases"] else "name_candidate",
                    "review":"pending","evidence":[support],"external_ref":None}
        records.append({**grounded[0],"record_id":r["record_id"],"document_id":doc,
            "proposed_type_id":r.get("type_id"),"identity_candidate_id":identity_id,
            "machine_qa":"literal_anchor_pass","semantic_qa":"primary_agent_checked","review":"pending"})
    delta.update(mentions=list(mentions.values()),entities=list(entities.values()),identities=list(identities.values()),identity_links=list(links.values()))
    schema=read(root/"schema/records.schema.json")
    # An entity-only delta is not a full KG instance: the latter requires >=1 fact.
    collection_defs={"documents":"document","blocks":"block","mentions":"mention","entities":"entity","identities":"identity","identity_links":"identity_link"}
    errors=[]
    for collection,definition in collection_defs.items():
        component_schema={"$ref":"#/$defs/"+definition,"$defs":schema["$defs"]}
        validator=Draft202012Validator(component_schema)
        for item in delta[collection]:errors.extend(validator.iter_errors(item))
    assert not errors,[(list(e.absolute_path),e.message) for e in errors][:5]
    for link in delta["identity_links"]:
        assert link["mention_id"] in mentions and link["identity_id"] in identities
    doc_ids={d["id"] for d in delta["documents"]}
    block_docs={b["id"]:b["document_id"] for b in delta["blocks"]}
    assert docs==doc_ids
    for m in mentions.values():
        ev=m["evidence"]
        assert block_docs[ev["block_id"]]==m["document_id"]
        assert source[ev["block_id"]][ev["start"]:ev["end"]]==ev["quote"]==m["surface"]
    for link in delta["identity_links"]:
        assert mentions[link["mention_id"]]["document_id"]==identities[link["identity_id"]]["document_id"]
    assert all(e["identity_id"] is None for e in delta["entities"])
    assert all(x["review"]=="pending" for x in delta["identity_links"])
    assert not delta["facts"] and not delta["edges"]
    write(a.run/"candidate_delta.json",delta)
    (a.run/"reviewed_entities.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in records),encoding="utf-8")
    write(a.run/"primary_quarantine.json",held)
    summary={"documents":len(docs),"source_blocks":len(source),"raw_records":len(reviews["records"]),
      "primary_retained_records":len(records),"primary_dropped_records":len(held),
      "categories":dict(Counter(r["category"] for r in records)),
      "distinct_mentions":len(mentions),"candidate_identities":len(identities),"pending_identity_links":len(links),
      "identity_status":dict(Counter(x["status"] for x in identities.values())),
      "typed_entities":sum(x["type_id"] is not None for x in entities.values()),
      "schema_component_validation_errors":len(errors),"full_graph_schema_validation":"not_applicable_entity_only_delta","production_sha256_unchanged":hashlib.sha256(graphpath.read_bytes()).hexdigest()==original_sha,
      "production_graph_modified":False,"human_review":"pending","cross_document_merges":0}
    write(a.run/"final_summary.json",summary); print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
