"""把记录层物化为图视图（实体 + 边），物化规则显式、确定、可逆。

规则：
1. 每个提及物化为一个实体，保留已有ID；新提及默认ent:<mention_id>。
2. 只有 identity_links.review=reviewed 且身份非 unresolved 时，实体才指向 identity_id；
   pending 合并不改变实体指向，所以同一实体在复核前后 id 不变、身份指针可变。
3. 只有启用关系按登记的参与者角色投影成边；开放事实不强行展开，
   陈述性质/来源范围/极性/模态/条件/证据/复核状态全部复制自事实。
4. 边与实体可由事实层完全重建：先清空再生成，同输入两次结果一致。
5. retrieval_keys() 按 registry/consumer_contract.json 的键生成检索视图，并保留没有图边的事实。
"""
import copy
from defaults import normalize
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _identity_pointer(bundle):
    identities = {i["id"]: i for i in bundle.get("identities", [])}
    pointer = {}
    for link in bundle.get("identity_links", []):
        ident = identities.get(link.get("identity_id"))
        if not ident:
            continue
        if link.get("review") != "reviewed" or ident.get("status") == "unresolved":
            continue
        pointer.setdefault(link["mention_id"], link["identity_id"])
    return pointer


def materialize(bundle):
    normalized = normalize(bundle)
    bundle.clear()
    bundle.update(normalized)
    existing_ids = {}
    owners = {}
    for entity in bundle.get("entities", []):
        mid, eid = entity.get("from_mention_id"), entity.get("id")
        if not mid or not eid:
            continue
        if mid in existing_ids and existing_ids[mid] != eid:
            raise ValueError("同一提及存在多个实体ID: " + mid)
        if eid in owners and owners[eid] != mid:
            raise ValueError("实体ID被多个提及占用: " + eid)
        existing_ids[mid], owners[eid] = eid, mid
    relations = {r["relation_id"]: r for r in json.loads((ROOT / "registry/relations.json").read_text(encoding="utf-8"))["relations"]}
    types = {t["type_id"]: t for t in json.loads((ROOT / "registry/entity_types.json").read_text(encoding="utf-8"))["types"]}
    pointer = _identity_pointer(bundle)
    entities, edges = {}, []
    for mention in bundle["mentions"]:
        type_ids = mention.get("candidate_type_ids") or []
        entities[mention["id"]] = {
            "id": existing_ids.get(mention["id"], "ent:" + mention["id"]),
            "document_id": mention["document_id"],
            "label": mention["surface"],
            "type_id": type_ids[0] if len(type_ids) == 1 and types.get(type_ids[0], {}).get("status") == "core" else None,
            "identity_id": pointer.get(mention["id"]),
            "from_mention_id": mention["id"],
            "evidence": [copy.deepcopy(mention["evidence"])],
        }

    if len({e["id"] for e in entities.values()}) != len(entities):
        raise ValueError("新增实体ID与已有实体冲突")
    for fact in bundle["facts"]:
        relation = relations.get(fact["relation"]["candidate_relation_id"])
        if not relation or relation["status"] != "core" or not relation.get("projection"):
            continue
        projection = relation["projection"]
        heads = {p["mention_id"] for p in fact["participants"] if p["role"] in projection["from_roles"] and p["mention_id"] in entities}
        tails = {p["mention_id"] for p in fact["participants"] if p["role"] in projection["to_roles"] and p["mention_id"] in entities}
        for index, (head, target) in enumerate(sorted((a, b) for a in heads for b in tails if a != b)):
            edges.append({
                "id": "edge:%s:%d" % (fact["id"], index + 1),
                "fact_id": fact["id"],
                "from_entity_id": entities[head]["id"],
                "to_entity_id": entities[target]["id"],
                "relation": copy.deepcopy(fact["relation"]),
                "qualifiers": {
                    "statement_type": fact["statement_type"],
                    "source_scope": fact["source_scope"],
                    "polarity": fact["polarity"],
                    "modality": fact["modality"],
                    "conditions": copy.deepcopy(fact["conditions"]),
                },
                "evidence": copy.deepcopy(fact["evidence"]),
                "review": fact["review"],
            })

    bundle["entities"] = list(entities.values())
    bundle["edges"] = edges
    return bundle


def retrieval_keys(bundle):
    """按消费端契约生成检索视图；键名与 registry/consumer_contract.json 一致。"""
    entities = {e["id"]: e for e in bundle.get("entities", [])}
    facts = {f["id"]: f for f in bundle["facts"]}
    rows, unkeyed = [], []
    for edge in bundle.get("edges", []):
        fact = facts.get(edge["fact_id"])
        if not fact:
            unkeyed.append(edge["id"])
            continue
        head = entities.get(edge["from_entity_id"], {})
        rows.append({
            "edge_id": edge["id"],
            "keys": {
                "entity": edge["from_entity_id"],
                "entity_type": head.get("type_id"),
                "identity": head.get("identity_id"),
                "relation": edge["relation"]["candidate_relation_id"],
                "indicator": [o["indicator_raw"] for o in fact["outcomes"]],
                "parameter": [c["parameter_raw"] for c in fact["conditions"]],
                "sample": [o["sample_id"] for o in fact["outcomes"] if o.get("sample_id")],
                "document": fact["document_id"],
                "statement": "%s/%s" % (fact["statement_type"], fact["source_scope"]),
                "review": fact["review"],
            },
        })
    fact_keys = [{"fact_id": f["id"], "document": f["document_id"], "relation": f["relation"]["candidate_relation_id"], "participants": [p["mention_id"] for p in f["participants"]]} for f in bundle["facts"]]
    return {"edge_keys": rows, "fact_keys": fact_keys, "edges_without_fact": unkeyed,
            "note": "检索键由记录层派生；键值不构成断言，开放事实仍可检索引用，用途分别判断。"}


if __name__ == "__main__":
    import sys
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "knowledge_graph.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    materialize(data)
    keys = retrieval_keys(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"entities": len(data["entities"]), "edges": len(data["edges"]),
                      "edge_keys": len(keys["edge_keys"])}, ensure_ascii=False))
