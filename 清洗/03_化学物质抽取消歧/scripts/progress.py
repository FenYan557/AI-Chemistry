# -*- coding: utf-8 -*-
"""阶段03 辅助：汇总 48 篇文献的处理进度，供新对话快速接手。

用法（仓库根目录）：
    python -X utf8 清洗/03_化学物质抽取消歧/scripts/progress.py

输出每篇：字符量、抽取/消歧/合并文件是否存在、记录数、pending 数、
各 link_status 计数；按 chars 从小到大排序（即建议推进顺序）。
"""
import json
import sys
from pathlib import Path

STAGE = Path(__file__).resolve().parents[1]
INPUT_DIR = STAGE / "out" / "extraction_input"
EXTRACT_DIR = STAGE / "out" / "extraction"
DISAM_DIR = STAGE / "out" / "disambiguation"
FINAL_DIR = STAGE / "out" / "final"


def main():
    summary = json.loads(
        (INPUT_DIR / "_summary.json").read_text(encoding="utf-8")
    )["per_doc"]
    rows = []
    for doc_id in sorted(INPUT_DIR.glob("*.jsonl"), key=lambda p: p.stem):
        d = doc_id.stem
        chars = summary.get(d, {}).get("chars", 0)
        ext = EXTRACT_DIR / f"{d}.json"
        dis = DISAM_DIR / f"{d}.json"
        fin = FINAL_DIR / f"{d}.json"
        n_rec = n_status = n_pending = 0
        stat = {}
        if ext.is_file():
            recs = json.loads(ext.read_text(encoding="utf-8"))
            n_rec = len(recs)
            n_status = len({(r.get("span") or "").strip() for r in recs})
        if fin.is_file():
            chems = json.loads(fin.read_text(encoding="utf-8"))["chemicals"]
            for c in chems:
                stat[c["link_status"]] = stat.get(c["link_status"], 0) + 1
            n_pending = stat.get("pending", 0)
        state = "DONE" if (ext.is_file() and dis.is_file() and fin.is_file()
                           and n_pending == 0) else (
            "PART" if ext.is_file() else "TODO")
        rows.append((chars, d, state, n_rec, n_status,
                     f"m{stat.get('matched', 0)}/a{stat.get('ambiguous', 0)}"
                     f"/u{stat.get('unmatched_new', 0)}"
                     f"/s{stat.get('spec_of_general', 0)}"
                     f"/x{stat.get('not_chemical', 0)}",
                     n_pending))
    rows.sort()
    done = sum(1 for r in rows if r[2] == "DONE")
    part = sum(1 for r in rows if r[2] == "PART")
    todo = len(rows) - done - part
    print(f"{'状态':<6}{'chars':>8} {'span':>5} {'rec':>4}  "
          f"{'m/a/u/s/x':<14} doc_id")
    for chars, d, state, n_rec, n_status, stat, n_pending in rows:
        flag = "!" if n_pending else ""
        print(f"{state + flag:<6}{chars:>8} {n_status:>5} {n_rec:>4}  "
              f"{stat:<14} {d}")
    print(f"合计: DONE={done} PART={part} TODO={todo} 共{len(rows)}篇")
    return 0


if __name__ == "__main__":
    sys.exit(main())
