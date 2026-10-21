"""Create a full KG candidate by adding pending entities, preserving existing facts.

No LLM requests. Relation review queues are source candidates, never inferred edges.
"""
import argparse,copy,json,hashlib
from pathlib import Path
from collections import Counter,defaultdict
from batch_extract import ROOT,read,write,now
from validate import validate

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def merge(base,delta):
    result=copy.deepcopy(base)
    for key in ("documents","blocks"):
        indexed={item["id"]:item for item in base[key]}
        for item in delta[key]:
            if indexed.get(item["id"])!=item:raise ValueError("source snapshot mismatch: "+key)
    for key in ("mentions","entities","identities"):
        indexed={item["id"]:item for item in result[key]}
        for item in delta[key]:
            if item["id"] in indexed:
                if indexed[item["id"]]!=item:raise ValueError("conflicting ID: "+item["id"])
                continue
            if key=="entities" and item["identity_id"] is not None:raise ValueError("candidate cannot confirm identity")
            if key=="identities" and item["status"]=="reviewed":raise ValueError("candidate cannot claim human review")
            result[key].append(copy.deepcopy(item));indexed[item["id"]]=item
    links={(x["mention_id"],x["identity_id"]) for x in result["identity_links"]}
    for link in delta["identity_links"]:
        if link["review"]!="pending":raise ValueError("candidate identity link must remain pending")
        pair=link["mention_id"],link["identity_id"]
        if pair not in links:result["identity_links"].append(copy.deepcopy(link));links.add(pair)
    # Existing arrays, including IDs and qualifier/evidence fields, are immutable.
    for key in ("facts","edges","role_assignments","experiments","runs","samples","identity_merges","external_records"):
        assert result[key]==base[key]
    for key in ("mentions","entities"):
        assert result[key][:len(base[key])]==base[key]
    return result

def relation_queue(graph,delta):
    facts_by_block=defaultdict(list);mentions_by_block=defaultdict(list)
    for fact in graph["facts"]:
        for sid in {e["block_id"] for e in fact["evidence"] if e["kind"]=="block"}:
            facts_by_block[sid].append(fact)
    for mention in delta["mentions"]:mentions_by_block[mention["evidence"]["block_id"]].append(mention)
    result=[]
    for sid,mentions in mentions_by_block.items():
        facts=facts_by_block[sid];open_facts=[f for f in facts if f["relation"]["candidate_relation_id"] is None]
        result.append({"document_id":mentions[0]["document_id"],"source_id":sid,
                       "new_mention_ids":[m["id"] for m in mentions],"existing_fact_ids":[f["id"] for f in facts],
                       "unmapped_relation_fact_ids":[f["id"] for f in open_facts],
                       "priority":"reuse_existing_facts_first" if open_facts else "source_bound_gap_check",
                       "review":"pending","note":"Entity co-occurrence is only a review trigger, not relationship evidence."})
    return sorted(result,key=lambda x:(x["priority"]!="reuse_existing_facts_first",x["document_id"],x["source_id"]))

def run(base_path,entity_run,out):
    if (out/"knowledge_graph.json").exists():raise ValueError("output already exists; do not overwrite frozen candidate")
    patch=read(entity_run/"entity_enrichment_patch.json")
    if sha(base_path)!=patch["base_graph_sha256"]:raise ValueError("base graph fingerprint mismatch")
    base=read(base_path);delta=read(entity_run/"candidate_delta.json");graph=merge(base,delta)
    validation=validate(graph);write(out/"validation.json",validation)
    if not validation["valid"]:raise ValueError("full graph validation blocked; inspect validation.json")
    write(out/"knowledge_graph.json",graph)
    write(out/"entity_annotations_pending.json",patch["existing_annotations"])
    queue=relation_queue(graph,delta);write(out/"relation_source_review_queue.json",queue)
    summary={"created_at":now(),"status":"entity_integrated_candidate","base_graph":str(base_path),"base_sha256":sha(base_path),
             "entity_delta":str(entity_run/"candidate_delta.json"),"entity_delta_sha256":sha(entity_run/"candidate_delta.json"),
             "candidate_sha256":sha(out/"knowledge_graph.json"),"documents":len(graph["documents"]),"mentions":len(graph["mentions"]),
             "entities":len(graph["entities"]),"added_mentions":len(delta["mentions"]),"identities":len(graph["identities"]),
             "identity_status":dict(Counter(i["status"] for i in graph["identities"])),"pending_identity_links":len(graph["identity_links"]),
             "existing_facts_preserved":len(graph["facts"]),"existing_edges_preserved":len(graph["edges"]),
             "relation_counts":dict(Counter(f["relation"]["candidate_relation_id"] or "unmapped" for f in graph["facts"])),
             "relation_review_source_blocks":len(queue),"relation_queue_means":"candidate source blocks, not asserted missing relations",
             "new_relations_extracted":0,"network_calls":0,"model_tokens":0,"full_graph_validation":validation["valid"],
             "validation_tiers":validation["tier_counts"],"production_graph_unchanged":sha(base_path)==patch["base_graph_sha256"],
             "human_review":"pending","unresolved_identities_not_promoted":True}
    write(out/"integration_summary.json",summary);print(json.dumps(summary,ensure_ascii=False))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--base",type=Path,default=ROOT/"reports/full_extraction_20261020/quality/precision_graph.json")
    p.add_argument("--entities",type=Path,default=ROOT/"reports/entity_corpus_reuse_20261021/normalized");p.add_argument("--out",type=Path,required=True);a=p.parse_args();run(a.base,a.entities,a.out)
