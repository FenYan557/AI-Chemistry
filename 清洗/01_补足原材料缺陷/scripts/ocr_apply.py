# -*- coding: utf-8 -*-
"""把 OCR 复核结论按 **表 tid** 写回（v2）。

审查 P1-5：旧版按页写回，同页多表共用第一条记录。本版按 tid 一一对应。
审查 其他-4：缺 ocr_check.json 时以非零码退出，并写入输入 hash 供 --skip-ocr 校验。
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = pathlib.Path(__file__).resolve().parents[2]
REP = BASE / "01_补足原材料缺陷" / "out" / "repaired"
REPORT = BASE / "01_补足原材料缺陷" / "out" / "report"


def status(page_agreement: float | None) -> str:
    if page_agreement is None:
        return "unreadable"
    if page_agreement >= 0.8:
        return "confirmed"
    if page_agreement >= 0.5:
        return "partial"
    return "unreadable"


def file_hash() -> str:
    h = hashlib.sha256()
    for f in sorted(REP.glob("*.json")):
        if f.name.endswith(".fields.json"):
            continue
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def main() -> None:
    p = REPORT / "ocr_check.json"
    if not p.exists():
        print("[失败] 未找到 ocr_check.json，请先跑 ocr_tables.py（不能假装通过）")
        sys.exit(2)
    data = json.loads(p.read_text(encoding="utf-8"))
    by_doc = data.get("docs", {})

    tally = {"confirmed": 0, "partial": 0, "unreadable": 0, "no_ocr": 0}
    seen_tid = set()
    for name, entries in by_doc.items():
        f = REP / f"{name}.json"
        if not f.exists():
            continue
        by_tid = {e["tid"]: e for e in entries if e.get("tid")}
        blocks = json.loads(f.read_text(encoding="utf-8"))
        for b in blocks:
            if b.get("type") != "table":
                continue
            tid = b.get("tid")
            tr = b.setdefault("table_repair", {})
            e = by_tid.get(tid)
            if not e:
                tr.setdefault("ocr", {"status": "no_ocr"})
                tally["no_ocr"] += 1
                continue
            st = status(e.get("page_agreement"))
            # 表级确认要求：bbox 与整页一致（差距 ≤0.3），否则即使整页命中高也只到 partial
            if st == "confirmed" and e.get("bbox_content_mismatch"):
                st = "partial"
            tr["ocr"] = {"status": st,
                         "tid": tid,
                         "page_agreement": e.get("page_agreement"),
                         "bbox_agreement": e.get("bbox_agreement"),
                         "bbox_content_mismatch": e.get("bbox_content_mismatch"),
                         "coord": e.get("coord"),
                         "note": "整页命中只证明页面存在同值；confirmed 需 bbox 与整页一致"}
            seen_tid.add(tid)
            tally[st] += 1
        f.write_text(json.dumps(blocks, ensure_ascii=False), encoding="utf-8")

    all_tables = sum(1 for f in REP.glob("*.json") if not f.name.endswith(".fields.json")
                     for b in json.loads(f.read_text(encoding="utf-8")) if b.get("type") == "table")
    tally["no_ocr"] = all_tables - tally["confirmed"] - tally["partial"] - tally["unreadable"]
    tally["tables_total"] = all_tables
    tally["tids_in_check"] = len(seen_tid)
    tally["input_hash"] = file_hash()
    print("== OCR 结论写回（按 tid）==")
    for k, v in tally.items():
        print(f"  {k}: {v}")
    (REPORT / "ocr_applied.json").write_text(json.dumps(tally, ensure_ascii=False, indent=2),
                                             encoding="utf-8")


if __name__ == "__main__":
    main()
