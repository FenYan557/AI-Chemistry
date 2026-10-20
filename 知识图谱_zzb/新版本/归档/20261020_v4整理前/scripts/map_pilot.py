"""把旧试跑输出映射到新协议，只做结构可表达性与可回指检查。\n\n不是重新抽取，不是金标，也不评价准确率。输出：\n- 58 个 mention 的原文可定位情况\n- 18 条 fact 的关系/条件/证据字段可映射情况\n- 明确写出无法映射的原因\n"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / "讨论/方法试跑_20261019"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    blocks = {}
    for line in (ROOT / "data/source_blocks.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            blocks[row["block_id"]] = row["text"]
    candidates = load(OLD / "01_candidates.json")
    proposals = load(OLD / "02_induced_proposals.json")
    type_by_mention = {m["mention_id"]: m["type_id"] for m in proposals["mention_mapping"]}
    registry_types = {t["type_id"] for t in load(ROOT / "registry/candidates.json")["types"]}
    fact_mapping = {f["fact_id"]: f for f in proposals["fact_mapping"]}
    relation_labels = {r["relation_id"]: r["label"] for r in proposals["canonical_relations"]}

    mention_rows = []
    for m in candidates["mentions"]:
        text = blocks.get(m["block_id"])
        locatable = text is not None and m["text"] in text
        type_id = type_by_mention.get(m["mention_id"])
        mention_rows.append({
            "mention_id": m["mention_id"],
            "surface": m["text"],
            "source_block_present": text is not None,
            "surface_literal_in_snapshot": locatable,
            "type_id": type_id,
            "type_in_candidate_registry": type_id in registry_types,
            "v2_representation": "mention_record",
        })

    fact_rows = []
    for f in candidates["facts"]:
        text = blocks.get(f["block_id"])
        quote = f.get("evidence_quote") or ""
        mapping = fact_mapping.get(f["fact_id"], {})
        rel_ids = mapping.get("relation_ids") or []
        relations = [relation_labels.get(r) for r in rel_ids]
        fact_rows.append({
            "fact_id": f["fact_id"],
            "participant_count": len(f.get("participants") or []),
            "has_relation_definition": bool(f.get("relation_definition")),
            "has_qualifier_fields": bool(f.get("qualifiers")),
            "has_discourse_status": bool(f.get("discourse_status")),
            "evidence_literal_in_snapshot": bool(text) and bool(quote) and quote in text,
            "relation_raw_uses_dot_ellipsis": "..." in (f.get("relation_raw") or ""),
            "evidence_uses_dot_ellipsis": "..." in quote,
            "requires_split": bool(mapping.get("requires_split")),
            "candidate_relations": [r for r in relations if r],
            "v2_representation": "fact_record + conditions + outcomes + role_assignments(若角色有据)",
        })

    report = {
        "not_a_reextraction": True,
        "not_gold": True,
        "mentions": {
            "total": len(mention_rows),
            "surface_literal_in_snapshot": sum(r["surface_literal_in_snapshot"] for r in mention_rows),
            "type_in_candidate_registry": sum(r["type_in_candidate_registry"] for r in mention_rows),
            "rows": mention_rows,
        },
        "facts": {
            "total": len(fact_rows),
            "evidence_literal_in_snapshot": sum(r["evidence_literal_in_snapshot"] for r in fact_rows),
            "evidence_uses_dot_ellipsis": sum(r["evidence_uses_dot_ellipsis"] for r in fact_rows),
            "relation_raw_uses_dot_ellipsis": sum(r["relation_raw_uses_dot_ellipsis"] for r in fact_rows),
            "requires_split": sum(r["requires_split"] for r in fact_rows),
            "with_relation_definition": sum(r["has_relation_definition"] for r in fact_rows),
            "with_qualifier_fields": sum(r["has_qualifier_fields"] for r in fact_rows),
            "rows": fact_rows,
        },
        "known_gaps": [
            "旧输出只有关系与参与者，没有功能角色字段；角色须按新协议逐个作答，不能由旧结果直接继承。",
            "旧输出未区分样品处理前后状态，电阻率类事实需按阶段拆分。",
            "带省略号拼接的引用不能作为可回指证据，需重新定位。",
            "类型提案来自一次探索性试跑，不是领域金标。",
        ],
    }
    out = ROOT / "reports/pilot_mapping.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "mentions": report["mentions"]["total"],
        "mentions_literal": report["mentions"]["surface_literal_in_snapshot"],
        "facts": report["facts"]["total"],
        "facts_evidence_literal": report["facts"]["evidence_literal_in_snapshot"],
        "facts_relation_spliced": report["facts"]["relation_raw_uses_dot_ellipsis"],
        "facts_requires_split": report["facts"]["requires_split"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
