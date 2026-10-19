# -*- coding: utf-8 -*-
"""阶段二开工前的数据分析：只读阶段一产物，回答"要清什么、怎么切、切完多少块"。"""
from __future__ import annotations

import json
import pathlib
import re
import statistics
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BASE = pathlib.Path(__file__).resolve().parents[2]
REP = BASE / "01_补足原材料缺陷" / "out" / "repaired"
OUT = BASE / "02_清洗" / "out" / "report"

NOISE = {"header", "footer", "page_number", "ref_text", "page_footnote", "aside_text"}
NONBODY = re.compile(r"(\S+@\S+\.\w+|CRediT|Author Contributions|Declaration of Competing|"
                     r"Acknowledg(e)?ment|致\s*谢|作者简介|基金项目)", re.I)
UNIT = re.compile(r"(mg/L|g/L|mol/L|mmol/L|ppm|mA/cm2|A/dm2|mV|mJ/m2|μm|°C|mM|%)")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    types = Counter()
    lens_text, lens_all = [], []
    sec_ok = sec_missing = 0
    refs = figs = figs_cap = figs_paired = 0
    tabs = tabs_cap = tabs_raster = tabs_ocr_conf = 0
    eqs = 0
    nonbody = 0
    zh_docs = 0
    dup = 0
    docs = 0
    cls = Counter()
    est_chunks = 0

    for f in sorted(REP.glob("*.json")):
        if f.name.endswith(".fields.json"):
            continue
        docs += 1
        blocks = json.loads(f.read_text(encoding="utf-8"))
        seen = set()
        zh = 0
        for b in blocks:
            t = b.get("type")
            types[t] += 1
            txt = b.get("text") or ""
            if len(txt) > 20:
                if txt in seen:
                    dup += 1
                seen.add(txt)
            if re.search(r"[\u4e00-\u9fff]", txt):
                zh += 1
            if t in NOISE:
                continue
            if t == "text":
                lens_text.append(len(txt))
                lens_all.append(len(txt))
                if b.get("text_level") in (1, 2, 3):
                    sec_ok += 1
                if NONBODY.search(txt):
                    nonbody += 1
            elif t == "table":
                tabs += 1
                if b.get("table_caption"):
                    tabs_cap += 1
                tr = b.get("table_repair") or {}
                if tr.get("evidence") == "raster_or_image":
                    tabs_raster += 1
                if (tr.get("ocr") or {}).get("status") == "confirmed":
                    tabs_ocr_conf += 1
                cls[tr.get("evidence", "?")] += 1
            elif t in ("image", "chart"):
                figs += 1
                if b.get("image_caption") or b.get("chart_caption"):
                    figs_cap += 1
                if b.get("caption_paired"):
                    figs_paired += 1
            elif t == "equation":
                eqs += 1
            elif t == "ref_text":
                refs += 1
        if zh > len(blocks) * 0.3:
            zh_docs += 1

    def q(v, p):
        v = sorted(v)
        return v[int(round((len(v) - 1) * p))] if v else 0

    print(f"篇数 {docs}")
    print("\n=== 块类型 ===")
    for k, v in types.most_common():
        print(f"  {k:14s} {v:6d}")
    noise_total = sum(v for k, v in types.items() if k in NOISE)
    print(f"  其中噪音类合计 {noise_total} ({noise_total/sum(types.values())*100:.1f}%)")

    print("\n=== 正文段长度（字符） ===")
    print(f"  段数 {len(lens_text)}  p10={q(lens_text,0.1)} 中位={int(statistics.median(lens_text))} "
          f"p90={q(lens_text,0.9)} p99={q(lens_text,0.99)} max={max(lens_text) if lens_text else 0}")
    print(f"  >2000 字符的段 {sum(1 for x in lens_text if x > 2000)}；<80 字符的段 {sum(1 for x in lens_text if x < 80)}")

    print("\n=== 结构件 ===")
    print(f"  heading 块 {sec_ok}；参考文献块 {refs}；公式 {eqs}")
    print(f"  图 {figs}（有 caption {figs_cap}，题注配对 {figs_paired}）")
    print(f"  表 {tabs}（有 caption {tabs_cap}，位图表 {tabs_raster}，OCR 已确认 {tabs_ocr_conf}）")
    print(f"  非正文样段（邮箱/CRediT/致谢等）{nonbody}")
    print(f"  重复正文块 {dup}")
    print(f"  中文为主的文章 {zh_docs}")

    print("\n=== 表格证据状态 ===")
    for k, v in cls.most_common():
        print(f"  {k}: {v}")

    # 600 字符 / 80 重叠 估算
    total_chars = sum(lens_text)
    est = sum(max(1, int((x - 80) / (600 - 80)) + 1) if x > 600 else 1 for x in lens_text)
    print("\n=== 若按 600 字符 / 80 重叠切块 ===")
    print(f"  正文字符 {total_chars}；预计块数 ≈ {est}")
    (OUT / "stage2_preanalysis.json").write_text(json.dumps({
        "docs": docs, "types": dict(types), "noise_total": noise_total,
        "text_len": {"count": len(lens_text), "p50": int(statistics.median(lens_text)) if lens_text else 0,
                     "p90": q(lens_text, 0.9), "p99": q(lens_text, 0.99),
                     "gt2000": sum(1 for x in lens_text if x > 2000),
                     "lt80": sum(1 for x in lens_text if x < 80)},
        "headings": sec_ok, "refs": refs, "equations": eqs,
        "figs": figs, "figs_cap": figs_cap, "figs_paired": figs_paired,
        "tables": tabs, "tabs_cap": tabs_cap, "tabs_raster": tabs_raster,
        "tabs_ocr_confirmed": tabs_ocr_conf, "nonbody": nonbody, "dup": dup,
        "zh_docs": zh_docs, "est_chunks_600_80": est, "total_chars": total_chars,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n已写", OUT / "stage2_preanalysis.json")


if __name__ == "__main__":
    main()
