"""结构校验复用jsonschema；本文件做引用、身份、条件、物化层与三档处置的本地适配。

三档来自 schema/constraints.json：block=入库拒绝，review=保留待审（降级），warn=事后统计。
检查通过不表示事实正确；没有命令会自动把pending改成reviewed。
"""
import argparse
import copy
from defaults import normalize
import csv
import json
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def code_tiers():
    """错误码→档位；未登记的码按 block 处理并报 CONSTRAINT_CATALOG_GAP。"""
    tiers = {}
    for item in load(ROOT / "schema/constraints.json")["constraints"]:
        for code in item["codes"]:
            tiers[code] = item["severity"]
    return tiers


def validate(bundle):
    bundle = normalize(bundle)
    schema = load(ROOT / "schema/records.schema.json")
    Draft202012Validator.check_schema(schema)
    tiers = code_tiers()
    findings, unmapped = [], []

    def add(code, message):
        tier = tiers.get(code)
        if tier is None:
            unmapped.append(code)
            tier = "block"
        findings.append({"code": code, "tier": tier, "message": message})

    err = add
    warn = add

    for e in Draft202012Validator(schema).iter_errors(bundle):
        err("STRUCTURE", "/".join(map(str, e.absolute_path)) + ": " + e.message)
    if any(f["code"] == "STRUCTURE" for f in findings):
        for code in unmapped:
            add("CONSTRAINT_CATALOG_GAP", code)
        return _result(findings, [], None, None)

    def index(key):
        result = {}
        for item in bundle.get(key) or []:
            if item["id"] in result:
                err("DUPLICATE_ID", key + ":" + item["id"])
            result[item["id"]] = item
        return result

    docs, blocks = index("documents"), index("blocks")
    mentions, identities, external = index("mentions"), index("identities"), index("external_records")
    experiments, runs, samples = index("experiments"), index("runs"), index("samples")
    facts_by_id = index("facts")
    entity_types = {t["type_id"]: t for t in load(ROOT / "registry/entity_types.json")["types"]}
    relation_registry = {r["relation_id"]: r for r in load(ROOT / "registry/relations.json")["relations"]}
    relation_ids = set(relation_registry)

    tables_dir = ROOT / "tables"

    def evidence(e, doc_id, context):
        if e.get("kind") == "table_cell":
            missing = [k for k in ("table_id", "row", "col", "cell_raw") if k not in e]
            if missing:
                err("EVIDENCE_FIELD_MISSING", context + ":" + ",".join(missing))
                return
            if not e["table_id"].startswith(doc_id):
                err("CROSS_DOCUMENT_EVIDENCE", context)
            path = tables_dir / (e["table_id"] + ".csv")
            if not path.exists():
                warn("TABLE_CSV_NOT_FOUND", context + ":" + e["table_id"])
                return
            rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
            if e["row"] >= len(rows) or e["col"] >= len(rows[e["row"]]):
                err("TABLE_CELL_OUT_OF_RANGE", context)
                return
            if rows[e["row"]][e["col"]] != e["cell_raw"]:
                err("TABLE_CELL_MISMATCH", context)
            return
        if e.get("kind") != "block":
            err("EVIDENCE_KIND_UNKNOWN", context)
            return
        if not {"block_id", "start", "end", "quote"} <= set(e):
            err("EVIDENCE_FIELD_MISSING", context)
            return
        b = blocks.get(e["block_id"])
        if not b:
            err("MISSING_BLOCK", context + ":" + e["block_id"])
            return
        if b["document_id"] != doc_id:
            err("CROSS_DOCUMENT_EVIDENCE", context)
        if not (0 <= e["start"] < e["end"] <= len(b["text"])):
            err("INVALID_SPAN", context)
        elif b["text"][e["start"]:e["end"]] != e["quote"]:
            err("QUOTE_MISMATCH", context)
        if b["page"] is None:
            warn("PAGE_UNRESOLVED", context)

    def literal_evidence(e, context):
        """合并不是同文献行为，证据可跨篇；只核对逐字与偏移，不核对 document_id。"""
        if e.get("kind") != "block":
            evidence(e, "", context)
            return
        b = blocks.get(e["block_id"])
        if not b:
            err("MISSING_BLOCK", context + ":" + e["block_id"])
            return
        if not (0 <= e["start"] < e["end"] <= len(b["text"])):
            err("INVALID_SPAN", context)
        elif b["text"][e["start"]:e["end"]] != e["quote"]:
            err("QUOTE_MISMATCH", context)

    def quoted(e):
        return e.get("quote", e.get("cell_raw", ""))

    def quantity(q, context):
        if q["value_kind"] in {"numeric", "ordinal"} and not q["value_raw"]:
            err("VALUE_MISSING", context)
        if q["value_kind"] == "absent" and q["value_raw"] is not None:
            err("VALUE_STATE_INCONSISTENT", context)
        if q["unit_status"] == "reported" and not q["unit_raw"]:
            err("UNIT_STATE_INCONSISTENT", context)
        if q["unit_status"] in {"not_reported", "not_applicable"} and q["unit_raw"] is not None:
            err("UNIT_STATE_INCONSISTENT", context)

    for b in blocks.values():
        if b["document_id"] not in docs:
            err("MISSING_DOCUMENT", b["id"])
    for m in mentions.values():
        if m["document_id"] not in docs:
            err("MISSING_DOCUMENT", m["id"])
        evidence(m["evidence"], m["document_id"], m["id"])
        if m["surface"] != quoted(m["evidence"]):
            err("MENTION_SURFACE_MISMATCH", m["id"])
        for candidate in m["candidate_type_ids"]:
            if candidate not in entity_types:
                warn("NEW_TYPE_CANDIDATE", m["id"] + ":" + candidate)

    for ident in identities.values():
        if ident["scope"] == "document" and ident["document_id"] not in docs:
            err("IDENTITY_SCOPE", ident["id"])
        if ident["scope"] == "global" and ident["document_id"] is not None:
            err("IDENTITY_SCOPE", ident["id"])
        for ext_id in ident["external_refs"]:
            if ext_id not in external:
                err("MISSING_EXTERNAL_RECORD", ident["id"] + ":" + ext_id)

    for link in bundle["identity_links"]:
        m, ident = mentions.get(link["mention_id"]), identities.get(link["identity_id"])
        if not m or not ident:
            err("IDENTITY_REFERENCE", str(link))
            continue
        if ident["scope"] == "document" and ident["document_id"] != m["document_id"]:
            err("CROSS_DOCUMENT_ALIAS", link["mention_id"])
        for e in link["evidence"]:
            evidence(e, m["document_id"], "identity:" + m["id"])
        ext = external.get(link["external_ref"])
        if link["external_ref"] is not None and not ext:
            err("MISSING_EXTERNAL_RECORD", m["id"])
        # 名称相似只能作候选；篇内括注不能自动变成全局同一性。
        if link["review"] == "reviewed":
            if ident["status"] != "reviewed":
                err("IDENTITY_REVIEW_MISMATCH", m["id"])
            if link["basis"] == "name_candidate":
                err("NAME_ONLY_IDENTITY_MERGE", m["id"])
            if link["basis"] == "database" and (not ext or ext["match_status"] != "reviewed"):
                err("UNREVIEWED_DATABASE_MATCH", m["id"])
            if link["basis"] in {"structure", "author_explicit"} and not link["evidence"]:
                err("IDENTITY_EVIDENCE_REQUIRED", m["id"])
            if ident["scope"] == "global" and link["basis"] == "author_explicit":
                err("GLOBAL_ALIAS_NEEDS_IDENTITY_EVIDENCE", m["id"])
        if link["review"] == "pending":
            warn("IDENTITY_PENDING", m["id"])

    # ── 标识与合并：合并/拆分必须留痕，且不得自相矛盾 ──
    merge_pairs = {}
    seen_merges = set()
    for merge in bundle.get("identity_merges") or []:
        mid = merge["id"]
        if mid in seen_merges:
            err("MERGE_DUPLICATE", mid)
        seen_merges.add(mid)
        a, b = identities.get(merge["from_identity_id"]), identities.get(merge["to_identity_id"])
        if not a or not b:
            err("MERGE_IDENTITY_MISSING", mid)
            continue
        if a["id"] == b["id"]:
            err("MERGE_SELF", mid)
        for e in merge["evidence"]:
            literal_evidence(e, mid)
        if merge["relation"] == "same_as":
            if merge["review"] == "reviewed":
                if not merge["evidence"]:
                    err("MERGE_UNVERIFIED_SAME_AS", mid)
                if merge["basis"] == "name_candidate":
                    err("MERGE_UNVERIFIED_SAME_AS", mid)
                if a["status"] != "reviewed" or b["status"] != "reviewed":
                    err("MERGE_UNVERIFIED_SAME_AS", mid)
                if a["scope"] == "document" and b["scope"] == "document" and a["document_id"] != b["document_id"]:
                    err("MERGE_CROSS_DOCUMENT_UNREVIEWED", mid)
            elif merge["basis"] == "name_candidate" and not merge["evidence"]:
                warn("MERGE_DISTINCT_WITHOUT_EVIDENCE", mid)
        elif not merge["evidence"]:
            warn("MERGE_DISTINCT_WITHOUT_EVIDENCE", mid)
        key = frozenset((merge["from_identity_id"], merge["to_identity_id"]))
        merge_pairs.setdefault(key, set()).add(merge["relation"])
    for key, kinds in merge_pairs.items():
        if {"same_as", "distinct_from"} <= kinds:
            err("MERGE_CONTRADICTION", "|".join(sorted(key)))

    # ── L2 事件与 L3 样品：共享条件与处理前后状态 ──
    for exp in experiments.values():
        if exp["document_id"] not in docs:
            err("MISSING_DOCUMENT", exp["id"])
        for e in exp["evidence"]:
            evidence(e, exp["document_id"], exp["id"])

    for run in runs.values():
        if run["document_id"] not in docs:
            err("MISSING_DOCUMENT", run["id"])
        if run["experiment_id"] is not None:
            exp = experiments.get(run["experiment_id"])
            if not exp:
                err("EXPERIMENT_MISSING", run["id"])
            elif exp["document_id"] != run["document_id"]:
                err("EXPERIMENT_CROSS_DOCUMENT", run["id"])
        for e in run["evidence"]:
            evidence(e, run["document_id"], run["id"])
        for item in run["conditions"]:
            quantity(item["value"], run["id"])
            for e in item["evidence"]:
                evidence(e, run["document_id"], run["id"] + ":condition")

    for sample in samples.values():
        if sample["document_id"] not in docs:
            err("MISSING_DOCUMENT", sample["id"])
        for e in sample["evidence"]:
            evidence(e, sample["document_id"], sample["id"])
        if sample["derived_from_sample_id"] is not None:
            parent = samples.get(sample["derived_from_sample_id"])
            if not parent:
                err("SAMPLE_PARENT_MISSING", sample["id"])
            elif parent["document_id"] != sample["document_id"]:
                err("SAMPLE_CROSS_DOCUMENT", sample["id"])
            elif parent["id"] == sample["id"]:
                err("SAMPLE_SELF_PARENT", sample["id"])

    # ── L2 功能角色：受控多选，绑定使用性事实与条件，不产生无条件永久角色 ──
    role_options = {r["id"] for r in load(ROOT / "registry/roles.json")["options"]}
    seen_roles = set()
    role_stats = {}
    for assignment in bundle.get("role_assignments", []):
        rid = assignment["id"]
        fact = facts_by_id.get(assignment["fact_id"])
        if not fact:
            err("ROLE_FACT_MISSING", rid)
            continue
        if assignment["functional_role"] not in role_options:
            err("ROLE_OPTION_UNKNOWN", rid)
        mention = mentions.get(assignment["subject_mention_id"])
        if not mention:
            err("ROLE_SUBJECT_MISSING", rid)
        else:
            if mention["document_id"] != fact["document_id"]:
                err("ROLE_CROSS_DOCUMENT", rid)
            if assignment["subject_mention_id"] not in {p["mention_id"] for p in fact["participants"]}:
                err("ROLE_SUBJECT_NOT_PARTICIPANT", rid)
        for e in assignment["evidence"]:
            evidence(e, fact["document_id"], rid)
        raw = assignment["role_raw"]
        if assignment["functional_role"] == "other" and not raw:
            err("ROLE_OTHER_NEEDS_RAW", rid)
        if assignment["role_basis"] == "author_explicit" and not raw:
            err("ROLE_EXPLICIT_NEEDS_RAW", rid)
        if assignment["functional_role"] == "unknown" and assignment["role_basis"] != "unknown":
            err("ROLE_UNKNOWN_BASIS", rid)
        if assignment["functional_role"] != "unknown" and assignment["role_basis"] == "unknown":
            err("ROLE_KNOWN_WITHOUT_BASIS", rid)
        if assignment["role_basis"] == "effect_inference" and assignment["functional_role"] in {"accelerator", "suppressor"}:
            warn("ROLE_FROM_EFFECT_ONLY", rid)
        if assignment["role_basis"] == "author_explicit" and raw:
            if not any(raw in quoted(e) for e in assignment["evidence"]):
                warn("ROLE_RAW_NOT_LITERAL_IN_CITED_EVIDENCE", rid)
        if fact["statement_type"] == "future_work":
            warn("ROLE_ON_FUTURE_WORK", rid)
        if assignment["functional_role"] in {"accelerator", "suppressor"} and not fact["conditions"]:
            warn("ROLE_WITHOUT_RECORDED_CONDITION", rid)
        key = (assignment["fact_id"], assignment["subject_mention_id"], assignment["functional_role"])
        if key in seen_roles:
            err("ROLE_DUPLICATE", rid)
        seen_roles.add(key)
        role_stats[assignment["functional_role"]] = role_stats.get(assignment["functional_role"], 0) + 1

    reports = []
    for fact in bundle["facts"]:
        fid, doc_id = fact["id"], fact["document_id"]
        if doc_id not in docs:
            err("MISSING_DOCUMENT", fid)
        participants = set()
        for part in fact["participants"]:
            mid = part["mention_id"]
            participants.add(mid)
            if mid not in mentions:
                err("MISSING_PARTICIPANT", fid + ":" + mid)
            elif mentions[mid]["document_id"] != doc_id:
                err("CROSS_DOCUMENT_PARTICIPANT", fid + ":" + mid)
        for e in fact["evidence"]:
            evidence(e, doc_id, fid)
        rid = fact["relation"]["candidate_relation_id"]
        if rid is None or rid not in relation_ids:
            warn("OPEN_RELATION_CANDIDATE", fid + ":" + str(rid))
        reasons = []
        run = runs.get(fact.get("run_id")) if fact.get("run_id") else None
        if fact.get("run_id") and not run:
            err("RUN_MISSING", fid)
        elif run and run["document_id"] != doc_id:
            err("RUN_CROSS_DOCUMENT", fid)
        cited = fact.get("cited_work") or {}
        if fact["source_scope"] == "cited_study" and not cited.get("raw"):
            warn("CITED_WORK_MISSING", fid)
        if fact["source_scope"] != "cited_study" and cited.get("raw"):
            warn("CITED_WORK_UNEXPECTED", fid)
        if cited.get("document_id") and cited["document_id"] not in docs:
            err("MISSING_DOCUMENT", fid + ":cited_work")
        for condition in fact["conditions"]:
            if not set(condition["about_mention_ids"]).issubset(participants):
                err("CONDITION_OWNER", fid)
            if condition.get("inherited"):
                if not run:
                    err("INHERITED_CONDITION_WITHOUT_RUN", fid)
                else:
                    same = [c for c in run["conditions"]
                            if c["parameter_raw"] == condition["parameter_raw"]]
                    if not same:
                        err("INHERITED_CONDITION_NOT_IN_RUN", fid)
                    elif same[0]["value"]["value_raw"] != condition["value"]["value_raw"]:
                        err("INHERITED_CONDITION_VALUE_MISMATCH", fid)
            quantity(condition["value"], fid)
            for e in condition["evidence"]:
                evidence(e, doc_id, fid + ":condition")
                if condition["value"]["value_raw"] is not None and condition["value"]["value_raw"] not in quoted(e):
                    warn("CONDITION_VALUE_NOT_LITERAL", fid)
            if condition["scope_status"] == "pending":
                reasons.append("condition_scope_pending")
        for outcome in fact["outcomes"]:
            quantity(outcome["value"], fid)
            if outcome.get("sample_id"):
                sample = samples.get(outcome["sample_id"])
                if not sample:
                    err("SAMPLE_MISSING", fid)
                elif sample["document_id"] != doc_id:
                    err("SAMPLE_CROSS_DOCUMENT", fid)
            for e in outcome["evidence"]:
                evidence(e, doc_id, fid + ":outcome")
            numeric_value = outcome["value"]["value_kind"] in {"numeric", "ordinal"}
            literal = any((outcome["value"]["value_raw"] or "") in quoted(e) for e in outcome["evidence"])
            if numeric_value and not literal:
                err("OUTCOME_VALUE_NOT_LITERAL", fid)
            if outcome["value"]["unit_status"] in {"not_reported", "unresolved"}:
                reasons.append("unit_missing_or_unresolved")
            # 程度限定：有程度必须有原措辞；原措辞不被逐字引用只作审计提示。
            mag = outcome.get("magnitude") or {"raw": None, "qualifier": "unknown"}
            if mag["qualifier"] != "unknown" and not mag["raw"]:
                err("MAGNITUDE_WITHOUT_RAW", fid)
            if mag["raw"] and not any(mag["raw"] in quoted(e) for e in outcome["evidence"]):
                warn("MAGNITUDE_RAW_NOT_LITERAL", fid)
            # 比较基准：基准状态与基准串必须一致；基准提及必须存在且在本事实内。
            comp = outcome.get("comparison") or {}
            if comp.get("status") in {"explicit", "raw_only"} and not comp.get("baseline_raw"):
                err("COMPARISON_BASELINE_MISSING", fid)
            if comp.get("status") == "not_stated" and comp.get("baseline_raw"):
                err("COMPARISON_BASELINE_MISSING", fid)
            for e in comp.get("evidence", []):
                evidence(e, doc_id, fid + ":baseline")
            if comp.get("baseline_raw"):
                sources = comp.get("evidence", []) + outcome["evidence"] + fact["evidence"]
                if not any(comp["baseline_raw"] in quoted(e) for e in sources):
                    err("COMPARISON_BASELINE_NOT_LITERAL", fid)
            if comp.get("baseline_mention_id"):
                if comp["baseline_mention_id"] not in mentions:
                    err("COMPARISON_MENTION_MISSING", fid)
                elif comp["baseline_mention_id"] not in participants:
                    warn("COMPARISON_MENTION_NOT_PARTICIPANT", fid)
        if not fact["conditions"]:
            reasons.append("conditions_not_recorded")
        if fact["statement_type"] in {"future_work", "author_interpretation", "unknown"}:
            reasons.append("not_direct_observation")
        if fact["source_scope"] in {"cited_study", "review_summary", "unknown"}:
            reasons.append("source_scope_requires_review")
        # 不给任何记录自动授予定量比较、因果推断、推荐资格。
        reports.append({
            "fact_id": fid, "storage": "retained_if_valid",
            "numeric_comparison": "blocked" if reasons else "not_assessed",
            "causal_inference": "not_assessed", "recommendation": "not_assessed",
            "reasons": sorted(set(reasons)),
        })

    # 图端点/数量必须与登记角色投影一致，不能仅核对边限定词。
    if "edges" in bundle:
        from materialize import materialize
        try:
            expected = materialize(copy.deepcopy(bundle))["edges"]
        except ValueError as exc:
            err("ENTITY_ID_CONFLICT", str(exc))
            expected = []
        def edge_shape(edges):
            return sorted((e["id"], e["fact_id"], e["from_entity_id"], e["to_entity_id"]) for e in edges)
        if edge_shape(bundle["edges"]) != edge_shape(expected):
            err("EDGE_DERIVATION_MISMATCH", "边的端点或数量不符合登记角色投影")

    # ── 物化层：实体与边必须由记录层派生，不得自带新语义 ──
    entities_by_id = {}
    for entity in bundle.get("entities") or []:
        eid = entity["id"]
        if eid in entities_by_id:
            err("ENTITY_DUPLICATE", eid)
        entities_by_id[eid] = entity
        mention = mentions.get(entity["from_mention_id"])
        if not mention:
            err("ENTITY_MENTION_MISSING", eid)
        else:
            if entity["document_id"] != mention["document_id"]:
                err("ENTITY_CROSS_DOCUMENT", eid)
            if entity["label"] != mention["surface"]:
                err("ENTITY_LABEL_MISMATCH", eid)
        if entity["identity_id"] is not None:
            ident = identities.get(entity["identity_id"])
            if not ident:
                err("ENTITY_IDENTITY_MISSING", eid)
            else:
                if ident["scope"] == "document" and ident["document_id"] != entity["document_id"]:
                    err("ENTITY_CROSS_DOCUMENT", eid)
                reviewed = any(l["mention_id"] == entity["from_mention_id"]
                               and l["identity_id"] == entity["identity_id"]
                               and l["review"] == "reviewed"
                               for l in bundle["identity_links"])
                if not reviewed:
                    warn("ENTITY_IDENTITY_LINK_MISMATCH", eid)
        if entity["type_id"] is None:
            warn("ENTITY_UNTYPED", eid)
        else:
            declared = entity_types.get(entity["type_id"])
            if not declared:
                warn("ENTITY_TYPE_UNKNOWN", eid + ":" + entity["type_id"])
            elif declared["status"] != "core" or not declared["criteria"]:
                warn("ENTITY_TYPE_UNDERSPECIFIED", eid + ":" + entity["type_id"])
        for e in entity["evidence"]:
            evidence(e, entity["document_id"], eid)
    if bundle.get("entities"):
        covered = {e["from_mention_id"] for e in bundle["entities"]}
        for mid in mentions:
            if mid not in covered:
                warn("ENTITY_COVERAGE_GAP", mid)

    edges_by_id = {}
    for edge in bundle.get("edges") or []:
        eid = edge["id"]
        if eid in edges_by_id:
            err("EDGE_DUPLICATE", eid)
        edges_by_id[eid] = edge
        fact = facts_by_id.get(edge["fact_id"])
        head = entities_by_id.get(edge["from_entity_id"])
        tail = entities_by_id.get(edge["to_entity_id"])
        if not fact:
            err("EDGE_FACT_MISSING", eid)
        if not head or not tail:
            err("EDGE_ENTITY_MISSING", eid)
        if not fact or not head or not tail:
            continue
        q = edge["qualifiers"]
        for field in ("statement_type", "source_scope", "polarity", "modality"):
            if q[field] != fact[field]:
                err("EDGE_SEMANTICS_DRIFT", eid + ":" + field)
        if q["conditions"] != fact["conditions"]:
            err("EDGE_SEMANTICS_DRIFT", eid + ":conditions")
        if edge["relation"] != fact["relation"]:
            err("EDGE_SEMANTICS_DRIFT", eid + ":relation")
        if edge["review"] != fact["review"]:
            err("EDGE_SEMANTICS_DRIFT", eid + ":review")
        if edge["evidence"] != fact["evidence"]:
            warn("EDGE_EVIDENCE_DIFFERS", eid)
        for e in edge["evidence"]:
            evidence(e, fact["document_id"], eid)
        declared = relation_registry.get(edge["relation"]["candidate_relation_id"])
        if declared:
            if declared["status"] != "core":
                warn("EDGE_RELATION_PROPOSED", eid + ":" + declared["relation_id"])
            if head["type_id"] and declared["domain_types"] and head["type_id"] not in declared["domain_types"]:
                warn("EDGE_DOMAIN_MISMATCH", eid + ":" + head["type_id"])
            if tail["type_id"] and declared["range_types"] and tail["type_id"] not in declared["range_types"]:
                warn("EDGE_RANGE_MISMATCH", eid + ":" + tail["type_id"])
            card = declared["cardinality"]
            if not (card["min_participants"] <= len(fact["participants"]) <= card["max_participants"]):
                warn("EDGE_CARDINALITY", eid)
    if bundle.get("edges"):
        edge_facts = {e["fact_id"] for e in bundle["edges"]}
        for fact in bundle["facts"]:
            declared = relation_registry.get(fact["relation"]["candidate_relation_id"], {})
            roles = {p["role"] for p in fact["participants"]}
            projection = declared.get("projection", {})
            should_edge = bool(roles.intersection(projection.get("from_roles", [])) and roles.intersection(projection.get("to_roles", [])))
            if should_edge and fact["id"] not in edge_facts:
                warn("EDGE_COVERAGE_GAP", fact["id"])

    for code in unmapped:
        err("CONSTRAINT_CATALOG_GAP", code)
    return _result(findings, reports, role_stats, {"entities": len(entities_by_id), "edges": len(edges_by_id)})


def _result(findings, reports, role_stats, graph):
    by_tier = {"block": [], "review": [], "warn": []}
    for item in findings:
        by_tier[item["tier"]].append(item)
    result = {
        "valid": not by_tier["block"],
        "tier_counts": {k: len(v) for k, v in by_tier.items()},
        "errors": by_tier["block"],
        "warnings": by_tier["review"] + by_tier["warn"],
        "facts": reports or [],
        "roles": role_stats or {},
        "graph": graph or {},
        "semantics_verified": False,
        "note": "三档：block 入库拒绝 / review 保留待审 / warn 事后统计。只验证结构与出处一致性；通过不证明同一身份、研究结论或全库覆盖。",
    }
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("bundle", type=Path)
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    result = validate(load(args.bundle))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": result["valid"], "tiers": result["tier_counts"],
                      "facts": len(result["facts"]), "roles": result.get("roles", {}),
                      "graph": result.get("graph", {})}, ensure_ascii=False))
    raise SystemExit(0 if result["valid"] else 1)
