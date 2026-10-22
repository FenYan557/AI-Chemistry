"""Retrieve source facts and RAG blocks through the active resolved entity graph."""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

from answer_context import build_context
from runtime_common import ROOT, lexical, load, file_digest


def alias_match(alias, query):
    alias, query = lexical(alias), lexical(query, fold_natural=False)
    if not alias:
        return False
    if re.search(r'[a-z]{3,}', alias):
        alias, query = alias.casefold(), query.casefold()
    # Keep formula/acronym case, and avoid matching MG inside DMG.
    if re.fullmatch(r"[A-Za-z0-9+^_-]+", alias):
        return bool(re.search(r"(?<![A-Za-z0-9-])" + re.escape(alias) + r"(?![A-Za-z0-9-])", query))
    return alias in query


def select(artifact, query, limit=8):
    if not query.strip() or limit < 1:
        raise ValueError("nonempty query and positive limit required")
    concept_scores, forward, acronym_anchors, named_anchors = {}, set(), set(), set()
    is_term = len(query.strip()) <= 100 and not re.search(r'[?？。;；\n]', query)
    generic = {"copper", "cobalt", "nickel", "water", "hydrogen", "electrolyte",
               "additive", "additives", "metal", "metals", "cathode", "anode"}
    for concept in artifact["concepts"]:
        matches = []
        for alias in concept['aliases'] + [concept['canonical_label']]:
            if alias_match(alias, query):
                matches.append(min(len(alias), 45))
                forward.add(concept["id"])
                if concept["kind"] in {"chemical", "material"} and not concept.get("composite_name"):
                    if re.fullmatch(r"[A-Z][A-Z0-9-]{1,11}", alias.strip()):
                        acronym_anchors.add(concept["id"])
                    elif len(alias.strip()) >= 4 and lexical(alias).casefold() not in generic:
                        named_anchors.add(concept["id"])
            elif is_term and alias_match(query, alias):
                matches.append(min(len(query.strip()), 45))
        if matches:
            concept_scores[concept["id"]] = max(matches)
    # Named chemicals constrain retrieval before generic property labels can compete.
    focus = acronym_anchors or named_anchors
    if focus and not any(any(p["concept_id"] in focus for p in f["participants"])
                         for f in artifact["contextual_facts"]):
        # An entity with no extracted facts still supplies its own source blocks.
        no_focus_facts = True
    else:
        no_focus_facts = False
    scored = []
    tokens = {x.casefold() for x in re.findall(r"[A-Za-z]{4,}", query)}
    asks_hypothesis = bool(re.search(r"hypothes|speculat|propos|推测|假说|可能", query, re.I))
    for fact in artifact["contextual_facts"]:
        participants = {p["concept_id"] for p in fact["participants"]}
        hit = participants & concept_scores.keys()
        if not hit:
            continue
        anchor_hit = participants & focus
        if focus and not anchor_hit:
            continue
        text = " ".join(e.get("quote", "") for e in fact["evidence"])
        score = 100 * len(anchor_hit) + sum(min(concept_scores[c], 8) for c in hit)
        score += sum(2 for word in tokens if word in text.casefold())
        if fact.get("outcomes"):
            score += 2
        if fact.get("conditions"):
            score += 1
        if not asks_hypothesis:
            score += {"observation": 3, "calculation_result": 1}.get(fact.get("statement_type"), 0)
            score += {"explicit": 2, "hedged": -2, "speculative": -4}.get(fact.get("modality"), 0)
        scored.append((score, fact["fact_id"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return {"concept_scores": concept_scores, "focus_concept_ids": sorted(focus),
            "fact_ids": [fid for _, fid in scored[:limit]],
            "total_matching_facts": len(scored), "focus_has_no_facts": no_focus_facts,
            "selection_policy": "named_object_first_then_query_relevance"}


def retrieve(graph, artifact, query, limit=8, block_limit=4, relation_context=None):
    selected = select(artifact, query, limit)
    context = build_context(graph, selected["fact_ids"], limit=limit)
    concepts = {c["id"]: c for c in artifact["concepts"]}
    selected_ids = set(selected.get("focus_concept_ids") or selected["concept_scores"])
    context["matched_entities"] = [{"name": concepts[c]["canonical_label"], "kind": concepts[c]["kind"],
                                     "identity_review_required": concepts[c].get("identity_review_required", False)}
                                    for c in sorted(selected_ids, key=lambda c: -selected["concept_scores"][c])]
    # Raw blocks support mentions that have no extracted facts. Keep their source
    # anchors separate; a co-occurrence in a block never creates a new graph edge.
    blocks = {b["id"]: b for b in graph["blocks"]}
    mention = {m["id"]: m for m in graph["mentions"]}
    scores = Counter()
    for mid, cid in artifact["mention_to_concept"].items():
        if cid in selected_ids:
            bid = mention[mid]["evidence"].get("block_id")
            if bid in blocks:
                scores[bid] += selected["concept_scores"][cid]
    source_blocks = []
    correction_path = ROOT / "registry/source_corrections.json"
    correction_rows = load(correction_path) if correction_path.is_file() else []
    corrections = {r["original_ocr_block_id"]: r["corrected_block_id"] for r in correction_rows}
    seen_blocks = set()
    for original_bid, _ in scores.most_common():
        if len(source_blocks) >= block_limit:
            break
        bid = corrections.get(original_bid, original_bid)
        if bid not in blocks:
            bid = original_bid
        if bid in seen_blocks:
            continue
        seen_blocks.add(bid)
        block = blocks[bid]
        relevant = [mention[mid]["evidence"]["start"] for mid, cid in artifact["mention_to_concept"].items()
                    if cid in selected_ids and mention[mid]["evidence"].get("block_id") == bid]
        start = max(0, min(relevant, default=0) - 450)
        end = min(len(block["text"]), start + 2200)
        citation = "R%d" % (len(source_blocks) + 1)
        source_blocks.append({"citation": citation, "text": block["text"][start:end],
                              "page": block.get("page"), "section": block.get("section"),
                              **({"source_note": "此为原始PDF校核后的摘录；原OCR块存在已确认错误，摘录不代表覆盖原块全部内容。", "original_ocr_block_id": original_bid} if bid != original_bid else {})})
        context["references"][citation] = {"document_id": block["document_id"], "block_id": bid,
                                           "start": start, "end": end, "quote": block["text"][start:end]}
    context["source_blocks"] = source_blocks
    context["instruction"] += "\n实体名称已归一，但不同文献/样品/实验的条件和数值仍分别属于各自来源；家族成员不等同。source_blocks是补充原文，可引用[R1]等；仅共现不能证明因果或作用关系。identity_review_required为true的名称涉及未核实OCR，不得据此确认化学身份。"
    context["retrieval"] = {"focus_concept_ids": selected.get("focus_concept_ids", []), "selection_policy": selected["selection_policy"], "matching_concepts": len(selected_ids), "matching_facts": selected["total_matching_facts"],
                            "returned_facts": len(context["evidence"]), "returned_blocks": len(source_blocks)}
    if relation_context is not None:
        from relation_context_retrieval import append_context
        context = append_context(context, graph, artifact, relation_context, query, selected_ids, limit)
    return context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--resolution", type=Path)
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    current = load(ROOT / "CURRENT.json")
    path = args.resolution or (ROOT / current["entity_resolution"])
    artifact = load(path)
    if not args.resolution and file_digest(path) != current['entity_resolution_sha256']:
        raise ValueError('active entity resolution hash mismatch')
    if args.graph:
        graph_path = args.graph
    elif args.resolution:
        source_path = Path(artifact["source_graph"])
        graph_path = source_path if source_path.is_absolute() else path.parent / source_path
    else:
        graph_path = ROOT / current["graph"]
    if file_digest(graph_path) != artifact["source_sha256"]:
        raise ValueError("resolution/source graph hash mismatch")
    graph = load(graph_path)
    from relation_context_retrieval import load_active
    supplemental = load_active(current, ROOT, graph, artifact) if not args.resolution and not args.graph else None
    result = retrieve(graph, artifact, args.query, args.limit, relation_context=supplemental)
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content)


if __name__ == "__main__":
    main()
