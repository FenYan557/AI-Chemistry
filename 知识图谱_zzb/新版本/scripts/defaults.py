"""代码补齐内部可选字段；省略字段不代表已核查文献未报告。"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalize(bundle):
    schema = json.loads((ROOT / "schema/records.schema.json").read_text(encoding="utf-8"))
    data = copy.deepcopy(bundle)

    def visit(value, definition):
        if "$ref" in definition:
            definition = schema["$defs"][definition["$ref"].split("/")[-1]]
        if isinstance(value, dict):
            for key, prop in definition.get("properties", {}).items():
                if key not in value and "default" in prop:
                    value[key] = copy.deepcopy(prop["default"])
                if key in value:
                    visit(value[key], prop)
        elif isinstance(value, list):
            for item in value:
                visit(item, definition.get("items", {}))

    visit(data, schema)
    return data
