# -*- coding: utf-8 -*-
"""阶段03 辅助：校验抽取结果里的 span 是否为对应单元文本的逐字子串。

用法（仓库根目录）：
    python -X utf8 清洗/03_化学物质抽取消歧/scripts/verify_spans.py <doc_id>

检查项：unit_id 是否存在、span 是否逐字出现在该单元 text 中、
source_type 是否与单元一致。有不符则退出码 1 并列出问题。
"""
import json
import sys
from pathlib import Path

STAGE = Path(__file__).resolve().parents[1]
INPUT_DIR = STAGE / "out" / "extraction_input"
EXTRACT_DIR = STAGE / "out" / "extraction"


def load_units(doc_id):
    units = {}
    with (INPUT_DIR / f"{doc_id}.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                u = json.loads(line)
                units[u["unit_id"]] = u
    return units


def main():
    if len(sys.argv) < 2:
        print("用法: verify_spans.py <doc_id>", file=sys.stderr)
        return 1
    doc_id = sys.argv[1]
    ep = EXTRACT_DIR / f"{doc_id}.json"
    if not ep.is_file():
        print(f"未找到 {ep}", file=sys.stderr)
        return 1
    units = load_units(doc_id)
    records = json.loads(ep.read_text(encoding="utf-8"))
    bad_unit = bad_span = bad_src = 0
    for i, r in enumerate(records):
        uid = r.get("unit_id", "")
        span = r.get("span", "")
        u = units.get(uid)
        if u is None:
            print(f"[unit不存在] #{i} {uid} :: {span}")
            bad_unit += 1
            continue
        if span not in u.get("text", ""):
            print(f"[非逐字] #{i} {uid} :: {span!r}")
            bad_span += 1
        if r.get("source_type") != u.get("source_type"):
            print(f"[source_type不符] #{i} {uid} "
                  f"{r.get('source_type')} != {u.get('source_type')}")
            bad_src += 1
    print(f"records={len(records)} 非逐字={bad_span} "
          f"unit不存在={bad_unit} source_type不符={bad_src}")
    return 1 if (bad_span or bad_unit or bad_src) else 0


if __name__ == "__main__":
    sys.exit(main())
