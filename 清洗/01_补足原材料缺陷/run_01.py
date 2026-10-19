# -*- coding: utf-8 -*-
"""阶段 01 一键复跑：诊断 → 补足 → OCR 复核 → 写回 → 保留度评估。

用法：
  python run_01.py                 # 全跑（含 OCR，约 8-10 分钟）
  python run_01.py --skip-ocr      # 跳过 OCR（复用已有 ocr_check.json）
  python run_01.py --skip-audit    # 跳过缺陷诊断
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).parent
SCRIPTS = HERE / "scripts"
REPORT = HERE / "out" / "report"


def run(name: str) -> bool:
    print(f"\n===== {name} =====")
    r = subprocess.run([sys.executable, str(SCRIPTS / name)], cwd=str(HERE))
    if r.returncode != 0:
        print(f"[失败] {name} 退出码 {r.returncode}")
        return False
    return True


def check_ocr_reuse() -> None:
    """--skip-ocr 时校验输入是否变过（审查：缺 hash 校验会假装通过）。"""
    import hashlib
    rep = HERE / "out" / "repaired"
    h = hashlib.sha256()
    for f in sorted(rep.glob("*.json")):
        if f.name.endswith(".fields.json"):
            continue
        h.update(f.name.encode())
        h.update(f.read_bytes())
    cur = h.hexdigest()[:16]
    p = REPORT / "ocr_applied.json"
    if not p.exists():
        print(f"[警告] 复用的 OCR 结果不存在；本次 OCR 状态一律视为未验证（hash {cur}）")
        return
    old = json.loads(p.read_text(encoding="utf-8")).get("input_hash")
    if old and old != cur:
        print(f"[警告] repaired 已变化（{old} → {cur}）；当前 OCR 结论属过期证据，需重跑 ocr_tables.py")
    elif old == cur:
        print(f"[信息] OCR 结论与当前输入一致（hash {cur}）")


def show() -> None:
    print("\n===== 汇总 =====")
    for f, keys in (("repair_stats.json", ["summary"]),
                    ("ocr_applied.json", None),
                    ("retention.json", ["macro"])):
        p = REPORT / f
        if not p.exists():
            print(f"  {f}: 缺失")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if f == "repair_stats.json":
            print("  【阶段一补足】", json.dumps(d["summary"], ensure_ascii=False))
        elif f == "ocr_applied.json":
            print("  【OCR 写回】", json.dumps(d, ensure_ascii=False))
        else:
            print("  【信息保留度】", json.dumps(d["macro"], ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-ocr", action="store_true")
    ap.add_argument("--skip-audit", action="store_true")
    a = ap.parse_args()

    if a.skip_ocr:
        check_ocr_reuse()

    steps = []
    if not a.skip_audit:
        steps.append("audit_defects.py")
    steps.append("repair.py")
    if not a.skip_ocr:
        steps.append("ocr_tables.py")
    steps += ["ocr_apply.py", "retention.py"]

    for s in steps:
        if not run(s):
            sys.exit(1)
    show()


if __name__ == "__main__":
    main()
