# -*- coding: utf-8 -*-
"""阶段 01：补足原材料缺陷（v3，按审查意见修正）

修正清单（对应 _work/review01_审查意见.md）：
  P1-2 归一化：改用共享库 lib/textnorm（不删未知命令、上下标不拼数字、指数保留 ^）
  P1-3 表格：保留原始 table_footnote / table_body / 题注原文（raw 字段），不再只留改造版
  P1-4 单位：取消"按位置把题注括号塞给列名"，改为只认单位行，其余输出 unit_candidates 待确认
  P1-5 表格加稳定 tid（doc:page:k），供 OCR 与回写一一对应
  其他 配对后重算 caption_pseudo / no_number；fields 带页码与证据片段

仍然「只修不删」，且每条修复都给标记。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BASE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "lib"))
sys.path.insert(0, str(BASE / "02_清洗" / "scripts"))
import textnorm  # noqa: E402  共享归一
import clean  # noqa: E402  仅用：SRC/doc_title/manifest/parse_table/merge_header/classify/clean_caption

SRC = clean.SRC
OUT = BASE / "01_补足原材料缺陷" / "out"
REP = OUT / "repaired"
REPORT = OUT / "report"

HTML_TAG = re.compile(r"</?(sup|sub|i|b|em|strong|br|span)[^>]{0,30}>", re.I)
THOUSAND = re.compile(r"(?<![\[\d,])(\d{1,3}),(\d{3})(?![\d\]])")
DEC_SPACE = re.compile(r"(\d)\.\s+(\d)")
MATH_CTX = re.compile(r"\\[a-zA-Z]+")
SUP10 = re.compile(r"[×x]\s*10\s*\^?\s*(-?\d)")
SUPPOW = re.compile(r"(?<![A-Za-z])(cm|mm|nm|dm|m|s|g|L|mol)\s*[-–]?\s*[23](?![A-Za-z0-9])")
SUPR2 = re.compile(r"\bR\s*(?:\^?\s*2|²)\s*[=＝]")
FIGCAP = re.compile(r"^\s*(Fig(?:ure)?s?\.?\s*\d+[a-z]?|图\s*\d+[\-–]?\d*)", re.I)
TABCAP = re.compile(r"^\s*(Table\s*\d+|表\s*\d+)", re.I)
UNIT_CELL = re.compile(
    r"^(?:mg/?[lL]|g/?[lL]|mol/?[lL]|mmol/?[lL]|ppm|mA\s*/?\s*cm\s*-?\s*2|A\s*/?\s*dm\s*-?\s*2|"
    r"mV|mJ\s*/?\s*m\s*-?\s*2|μm|nm|mm|°C|℃|mM|wt%|%|HV|GU|a\.u\.|r/min|rpm)$", re.I)
UNIT_PAREN = re.compile(
    r"\(\s*([^()]{0,20}?(?:mg/L|g/L|mol/L|mmol/L|ppm|mV|V|%|μm|°C|mM|A/dm2|mA/cm2|mJ/m2|HV|GU|a\.u\.)[^()]{0,10})\s*\)")
NUMCELL = re.compile(r"[-−–]?\d+(\.\d+)?")


def join_spaced_chars(s: str) -> tuple[str, int]:
    tokens, out, i, fixed = s.split(" "), [], 0, 0
    while i < len(tokens):
        j = i
        while j < len(tokens) and 0 < len(tokens[j]) <= 1:
            j += 1
        run = tokens[i:j]
        if len(run) >= 3:
            joined = "".join(run)
            if any(c.isalpha() for c in joined) and any(c.isdigit() or c == "/" for c in joined):
                out.append(joined)
                fixed += 1
                i = j
                continue
        out.append(tokens[i])
        i += 1
    return " ".join(out), fixed


def repair_text(s: str) -> tuple[str, str, str, dict]:
    """返回 (display, index, raw, flags)。数学式整体保留 LaTeX；其余走共享归一。"""
    raw = s
    flags: dict = {}
    t = HTML_TAG.sub(" ", s)
    t = clean.clean_text_noise(t)

    # 含分式/矩阵等结构性数学：整块保留 LaTeX（不尝试线性化）
    if ("$" in t or "\\" in t) and re.search(r"\\(frac|dfrac|tfrac|sqrt|begin|end|left|right|overline|sum|int|prod)\b", t):
        disp = re.sub(r"^\s*\$\$?\s*", "", t)
        disp = re.sub(r"\s*\$\$?\s*$", "", disp).strip()
        flags["math_kept_as_latex"] = True
        return disp, textnorm.to_index(disp), raw, flags

    t, tflags = textnorm.latex_to_display(t)
    flags.update(tflags)
    t, n_join = join_spaced_chars(t)
    if n_join:
        flags["char_spacing_joined"] = n_join
    t = THOUSAND.sub(r"\1\2", t)
    t = DEC_SPACE.sub(r"\1.\2", t)
    t = textnorm.norm_units(t)
    t = re.sub(r"\s{2,}", " ", t).strip()

    if SUP10.search(t) or SUPPOW.search(t) or SUPR2.search(t):
        m = SUP10.search(t) or SUPPOW.search(t) or SUPR2.search(t)
        flags["sup_uncertain"] = True
        flags["sup_raw"] = t[max(0, m.start() - 20): m.start() + 25]
    if t != raw.strip():
        flags["repaired"] = True
    return t, textnorm.to_index(t), raw, flags


def repair_table(body: str, caption: str, page_text: str = "") -> tuple[str, dict]:
    rows = clean.parse_table(body)              # 内部已走 textnorm，指数不再变 102
    header, data, levels = clean.merge_header(rows)
    width = max([len(header)] + [len(r) for r in data]) if (header or data) else 0
    header = list(header) + [""] * (width - len(header))
    data = [list(r) + [""] * (width - len(r)) for r in data]

    flags = {"header_levels": levels, "rows": len(data), "cols": width}
    raw_widths = {len(re.findall(r"<td", tr))
                  for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body or "", re.S)}
    if len(raw_widths) > 1 and not re.search(r"rowspan|colspan", body or ""):
        flags["header_flattened"] = True

    # 单位：只认"单位行"（整行是单位、无数值）→ 绑定到列名；其余只记候选（审查 P1-4）
    unit_row_filled = 0
    for r in data:
        units = [c for c in r if UNIT_CELL.match(c.strip())]
        nums = [c for c in r if NUMCELL.fullmatch(c.strip())]
        if len(units) >= 2 and not nums:
            for j, c in enumerate(r):
                if j < width and UNIT_CELL.match(c.strip()) and not clean.UNIT_PAT.search(header[j]):
                    header[j] = f"{header[j]} ({c.strip()})".strip()
                    unit_row_filled += 1
            flags["unit_from"] = "unit_row"
            break

    # 题注里的单位只作为"候选"，不自动写进列名
    cand = UNIT_PAREN.findall(caption or "")
    if cand:
        flags["unit_candidates"] = {"source": "caption", "values": cand[:6]}
    flags["unit_filled"] = unit_row_filled

    nums = [c.strip() for r in data for c in r if NUMCELL.fullmatch(c.strip())]
    if nums and page_text:
        flat = re.sub(r"\s+", "", page_text)
        hit = sum(1 for v in nums if v.lstrip("−-") in flat)
        flags["text_layer_verify"] = round(hit / len(nums), 2)
        flags["evidence"] = "text_layer" if hit / len(nums) >= 0.8 else "raster_or_image"
    elif nums:
        flags["evidence"] = "unknown"
    flags["numeric_cells"] = len(nums)

    html = "<table>" + "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in [header] + data
    ) + "</table>"
    return html, flags


def bbox_gap(a, b) -> float:
    if not a or not b:
        return 1e9
    return abs(a[1] - b[3]) if a[1] > b[3] else abs(b[1] - a[3])


def pair_captions(blocks: list[dict]) -> Counter:
    stats = Counter()
    figs = [b for b in blocks if b.get("type") in ("image", "chart")]
    tabs = [b for b in blocks if b.get("type") == "table"]
    texts = [b for b in blocks if b.get("type") == "text"]
    used = set()

    def attach(pool, kind):
        for t in texts:
            if id(t) in used:
                continue
            txt = (t.get("text") or "").strip()
            if not txt or len(txt) > 200:
                continue
            is_fig, is_tab = bool(FIGCAP.match(txt)), bool(TABCAP.match(txt))
            if (kind == "fig" and not is_fig) or (kind == "tab" and not is_tab):
                continue
            cands = [b for b in pool
                     if b.get("page_idx") == t.get("page_idx") and id(b) not in used
                     and not (b.get("image_caption") or b.get("chart_caption") or b.get("table_caption"))]
            if not cands:
                continue
            best = min(cands, key=lambda b: bbox_gap(t.get("bbox"), b.get("bbox")))
            if bbox_gap(t.get("bbox"), best.get("bbox")) > 400:
                continue
            cap = re.sub(r"\s+", " ", txt)[:300]
            if kind == "fig":
                best["image_caption" if best["type"] == "image" else "chart_caption"] = [cap]
            else:
                best["table_caption"] = [cap]
            best["caption_paired"] = {"from": "text_block", "page": (t.get("page_idx") or 0) + 1}
            used.add(id(best))
            used.add(id(t))
            stats[f"{kind}_paired"] += 1

    attach(figs, "fig")
    attach(tabs, "tab")
    return stats


def mark_cross_page_tables(blocks: list[dict]) -> int:
    tabs = [b for b in blocks if b.get("type") == "table"]
    merged = 0
    for b, n in zip(tabs, tabs[1:]):
        if (b.get("page_idx") or 0) + 1 != (n.get("page_idx") or 0):
            continue
        hb = re.findall(r"<td>(.*?)</td>", b.get("table_body") or "")[:6]
        hn = re.findall(r"<td>(.*?)</td>", n.get("table_body") or "")[:6]
        if not hb or len(hb) != len(hn):
            continue
        cap_b = (b.get("table_caption") or [""])[0]
        cap_n = (n.get("table_caption") or [""])[0]
        if (hb == hn) or (cap_b and cap_b == cap_n) or re.search(r"continu", cap_n, re.I):
            b["cross_page_suspect"] = {"next_page": (n.get("page_idx") or 0) + 1}
            merged += 1
    return merged


def refresh_caption_flags(blocks: list[dict]) -> None:
    """配对/清洗后重算 caption 相关标记（审查：配对后仍带旧标记）。"""
    for b in blocks:
        b.pop("no_number", None)
        b.pop("caption_pseudo", None)
        t = b.get("type")
        if t == "table":
            cap = (b.get("table_caption") or [""])[0]
        elif t in ("image", "chart"):
            cap = (b.get("image_caption") or b.get("chart_caption") or [""])[0]
        else:
            continue
        if not cap:
            b["no_caption"] = True
            continue
        if not (FIGCAP.match(cap) or TABCAP.match(cap)):
            b["no_number"] = True
        if clean.PSEUDO_CAP.match(cap) or len(cap) <= 8:
            b["caption_pseudo"] = True


def pdf_pages(path: pathlib.Path) -> list[str]:
    try:
        import fitz
        doc = fitz.open(path)
        pages = [p.get_text() for p in doc]
        doc.close()
        return pages
    except Exception:
        return []


def main() -> None:
    for p in (REP, REPORT):
        p.mkdir(parents=True, exist_ok=True)
    stats = Counter()
    docs = []
    for d in sorted(x for x in SRC.iterdir() if x.is_dir()):
        cl = list(d.glob("*_content_list.json"))
        if not cl:
            continue
        raw = json.loads(cl[0].read_text(encoding="utf-8"))
        pdfs = list(d.glob("*.pdf"))
        pages = pdf_pages(pdfs[0]) if pdfs else []

        blocks, fields_text = [], []
        counter = Counter()
        for e in raw:
            t = e.get("type")
            new = {k: e.get(k) for k in ("page_idx", "bbox", "text_level", "img_path") if k in e}
            new["type"] = t
            page = e.get("page_idx") or 0

            if t in ("text", "header", "footer", "page_footnote", "ref_text",
                     "page_number", "aside_text"):
                disp, idx, rw, flags = repair_text(e.get("text") or "")
                new.update({"text": disp, "text_index": idx, "raw": rw})
                if flags:
                    new["repair"] = flags
                    counter["sup_uncertain"] += 1 if flags.get("sup_uncertain") else 0
                    counter["math_kept"] += 1 if flags.get("math_kept_as_latex") else 0
                    counter["unmapped"] += 1 if flags.get("unmapped") else 0
                    counter["text_repaired"] += 1 if flags.get("repaired") else 0
                if t in ("text", "page_footnote", "ref_text"):
                    fields_text.append(disp)

            elif t == "equation":
                src = e.get("text") or e.get("latex") or ""
                disp, idx, rw, flags = repair_text(src)
                new.update({"text": disp, "text_index": idx, "raw": rw, "raw_latex": src})
                if flags:
                    new["repair"] = flags
                counter["unmapped"] += 1 if flags.get("unmapped") else 0

            elif t == "table":
                counter["table"] += 1
                tid = f"{d.name[:24]}:{page}:{counter['table']}"
                new["tid"] = tid
                cap, tail = clean.clean_caption(e.get("table_caption"))
                body, info = repair_table(e.get("table_body") or "", cap,
                                          pages[page] if page < len(pages) else "")
                new["table_body"] = body
                new["table_caption"] = [cap] if cap else []
                new["raw_table_body"] = e.get("table_body") or ""      # 审查 P1-3：保留原文
                new["raw_table_caption"] = e.get("table_caption") or []
                new["raw_table_footnote"] = e.get("table_footnote") or []
                if e.get("table_footnote"):
                    new["table_footnote"] = e.get("table_footnote")
                    counter["footnote_kept"] += 1
                if tail:
                    new["caption_tail"] = tail
                new["table_repair"] = info
                fields_text.append(textnorm.latex_to_display(e.get("table_body") or "")[0])

            elif t in ("image", "chart"):
                counter["fig"] += 1
                cap, tail = clean.clean_caption(e.get("image_caption") or e.get("chart_caption"))
                new["image_caption" if t == "image" else "chart_caption"] = [cap] if cap else []
                new["raw_caption"] = e.get("image_caption") or e.get("chart_caption") or []
                if tail:
                    new["caption_extra"] = tail
            else:
                continue
            blocks.append(new)

        paired = pair_captions(blocks)
        cross = mark_cross_page_tables(blocks)
        refresh_caption_flags(blocks)

        (REP / f"{d.name}.json").write_text(json.dumps(blocks, ensure_ascii=False), encoding="utf-8")

        blob = "\n".join(fields_text)
        cand = {}
        for name, pat in {
            "参比电极": re.compile(r"(SSE|SCE|Ag/AgCl|Ag-AgCl|SMSE|Hg/Hg2SO4|saturated calomel)", re.I),
            "电流密度": re.compile(r"(\d+(?:\.\d+)?)\s*(mA/cm2|mA\s*cm-2|A/dm2|A\s*dm-2|ASD)", re.I),
            "温度": re.compile(r"(\d{2,3})\s*(°C|℃)|(29[0-9]|30[0-9])\s*K\b|room temperature", re.I),
            "金属": re.compile(r"\b(Cu|Co|Ni|SnAg|Sn-Ag)\b"),
        }.items():
            hits = []
            for m in pat.finditer(blob):
                hits.append({"value": m.group(0)[:40], "context": blob[max(0, m.start() - 50):m.end() + 30]})
                if len(hits) >= 6:
                    break
            if hits:
                cand[name] = hits
        (REP / f"{d.name}.fields.json").write_text(
            json.dumps({"note": "正则候选，需人工/抽取层确认", "fields": cand},
                       ensure_ascii=False, indent=2), encoding="utf-8")

        rec = {"doc": clean.doc_title(d)[:48], "blocks": len(blocks),
               "tables": counter["table"], "figs": counter["fig"],
               "footnote_kept": counter["footnote_kept"],
               "fig_paired": paired["fig_paired"], "tab_paired": paired["tab_paired"],
               "cross_page_suspect": cross,
               "sup_uncertain": counter["sup_uncertain"], "math_kept": counter["math_kept"],
               "unmapped": counter["unmapped"], "text_repaired": counter["text_repaired"]}
        rec["tables_raster"] = sum(1 for b in blocks if b.get("type") == "table"
                                   and (b.get("table_repair") or {}).get("evidence") == "raster_or_image")
        rec["no_number"] = sum(1 for b in blocks if b.get("no_number"))
        rec["no_caption"] = sum(1 for b in blocks if b.get("no_caption"))
        docs.append(rec)
        for k in ("blocks", "tables", "figs", "footnote_kept", "fig_paired", "tab_paired",
                  "cross_page_suspect", "sup_uncertain", "math_kept", "unmapped",
                  "text_repaired", "tables_raster", "no_number", "no_caption"):
            stats[k] += rec[k]

    (REPORT / "repair_stats.json").write_text(
        json.dumps({"summary": dict(stats), "docs": docs}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("== 阶段 01 补足 v3 ==")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
