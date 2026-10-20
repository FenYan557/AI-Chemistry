"""v3/v4样例迁移：保留来源与ID，补确定的关系映射和基准原文锚点。"""
import copy
import json
from pathlib import Path
from materialize import materialize

ROOT = Path(__file__).resolve().parents[1]
EFFECTS = {"f:ado:low", "f:ado:high", "h:surface_two_outcomes", "h:stone_forest", "h:purity_hedged"}
MEASUREMENTS = {"f:resistivity:reported", "f:resistivity:annealed", "h:annealed_resistivity"}


def upgrade(bundle):
    result = copy.deepcopy(bundle)
    if result["schema_version"] not in {"3.0.0-draft", "4.0.0-draft"}:
        raise ValueError("只支持显式v3/v4迁移")
    result["schema_version"] = "4.0.0-draft"
    for fact in result["facts"]:
        if fact["id"] in EFFECTS:
            fact["relation"]["candidate_relation_id"] = "r7"
        if fact["id"] in MEASUREMENTS:
            fact["relation"]["candidate_relation_id"] = "r9"
        for part in fact["participants"]:
            if fact["id"] == "h:adsorption" and part["role"] == "site":
                pass
        for q in [c["value"] for c in fact.get("conditions", [])] + [o["value"] for o in fact.get("outcomes", [])]:
            if q.get("value_kind") == "numeric" and q.get("value_raw") in {"low-concentration", "high-concentration", "acceleration", "suppression"}:
                q["value_kind"] = "qualitative"
        for outcome in fact.get("outcomes", []):
            comp = outcome.get("comparison") or {}
            raw = comp.get("baseline_raw")
            if raw and not comp.get("evidence"):
                matches = [(b, b["text"].find(raw)) for b in result["blocks"]
                           if b["document_id"] == fact["document_id"] and raw in b["text"]]
                if len(matches) != 1:
                    raise ValueError("基准无法唯一定位，需人工核对: " + fact["id"])
                block, start = matches[0]
                comp["evidence"] = [{"kind": "block", "block_id": block["id"],
                                     "start": start, "end": start + len(raw), "quote": raw}]
    return materialize(result)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    data = json.loads(args.source.read_text(encoding="utf-8"))
    args.destination.write_text(json.dumps(upgrade(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
