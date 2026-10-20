"""复杂度预算检查：类型/关系/记录/字段/错误码/登记表/文档节数超过上限即失败。

预算写在 schema/constraints.json 的 budget 里。超了先删或合并，再增加。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def actual_counts():
    schema = load(ROOT / "schema/records.schema.json")
    constraints = load(ROOT / "schema/constraints.json")
    types = load(ROOT / "registry/entity_types.json")["types"]
    relations = load(ROOT / "registry/relations.json")["relations"]
    codes = {c for item in constraints["constraints"] for c in item["codes"]}
    props = {k: v for k, v in schema["properties"].items() if k != "schema_version"}
    defs = schema["$defs"]
    fields = [len(d["properties"]) for d in defs.values() if "properties" in d]
    doc = ROOT / "schema/schema.md"
    sections = len(re.findall(r"(?m)^## ", doc.read_text(encoding="utf-8"))) if doc.exists() else 0
    return {
        "entity_types": len(types),
        "core_entity_types": sum(1 for t in types if t["status"] == "core"),
        "relations": len(relations),
        "record_types": len(props),
        "top_level_fields": len(schema["properties"]),
        "fields_per_record": max(fields) if fields else 0,
        "defs": len(defs),
        "error_codes": len(codes),
        "registry_files": len(list((ROOT / "registry").glob("*.json"))),
        "doc_sections": sections,
    }


def check():
    budget = load(ROOT / "schema/constraints.json")["budget"]
    actual = actual_counts()
    exceeded = []
    for key, cap in budget.items():
        if key == "rule":
            continue
        metric = key[4:] if key.startswith("max_") else key
        if metric not in actual:
            continue
        if actual[metric] > cap:
            exceeded.append({"metric": metric, "actual": actual[metric], "budget": cap})
    return {"ok": not exceeded, "exceeded": exceeded, "budget": {k: v for k, v in budget.items() if k != "rule"},
            "actual": actual}


if __name__ == "__main__":
    result = check()
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)
