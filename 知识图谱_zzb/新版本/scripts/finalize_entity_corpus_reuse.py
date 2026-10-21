"""Validate saved responses locally and build a derived entity view without API calls.

Raw responses remain immutable. Per-record issues never discard unrelated valid
records or cause a paid retry. Conflicting AI decisions are retained for review.
"""
import argparse,copy,json,re,shutil
from pathlib import Path
from collections import Counter,defaultdict
from jsonschema import Draft202012Validator
import entity_corpus_reuse as reuse
from entity_extract_pilot import ground,ENTITY
from batch_extract import ROOT,read,write,now

def guard_entity(entity):
    """Stage-specific generic guards; preserve raw model proposals separately."""
    e=copy.deepcopy(entity);notes=[];name=e["name"]
    if e["category"]=="chemical" and e["kind"]=="not_chemical":
        e.update(category="unknown",kind="unknown",identity_uncertain=True);notes.append("chemical_nonchemical_conflict_kept_unresolved")
    if e["category"]=="chemical" and re.search(r"\b(foil|sheet|rod|plates?|anode|cathode|electrode|coating|film)\b",name,re.I):
        e.update(category="material",kind="not_chemical");notes.append("metal_material_or_device_not_chemical_identity")
    if e["category"]=="chemical" and e["kind"]=="metal_ion":
        cat,kind,_=reuse.classify(name)
        if re.search(r"\([\d\s−-]{2,}\)",name):
            e.update(category="material",kind="not_chemical");notes.append("crystal_plane_is_not_metal_ion")
        elif kind=="nonmetal_ion":
            e["kind"]=kind;notes.append("nonmetal_ion_is_not_metal_ion")
        elif kind!="metal_ion":
            e.update(kind="unknown",identity_uncertain=True);notes.append("metal_ion_without_unambiguous_charge_held")
    if e["category"]=="chemical":
        compact=re.sub(r"[\s_^{}]","",name)
        formula_or_acronym=bool(re.fullmatch(r"(?:[A-Z][a-z]?|\d|[+−\-·.()~])+",compact))
        if formula_or_acronym and reuse.classify(name)[1]!="metal_ion":
            e["identity_uncertain"]=True
            notes.append("formula_or_abbreviation_identity_stays_unresolved")
    kept=[]
    for d in e["distinctions"]:
        context_amount=d["kind"]=="other" and re.search(r"ppm|(?:mg|g|mol|mmol)\s*[·/]?\s*[lL]\b|\b[mμ]?M\b|CAS\s*(?:No|number)",d["value"])
        if context_amount:notes.append("experimental_amount_or_registry_metadata_not_identity_specification")
        else:kept.append(d)
    e["distinctions"]=kept
    if e["category"]!="chemical":e["kind"]="not_chemical"
    return e,notes

def input_windows(task,blocks):
    windows=defaultdict(list)
    for s in task["segments"]:
        block=blocks[s["source_id"]]
        assert block["text"][s["start"]:s["end"]]==s["text"]
        windows[s["source_id"]].append(s["text"])
    for c in task["candidates"]:
        block=blocks[c["source_id"]];lo=c["context_start"]
        assert block["text"][lo:lo+len(c["context"])]==c["context"]
        windows[c["source_id"]].append(c["context"])
    return windows

def normalize(result,task,blocks):
    result=copy.deepcopy(result);issues=[]
    original_status=result.get("status")
    if result.get("finish_reason")=="length" or not isinstance(result.get("data"),dict):return result,[{"reason":"incomplete_response_not_retried"}]
    data=result["data"];allowed={c["id"] for c in task["candidates"]};candidate_map={c["id"]:c for c in task["candidates"]}
    updates=defaultdict(list);not_entities={}
    for u in data.get("updates",[]):
        if list(Draft202012Validator(reuse.UPDATE).iter_errors(u)) or u["id"] not in allowed:
            issues.append({"reason":"invalid_update","record":u});continue
        if u["category"]!="chemical" and u["kind"]!="not_chemical":
            issues.append({"reason":"nonchemical_kind_corrected_to_not_chemical","record":copy.deepcopy(u)});u["kind"]="not_chemical"
        if u["kind"]=="unknown":u["identity_uncertain"]=True
        guarded,notes=guard_entity({"name":candidate_map[u["id"]]["name"],"category":u["category"],"kind":u["kind"],"identity_uncertain":u["identity_uncertain"],"distinctions":[]})
        if notes:issues.append({"reason":"generic_identity_guard","candidate_id":u["id"],"notes":notes,"original_proposal":copy.deepcopy(u)})
        u.update({key:guarded[key] for key in ("category","kind","identity_uncertain")})
        updates[u["id"]].append(u)
    for n in data.get("not_entities",[]):
        if not isinstance(n,dict) or n.get("id") not in allowed or not isinstance(n.get("reason"),str):
            issues.append({"reason":"invalid_deletion_proposal","record":n});continue
        not_entities[n["id"]]={"id":n["id"],"reason":n["reason"]}
    selected=[]
    for cid,items in updates.items():
        unique={reuse.fingerprint(u):u for u in items}
        if cid in not_entities or len(unique)>1:
            issues.append({"reason":"conflicting_decisions_kept_pending","candidate_id":cid,"updates":items,"deletion":not_entities.get(cid)})
            # Neither correction nor deletion becomes a final assertion.
            continue
        selected.append(items[0])
    windows=input_windows(task,blocks);segments=[{"source_id":sid,"text":blocks[sid]["text"]} for sid in windows]
    good=[];quarantined=[];seen=set()
    for i,original in enumerate(data.get("additions",[])):
        if list(Draft202012Validator(ENTITY).iter_errors(original)):
            issues.append({"reason":"invalid_addition_schema","index":i,"record":original})
            if not isinstance(original,dict) or not isinstance(original.get("name"),str) or not isinstance(original.get("source_id"),str):continue
            category=original.get("category","unknown")
            if category not in ENTITY["properties"]["category"]["enum"]:category="unknown"
            kind=original.get("kind","unknown")
            if kind not in ENTITY["properties"]["kind"]["enum"]:kind="unknown" if category in ("chemical","unknown") else "not_chemical"
            aliases=[a for a in original.get("aliases",[]) if not list(Draft202012Validator(ENTITY["properties"]["aliases"]["items"]).iter_errors(a))]
            distinctions=[d for d in original.get("distinctions",[]) if not list(Draft202012Validator(ENTITY["properties"]["distinctions"]["items"]).iter_errors(d))]
            original={"name":original["name"],"source_id":original["source_id"],"category":category,"kind":kind,"aliases":aliases,"distinctions":distinctions,"identity_uncertain":True}
        accepted,bad=ground({"entities":[original]},segments)
        if bad:
            # Salvage a literal name while preserving suspect alias/spec fields as
            # a separate review item. Never repair a chemical formula.
            sources={s["source_id"]:s["text"] for s in segments}
            e=copy.deepcopy(original)
            e["aliases"]=[a for a in e["aliases"] if reuse.locate(a["surface"],a["source_id"],sources) and (not a.get("basis_quote") or reuse.locate(a["basis_quote"],a["source_id"],sources))]
            e["distinctions"]=[d for d in e["distinctions"] if reuse.locate(d["value"],d["source_id"],sources)]
            e["identity_uncertain"]=True
            accepted,remaining=ground({"entities":[e]},segments)
            if remaining:
                quarantined.append({"index":i,"entity":original,"reason":"name_not_literal_in_supplied_source"});continue
            issues.append({"reason":"name_recovered_optional_fields_held","index":i,"record":original,"bad_fields":bad[0]["issues"]})
        e=accepted[0]
        # The full block is available locally for accurate offsets, but acceptance
        # requires that every field was actually visible to the model.
        name_visible=any(e["name"] in w for w in windows.get(e["source_id"],[]))
        if not name_visible:
            quarantined.append({"index":i,"entity":original,"reason":"name_outside_supplied_excerpt"});continue
        aliases=[]
        for alias in e["aliases"]:
            q=alias.get("basis_quote","")
            visible=any(alias["surface"] in w and q and q in w for w in windows.get(alias["source_id"],[]))
            if visible and e["name"] in q and alias["surface"] in q:aliases.append(alias)
            else:issues.append({"reason":"alias_definition_held","index":i,"alias":alias})
        distinctions=[]
        for distinction in e["distinctions"]:
            if any(distinction["value"] in w for w in windows.get(distinction["source_id"],[])):distinctions.append(distinction)
            else:
                e["identity_uncertain"]=True;issues.append({"reason":"specification_not_in_visible_excerpt","index":i,"distinction":distinction})
        e["aliases"]=aliases;e["distinctions"]=distinctions
        if e["category"]!="chemical":e["kind"]="not_chemical"
        if e["kind"]=="unknown":e["identity_uncertain"]=True
        e,notes=guard_entity(e)
        if notes:issues.append({"reason":"generic_identity_guard","index":i,"notes":notes,"original_proposal":original})
        key=reuse.fingerprint({k:e[k] for k in ("name","source_id","category","kind","aliases","distinctions")})
        if key in seen:continue
        seen.add(key);good.append(e)
    result.update(status="success",data={"updates":selected,"not_entities":list(not_entities.values()),"additions":[{k:v for k,v in e.items() if k in ENTITY["properties"]} for e in good],"coverage_notes":data.get("coverage_notes","")},grounded=good,quarantined=quarantined,
                  normalization={"created_at":now(),"original_status":original_status,"method":"local_record_validation_no_api","normalizer_sha256":reuse.checksum(__file__),"issues":issues})
    result.pop("error",None);result.pop("paths",None)
    return result,issues

def stable_preview_and_patch(preview,pool,base):
    """Preserve existing mention/entity IDs; propose annotations without merging."""
    anchor_key=lambda m:(m["document_id"],m["evidence"]["block_id"],m["evidence"]["start"],m["evidence"]["end"])
    base_mentions={anchor_key(m):m for m in base["mentions"]}
    base_entities={e["from_mention_id"]:e for e in base["entities"]}
    ids={};existing=set();annotations=[];pool_by_mention={r["mention_id"]:r for r in pool}
    for mention in preview["mentions"]:
        original=base_mentions.get(anchor_key(mention));old_id=mention["id"]
        if original:
            assert original["surface"]==mention["surface"]
            mention["id"]=original["id"];ids[old_id]=original["id"];existing.add(original["id"])
            row=pool_by_mention[old_id]
            annotations.append({"mention_id":original["id"],"entity_id":base_entities[original["id"]]["id"],"candidate_id":row["id"],"proposed_category":row["category"],"proposed_kind":row["kind"],"proposed_type_id":row["proposed_type_id"],"identity_candidate_id":row.get("identity_candidate_id"),"semantic_qa":row["semantic_qa"],"human_review":"pending"})
    for entity in preview["entities"]:
        previous=entity["from_mention_id"]
        if previous in ids:
            entity["from_mention_id"]=ids[previous];entity["id"]=base_entities[ids[previous]]["id"]
    for row in pool:row["mention_id"]=ids.get(row["mention_id"],row["mention_id"])
    for link in preview["identity_links"]:link["mention_id"]=ids.get(link["mention_id"],link["mention_id"])
    assert existing=={m["id"] for m in base["mentions"]}
    assert len({m["id"] for m in preview["mentions"]})==len(preview["mentions"])
    valid_mentions={m["id"]:m for m in preview["mentions"]};valid_identities={i["id"]:i for i in preview["identities"]}
    for link in preview["identity_links"]:
        assert valid_mentions[link["mention_id"]]["document_id"]==valid_identities[link["identity_id"]]["document_id"]
    delta={**preview,"mentions":[m for m in preview["mentions"] if m["id"] not in existing],"entities":[e for e in preview["entities"] if e["from_mention_id"] not in existing]}
    patch={"operation":"propose_entity_annotations_and_additions","human_review":"pending","existing_annotations":annotations,"new_mention_ids":[m["id"] for m in delta["mentions"]],"identity_links_target":"base mentions plus new delta mentions","facts_and_relations_modified":False,"automatic_application":False}
    return preview,pool,delta,patch

def finalize(out):
    out=out.resolve()
    graph=read(reuse.BASE/"quality/precision_graph.json");blocks={b["id"]:b for b in graph["blocks"]}
    tasks=read(out/"tasks.json");normalized=out/"normalized";normalized.mkdir(exist_ok=True)
    # A derived view carries explicit source hashes. Raw response files are not
    # rewritten and no result is relabelled as newly model-reviewed.
    for name in ("plan.json","tasks.json","reused_pool.jsonl"):
        shutil.copyfile(out/name,normalized/name)
    # Reuse explicit author definitions from old terminology, without asking a
    # model to rediscover them. Mere co-occurrence in a quote is insufficient.
    source_pool=reuse.lines(normalized/"reused_pool.jsonl");glossaries={};alias_count=0
    raw_pool={r["id"]:r for r in source_pool};before_units=len(raw_pool);unit_inputs=[]
    for unit_file in sorted((reuse.BASE/"units").glob("*.json")):
        unit=read(unit_file);sid=unit.get("unit_id")
        if sid not in blocks:continue
        block=blocks[sid];unit_inputs.append({"path":str(unit_file.relative_to(ROOT)),"sha256":reuse.checksum(unit_file)})
        for index,fact in enumerate(unit.get("response",{}).get("facts",[])):
            quote=fact.get("quote","")
            if not quote or quote not in block["text"]:continue
            names=[fact.get("subject"),fact.get("object")]
            names += [item.get("indicator") for item in fact.get("outcomes",[]) if isinstance(item,dict)]
            names += [item.get("parameter") for item in fact.get("conditions",[]) if isinstance(item,dict)]
            for name in names:
                if not isinstance(name,str) or name not in quote:continue
                ev=reuse.anchor(name,block,quote)
                if ev:reuse.pool_add(raw_pool,block["document_id"],block,name,{"artifact":str(unit_file.relative_to(ROOT)),"fact_index":index,"reuse_scope":"entity_surface_only"},evidence=ev)
    raw_unit_additions=len(raw_pool)-before_units
    omissions_path=ROOT/"reports/entity_acceptance_20261021/omitted_entity_queue.json";before_omissions=len(raw_pool)
    if omissions_path.exists():
        for item in read(omissions_path):
            block=blocks[item["source_id"]]
            for name in item["alternatives"]:
                if name not in block["text"]:continue
                category=item["category"]
                entity={"category":category,"kind":"unknown" if category=="chemical" else "not_chemical","aliases":[],"distinctions":[],"identity_uncertain":category=="chemical"}
                reuse.pool_add(raw_pool,block["document_id"],block,name,{"artifact":str(omissions_path.relative_to(ROOT)),"qa":"prior_reference_candidate_reused"},entity=entity)
    reference_additions=len(raw_pool)-before_omissions
    source_pool=list(raw_pool.values())
    write(normalized/"raw_unit_inputs.json",unit_inputs)
    for row in source_pool:
        if row["primary_reused"]:continue
        for provenance in row["provenance"]:
            artifact=provenance.get("artifact","")
            if "glossaries" not in Path(artifact).parts or "term" not in provenance:continue
            if artifact not in glossaries:glossaries[artifact]=read(ROOT/artifact)
            term=glossaries[artifact]["terms"][provenance["term"]]
            if row["surface"]!=term["surface"]:continue
            quote=term.get("quote","")
            for alias in term.get("aliases",[]):
                pattern=re.escape(row["surface"])+r"\s*\([^)]*\b"+re.escape(alias)+r"\b[^)]*\)"
                if not re.search(pattern,quote):continue
                if quote not in blocks[row["source_id"]]["text"]:continue
                value={"surface":alias,"source_id":row["source_id"],"basis_quote":quote}
                if value not in row["aliases"]:row["aliases"].append(value);alias_count+=1
    reuse.dump(normalized/"reused_pool.jsonl",source_pool)
    issues=[];raw_statuses=Counter();counts=Counter();derived_results=[]
    for task in tasks:
        source=out/"responses"/task["task_id"];path=source/"result.json"
        if not path.exists():continue
        original=read(path);raw_statuses[original.get("status","unknown")]+=1
        derived,problems=normalize(original,task,blocks)
        derived_results.append(derived)
        derived["raw_response_artifact"]={"path":str(path.relative_to(ROOT)),"sha256":reuse.checksum(path)}
        target=normalized/"responses"/task["task_id"]
        write(target/"result.json",derived)
        if (source/"response_metadata.json").exists():shutil.copyfile(source/"response_metadata.json",target/"response_metadata.json")
        for problem in problems:
            issues.append({"document_id":task["document_id"],**problem});counts[problem["reason"]]+=1
    # Reuse a document-local category hint across identical surface strings.
    # This does not create aliases, normalize names or merge chemical identities.
    donors=defaultdict(list);original_rows={r["id"]:r for r in source_pool};held_ids=set()
    for response in derived_results:
        if response.get("status")!="success":continue
        held_ids.update(n["id"] for n in response["data"]["not_entities"])
        for update in response["data"]["updates"]:
            row=original_rows[update["id"]]
            donors[(row["document_id"],row["surface"])].append((update["category"],update["kind"],row["id"]))
    for row in source_pool:
        supported=row["primary_reused"] or any("glossaries" in Path(p.get("artifact","")).parts for p in row["provenance"])
        if supported and row["category"]!="unknown":donors[(row["document_id"],row["surface"])].append((row["category"],row["kind"],row["id"]))
    propagated=0
    for row in source_pool:
        if row["category"]!="unknown" or row["primary_reused"] or row["id"] in held_ids:continue
        choices=donors[(row["document_id"],row["surface"])];categories={c for c,k,rid in choices if c!="unknown"}
        if len(categories)!=1:continue
        cat=next(iter(categories));row["category"]=cat
        row["kind"]="unknown" if cat=="chemical" else "not_chemical"
        row["identity_uncertain"]=cat=="chemical";row["semantic_qa"]="document_category_hint_pending"
        row["provenance"].append({"artifact":"document_local_category_reuse","basis_candidate_ids":sorted({rid for c,k,rid in choices if c==cat}),"note":"coarse category only; no alias or identity equivalence"});propagated+=1
    reuse.dump(normalized/"reused_pool.jsonl",source_pool)
    reuse.dump(normalized/"local_validation_issues.jsonl",issues)
    write(normalized/"normalization_summary.json",{"raw_statuses":dict(raw_statuses),"local_issue_counts":dict(counts),"raw_unit_files_reused":len(unit_inputs),"raw_unit_additional_name_anchors":raw_unit_additions,"prior_reference_additional_anchors":reference_additions,"glossary_author_aliases_reused":alias_count,"document_local_category_hints_reused":propagated,"api_calls":0,"source_run":str(out),"note":"Record-level recovery from existing responses; conflicting AI corrections not applied; literal source candidates only, not expert truth."})
    reuse.build(normalized)
    preview,pool,delta,patch=stable_preview_and_patch(read(normalized/"entity_pool_preview.json"),reuse.lines(normalized/"enriched_pool.jsonl"),graph)
    primary_path=out/"primary_corpus_reviews.json";primary_holds=[]
    if primary_path.exists():
        by_id={r["id"]:r for r in pool};base_ids={m["id"] for m in graph["mentions"]}
        for review in read(primary_path)["records"]:
            if review["action"]!="hold_new_candidate":continue
            row=by_id[review["candidate_id"]];assert row["mention_id"] not in base_ids,"base records require annotation, not deletion"
            row.update(primary_disposition="held_not_entity",semantic_qa="primary_agent_checked")
            primary_holds.append({**row,"primary_reason":review["reason"]})
        held_ids={r["mention_id"] for r in primary_holds}
        preview["mentions"]=[m for m in preview["mentions"] if m["id"] not in held_ids]
        preview["entities"]=[e for e in preview["entities"] if e["from_mention_id"] not in held_ids]
        preview["identity_links"]=[l for l in preview["identity_links"] if l["mention_id"] not in held_ids]
        used={l["identity_id"] for l in preview["identity_links"]};preview["identities"]=[i for i in preview["identities"] if i["id"] in used]
        delta={**preview,"mentions":[m for m in preview["mentions"] if m["id"] not in base_ids],"entities":[e for e in preview["entities"] if e["from_mention_id"] not in base_ids]}
        patch["new_mention_ids"]=[m["id"] for m in delta["mentions"]]
    reuse.dump(normalized/"primary_held_candidates.jsonl",primary_holds)
    patch["base_graph_sha256"]=read(out/"plan.json")["production_sha256"]
    write(normalized/"entity_pool_preview.json",preview);reuse.dump(normalized/"enriched_pool.jsonl",pool)
    write(normalized/"candidate_delta.json",delta);write(normalized/"entity_enrichment_patch.json",patch)
    reuse.dump(normalized/"chemical_candidates.jsonl",[r for r in pool if r["category"]=="chemical" and not r.get("primary_disposition")])
    inventory=defaultdict(list)
    for r in pool:
        if r.get("primary_disposition"):continue
        key=(r["document_id"],r["surface"],r["category"],r["kind"],tuple(sorted((d["kind"],d["value"]) for d in r["distinctions"])))
        inventory[key].append(r)
    reuse.dump(normalized/"entity_inventory.jsonl",[{"document_id":doc,"surface":surface,"category":cat,"kind":kind,"distinctions":[{"kind":k,"value":v} for k,v in distinctions],"occurrences":len(rows),"candidate_ids":[r["id"] for r in rows],"human_review":"pending","note":"inventory grouping, not chemical identity merging"} for (doc,surface,cat,kind,distinctions),rows in inventory.items()])
    summary=read(normalized/"summary.json");summary.update(enriched_mentions=len(preview["mentions"]),additional_mentions_vs_curated_graph=len(delta["mentions"]),stable_existing_mention_ids_preserved=len(patch["existing_annotations"]),new_mention_ids=len(patch["new_mention_ids"]),inventory_groups=len(inventory),raw_unit_additional_name_anchors=raw_unit_additions,glossary_author_aliases_reused=alias_count,document_local_category_hints_reused=propagated,primary_held_new_candidates=len(primary_holds))
    write(normalized/"summary.json",summary)
    grouped=defaultdict(list)
    held_candidates={r["id"] for r in primary_holds}
    for r in reuse.lines(normalized/"review_queue.jsonl"):
        if r["candidate_id"] not in held_candidates:grouped[(r["document_id"],r["surface"],tuple(r["flags"]))].append(r)
    reuse.dump(normalized/"review_groups.jsonl",[{"document_id":doc,"surface":surface,"flags":list(flags),"occurrences":len(items),"candidate_ids":[r["candidate_id"] for r in items],"example_sources":list(dict.fromkeys(r["source_id"] for r in items))[:2],"human_review":"pending"} for (doc,surface,flags),items in grouped.items()])
    bydoc={r["document_id"]:r for r in read(out/"coverage_plan.json")};document_status=[]
    for result in derived_results:
        row=copy.deepcopy(bydoc[result["document_id"]]);row.update(response_status=result["status"],raw_status=result.get("normalization",{}).get("original_status",result["status"]),coverage_notes=result.get("data",{}).get("coverage_notes",""),grounded_completion_records=len(result.get("grounded",[])),quarantined_records=len(result.get("quarantined",[])),human_review="pending")
        document_status.append(row)
    write(normalized/"document_status.json",document_status)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);finalize(p.parse_args().run)
