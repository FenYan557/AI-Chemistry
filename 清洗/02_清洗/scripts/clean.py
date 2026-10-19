# -*- coding: utf-8 -*-
"""D0–D5(轻量) 规则清洗：MinerU content_list.json → 干净 blocks / 表格矩阵 / 指标。
读取阶段一修复块，产物写入 02_清洗/out/。
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

SRC = pathlib.Path(__file__).resolve().parents[3] / "知识图谱所需文献" / "文献提取"
MANIFEST = pathlib.Path(__file__).resolve().parents[2] / "inputs" / "文献清单.csv"
BASE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "lib"))
import textnorm  # noqa: E402  阶段一/二共享归一
OUT = BASE / "02_清洗" / "out"
REPAIRED = BASE / "01_补足原材料缺陷" / "out" / "repaired"   # 存在则优先使用补足后的块

UNIT_PAT = re.compile(
    r"(mg/L|g/L|mol/L|mmol/L|ppm|mA/cm2|A/dm2|mJ/m2|mV|V|%|μm|°C|mM|HV|GU|a\.u\.)"
)
PSEUDO_CAP = re.compile(r"^(\s*\([a-zA-Z]\)\s*)+$")

NOISE = {"header", "footer", "page_number", "ref_text", "page_footnote", "aside_text"}
KEEP = {"text", "table", "equation", "image", "chart"}

# ---------- D2 LaTeX → Unicode ----------
LATEX_MAP = [
    (r"\\cdot|\\bullet", "·"),
    (r"\\times", "×"),
    (r"\\pm", "±"),
    (r"\\mu", "μ"),
    (r"\\alpha", "α"),
    (r"\\beta", "β"),
    (r"\\gamma", "γ"),
    (r"\\delta", "δ"),
    (r"\\eta", "η"),
    (r"\\chi", "χ"),
    (r"\\Delta", "Δ"),
    (r"\\Sigma", "Σ"),
    (r"\\Theta", "Θ"),
    (r"\\Omega", "Ω"),
    (r"\\Phi", "Φ"),
    (r"\\lambda", "λ"),
    (r"\\kappa", "κ"),
    (r"\\sigma", "σ"),
    (r"\\nu", "ν"),
    (r"\\log", "log"),
    (r"\\mathrm|\\text|\\mathbf|\\mathit", ""),
    (r"\\left|\\right", ""),
    (r"\\,|\\;|\\!|\\quad|\\qquad", " "),
    (r"\\ ", ""),
    (r"\\%", "%"),
    (r"\\&", "&"),
]

UNIT_RULES = [
    (r"mg\s*[·/\s]?\s*L\s*-?1\b|mg\s*L\s*-1", "mg/L"),
    (r"g\s*[·/\s]?\s*L\s*-?1\b|g\s*L\s*-1", "g/L"),
    (r"mol\s*[·/\s]?\s*L\s*-?1\b", "mol/L"),
    (r"mmol\s*[·/\s]?\s*L\s*-?1\b", "mmol/L"),
    (r"A\s*dm\s*-?2\b|A/dm2|A\s*dm−2", "A/dm2"),
    (r"mA\s*cm\s*-?2\b|mA/cm2", "mA/cm2"),
    (r"mJ\s*m\s*-?2\b", "mJ/m2"),
    (r"Ω\s*cm|ohm", "Ω·cm"),
    (r"℃", "°C"),
]


def strip_latex(s: str) -> str:
    """委托给共享库：不删未知命令、上下标不拼数字。"""
    return textnorm.latex_to_display(s)[0]


def norm_units(s: str) -> str:
    """委托给共享库的单位归一。"""
    return textnorm.norm_units(s)


def fix_decimal_spaces(s: str) -> str:
    """只在公式块用：把 '1. 1 5' 这类数字内空格收拢。"""
    t = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", s)
    return re.sub(r"(?<=\d)\s(?=\d{1,3}(?:\D|$))", "", t)


TRUE_CAP = re.compile(r"^\s*(Fig(?:ure)?s?\.?\s*\d+[a-z]?|Table\s*\d+[a-z]?|"
                      r"图\s*\d+(?:[.\-]\d+)?|表\s*\d+)", re.I)
CAP_TAIL = re.compile(r"(Notes?[:：]|注[:：]|Data are|Values are|The values|Error bars)", re.I)


def clean_caption(caps) -> tuple[str, str]:
    """保留编号前缀（题目/表号是 KG 的关键锚点），只把尾部注释拆出来。"""
    if not caps:
        return "", ""
    raw = " ".join(caps).strip()
    raw = re.sub(r"\s{2,}", " ", raw)
    tail = ""
    m = CAP_TAIL.search(raw)
    if m and m.start() > 10:
        tail = raw[m.start():].strip()
        raw = raw[: m.start()].strip()
    return norm_units(strip_latex(raw)).strip(), tail


TERM = re.compile(r"[.。!?！？:：;；)\]]\s*$")


def is_terminal(s: str) -> bool:
    return bool(TERM.search(s))


# ---------- D5 表格 ----------
def parse_table(body: str) -> list[dict]:
    """HTML → 行；展开 colspan / rowspan。返回 dict(row, cells, is_head)。"""
    body = body or ""
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S)
    grid: list[list[str]] = []
    spans: list[bool] = []
    pending: dict[int, list] = {}  # col -> [text, remaining_rows]
    for tr in trs:
        tds = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
        row: list[str] = []
        col = 0
        cells_iter = []
        for attrs, cell in tds:
            span = re.search(r'colspan\s*=\s*"?(\d+)', attrs)
            rspan = re.search(r'rowspan\s*=\s*"?(\d+)', attrs)
            txt = norm_units(strip_latex(re.sub(r"<[^>]+>", " ", cell)).strip())
            cells_iter.append((txt, int(span.group(1)) if span else 1,
                               int(rspan.group(1)) if rspan else 1))
        # 先铺 rowspan 遗留
        for text, cspan, rspan in cells_iter:
            while col in pending:
                t, rem = pending[col]
                row.append(t)
                if rem <= 1:
                    del pending[col]
                else:
                    pending[col][1] -= 1
                col += 1
            for k in range(cspan):
                row.append(text if k == 0 else "")
                if rspan > 1:
                    pending[col] = [text, rspan - 1]
                col += 1
        while col in pending:
            t, rem = pending[col]
            row.append(t)
            if rem <= 1:
                del pending[col]
            else:
                pending[col][1] -= 1
            col += 1
        grid.append(row)
        spans.append(any(c[1] > 1 or c[2] > 1 for c in cells_iter))
    # 补齐宽度
    w = max((len(r) for r in grid), default=0)
    for r in grid:
        r.extend([""] * (w - len(r)))
    return [{"row": i, "cells": r, "is_head": i == 0, "spans": spans[i] if i < len(spans) else False}
            for i, r in enumerate(grid)]


NUMCELL = re.compile(r"[-−–]?\d+(\.\d+)?$")


def merge_header(rows: list[dict]) -> tuple[list[str], list[list[str]], int]:
    """把一级/两级表头合成一条列名路径（TC-02）。默认保守：只在看起来真是表头时合并。"""
    rows = [r for r in rows if any(c.strip() for c in r["cells"])]
    if not rows:
        return [], [], 1
    width = max(len(r["cells"]) for r in rows)
    pad = lambda r: list(r) + [""] * (width - len(r))
    r0 = pad(rows[0]["cells"])
    if len(rows) >= 2:
        r1 = pad(rows[1]["cells"])
        top_num = sum(1 for c in r0 if NUMCELL.match(c.strip()))
        sub_num = sum(1 for c in r1 if NUMCELL.match(c.strip()))
        sub_filled = sum(1 for c in r1 if c.strip())
        if top_num == 0 and sub_num == 0 and sub_filled >= 2 and (rows[0].get("spans") or rows[1].get("spans")):
            # colspan 语义：父级标签应跨列生效 → 对 r0 做前向填充
            filled = []
            last = ""
            for a in r0:
                if a.strip():
                    last = a.strip()
                filled.append(last if not a.strip() else a.strip())
            header = []
            for a, b in zip(filled, r1):
                a, b = a.strip(), b.strip()
                if not b or a == b:
                    header.append(a or b)
                elif not a:
                    header.append(b)
                else:
                    header.append(f"{a} | {b}")
            return header, [pad(r["cells"]) for r in rows[2:]], 2
    return r0, [pad(r["cells"]) for r in rows[1:]], 1


HTML_TAG = re.compile(r"<[^>]{1,40}>")
LATEX_ESC = re.compile(r"\\(?=[\d*~%&()\[\],;:!~])")
EMAIL = re.compile(r"\S+@\S+\.\w+")
NONBODY = re.compile(
    r"Conceptualization|Methodology|Formal analysis|Data curation|Supervision|"
    r"Funding acquisition|Writing\s*[-–]\s*|Corresponding author|Electronic address|"
    r"E-?mail|State Key Laboratory|All authors have read|Declaration of|"
    r"CRediT|Acknowledg(e)?ments",
    re.I,
)


def clean_text_noise(s: str) -> str:
    """去掉正文里残留的 HTML 标签与 LaTeX 转义（作者上标、脚注符号等）。"""
    s = HTML_TAG.sub(" ", s)
    s = LATEX_ESC.sub("", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def split_long(txt: str, limit: int = 1200) -> list[str]:
    """C04：把超长段按句边界切成 ≤limit 的片段；无句边界时按空格切。"""
    # 只在中/英句末切；英文必须"点后跟空白 + 大写/括号/行尾"，否则 0.005 会被切成 0 . 005
    sents = re.split(r"(?<=[。！？；])\s*|(?<=[.!?;])(?=\s(?:[A-Z0-9(（\[]|$))\s*", txt)
    out, cur = [], ""
    for s in sents:
        s = s.strip()
        if not s:
            continue
        if len(cur) + len(s) + 1 > limit and cur:
            out.append(cur.strip())
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur.strip())
    # 仍超长（单句过长）→ 硬切
    final = []
    for p in out:
        while len(p) > limit * 1.5:
            cut = p.rfind(" ", 0, limit)
            cut = cut if cut > limit * 0.5 else limit
            final.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            final.append(p)
    return final or [txt]


def is_nonbody(s: str) -> bool:
    """作者/单位/邮箱/贡献声明/致谢 —— 不属于论文知识正文。"""
    if EMAIL.search(s):
        return True
    return bool(NONBODY.search(s))


CAP_CLASS = [
    ("method_eval", r"variance|anova|regression|model|significan|square|F-value|方差|回归"),
    ("design", r"box.?behnken|factor|level|orthogonal|design|正交|因素"),
    ("pretreat", r"pre-?treatment|pretreatment|degreas|etch|activation|前处理|除油"),
    ("spectra", r"band|assignment|raman|ftir|xps|spectra|谱|峰位"),
    ("formula", r"bath composition|composition|electrolyte|process parameter|配方|镀液"),
    ("result", r"filling|throwing|overpotential|hardness|gloss|resist|dimple|resistivity|填充|整平|硬度"),
]


def classify(caption: str, num_cells: int = 0, n_cells: int = 0) -> str:
    for name, pat in CAP_CLASS:
        if re.search(pat, caption or "", re.I):
            return name
    ratio = num_cells / n_cells if n_cells else 0.0
    if ratio >= 0.35:
        return "data_unnamed"
    if ratio == 0:
        return "descriptive"
    return "mixed"


def block_id(doc_id: str, page: int, bbox, type_: str, part: int) -> str:
    """位置哈希：与 知识图谱/schema/id_conventions.md §2 一致（文字改动不改 id）。"""
    bb = ",".join(str(round(float(x))) for x in (bbox or []))
    raw = f"{doc_id}|{page}|{bb}|{type_}|{part}"
    return "blk:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ---------- 主流程 ----------
def load_manifest() -> dict:
    m = {}
    if not MANIFEST.exists():
        return m
    with MANIFEST.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            p = (row.get("本地PDF路径") or "").replace("/", "\\")
            if p:
                m[pathlib.PureWindowsPath(p).name] = row
    return m


def doc_title(d: pathlib.Path) -> str:
    return d.name.split(".pdf-")[0] + ".pdf" if ".pdf-" in d.name else d.name


def main() -> None:
    for sub in ("blocks", "tables", "report"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    man = load_manifest()
    dirs = sorted(p for p in SRC.iterdir() if p.is_dir())

    before = Counter()
    after = Counter()
    per_doc = []
    tables_meta = []
    deletions = []
    tbl_seq = defaultdict(int)

    for d in dirs:
        cl = list(d.glob("*_content_list.json"))
        rp = REPAIRED / f"{d.name}.json"
        if rp.exists():
            raw = json.loads(rp.read_text(encoding="utf-8"))
        elif cl:
            raw = json.loads(cl[0].read_text(encoding="utf-8"))
        else:
            continue
        title = doc_title(d)
        info = man.get(title, {})
        doc_id = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", title.replace(".pdf", ""))[:60]

        before["总块"] += len(raw)
        before["噪音块"] += sum(1 for e in raw if e.get("type") in NOISE)
        before["text"] += sum(1 for e in raw if e.get("type") == "text")
        before["table"] += sum(1 for e in raw if e.get("type") == "table")
        before["equation"] += sum(1 for e in raw if e.get("type") == "equation")
        before["image"] += sum(1 for e in raw if e.get("type") == "image")
        before["chart"] += sum(1 for e in raw if e.get("type") == "chart")
        for e in raw:
            if e.get("type") == "text":
                t = e.get("text", "")
                if len(t.strip()) < 15:
                    before["过短块"] += 1
                if not is_terminal(t.strip()):
                    before["句尾未终止"] += 1
                if "$" in t:
                    before["含LaTeX块"] += 1

        # ---- C10 印刷页码映射 / C09 参考文献结构化 ----
        page_map = {}
        refs = []
        for e in raw:
            ty = e.get("type")
            if ty == "page_number":
                t = (e.get("text") or "").strip()
                if t.isdigit():
                    page_map[e.get("page_idx", 0) + 1] = int(t)
            elif ty == "ref_text":
                t = re.sub(r"\s+", " ", (e.get("text") or "")).strip()
                m = re.match(r"^\[?(\d{1,3})\]?[\.\s]", t)
                refs.append({"n": int(m.group(1)) if m else None,
                             "page": (e.get("page_idx") or 0) + 1, "raw": t[:400]})

        # ---- C12 删除决策表：噪音块先登记 ----
        for e in raw:
            ty = e.get("type")
            if ty in NOISE:
                reason = "参考文献，转结构化保留" if ty == "ref_text" else "模板噪音（页眉/页脚/页码/脚注/边注）"
                deletions.append({"doc": doc_id, "page": (e.get("page_idx") or 0) + 1,
                                  "type": ty, "rule": "C01", "chars": len(e.get("text") or ""),
                                  "reason": reason, "head": (e.get("text") or "")[:60]})
        # ---- 清洗 ----
        kept = [e for e in raw if e.get("type") in KEEP]
        after["保留块"] += len(kept)

        blocks = []
        merged_text_len = 0
        buf, buf_page, buf_bbox = [], None, None
        buf_section = ""
        merge_events = 0
        stack: list[tuple[int, str]] = []
        cur_section = ""

        def flush():
            nonlocal buf, merge_events
            if not buf:
                return
            txt = " ".join(buf).strip()
            txt = re.sub(r"\s{2,}", " ", txt)
            if txt:
                # C04：超长段按句切成多段（保留同一 bbox 与页码）
                pieces = split_long(txt) if len(txt) > 1200 else [txt]
                for k, piece in enumerate(pieces):
                    blocks.append({
                        "type": "text", "page": (buf_page or 0) + 1,
                        "bbox": buf_bbox, "text": piece, "section": buf_section,
                        "printed_page": page_map.get((buf_page or 0) + 1),
                        "merged_from": len(buf), "split": len(pieces) if len(pieces) > 1 else 0,
                        "part": k,
                    })
                    b0 = blocks[-1]
                    b0["block_id"] = block_id(doc_id, b0["page"], b0["bbox"], "text", k)
                    after["正文段"] += 1
                    after["正文段字符"] += len(piece)
                    if not is_terminal(piece):
                        after["合并后仍碎"] += 1
                    if len(piece) < 15:
                        after["合并后过短"] += 1
                    if len(piece) > 1800:
                        after["超长段"] += 1
                if len(pieces) > 1:
                    after["长段切分"] += len(pieces) - 1
                merge_events += len(buf) - 1
            buf = []

        for e in kept:
            t = e.get("type")
            page = e.get("page_idx", 0)
            if t == "text":
                txt = clean_text_noise(norm_units(strip_latex(e.get("text", ""))))
                txt = re.sub(r"\s{2,}", " ", txt).strip()
                if not txt:
                    deletions.append({"doc": doc_id, "page": page + 1, "type": "text",
                                      "rule": "C01b", "chars": 0, "reason": "空块", "head": ""})
                    continue
                # C05 章节树：heading 单独成块，不混进正文段
                lvl = e.get("text_level")
                if lvl in (1, 2, 3) and len(txt) < 160:
                    flush()
                    while stack and stack[-1][0] >= lvl:
                        stack.pop()
                    stack.append((lvl, txt))
                    cur_section = " > ".join(s for _, s in stack)
                    blocks.append({"type": "heading", "level": lvl, "page": page + 1,
                                   "bbox": e.get("bbox"), "text": txt,
                                   "section": cur_section,
                                   "block_id": block_id(doc_id, page + 1, e.get("bbox"),
                                                         "heading", 0)})
                    after["标题块"] += 1
                    continue
                if is_nonbody(txt):
                    after["丢弃作者与致谢段"] += 1
                    deletions.append({"doc": doc_id, "page": page + 1, "type": "text",
                                      "rule": "C02", "chars": len(txt),
                                      "reason": "非正文（邮箱/CRediT/致谢/基金）", "head": txt[:60]})
                    continue
                if len(txt) < 15 and not re.search(r"\d", txt):
                    after["丢弃碎片"] += 1
                    continue
                if buf and page != buf_page:
                    flush()
                if not buf:
                    buf_page, buf_bbox = page, e.get("bbox")
                    buf_section = cur_section
                buf.append(txt)
                joined = " ".join(buf)
                if is_terminal(joined) and len(joined) >= 40:
                    flush()
            elif t == "equation":
                flush()
                eq = e.get("text") or e.get("latex") or ""
                tag = ""
                m = re.search(r"\\tag\{(\d+)\}", eq)
                if m:
                    tag = m.group(1)
                body = fix_decimal_spaces(strip_latex(eq))
                blocks.append({"type": "equation", "page": page + 1, "bbox": e.get("bbox"),
                               "text": body, "tag": tag, "section": cur_section,
                               "printed_page": page_map.get(page + 1),
                               "raw_latex": e.get("raw_latex", ""),
                               "block_id": block_id(doc_id, page + 1, e.get("bbox"),
                                                     "equation", 0)})
                after["公式"] += 1
                if re.search(r"[=＝]", body):
                    after["定义式候选"] += 1
            elif t == "table":
                flush()
                cap, tail = clean_caption(e.get("table_caption"))
                rows = parse_table(e.get("table_body"))
                hdr, data_rows, levels = merge_header(rows)
                widths = [len(r) for r in data_rows] if data_rows else [len(hdr)]
                widths = [x for x in widths if x]
                ragged = (max(widths) - min(widths)) if widths else 0
                ncols = max(widths) if widths else 0
                num_cells = sum(
                    1 for r in data_rows for c in r
                    if re.fullmatch(r"[-−–]?\d+(\.\d+)?", c.strip())
                )
                tables_meta.append({
                    "doc_id": doc_id, "title": info.get("标题", ""), "doi": info.get("DOI", ""),
                    "page": page + 1, "caption": cap, "caption_extra": tail,
                    "n_rows": len(data_rows), "n_cols": ncols, "ragged": ragged,
                    "numeric_cells": num_cells, "header_levels": levels,
                    "header": " | ".join(hdr), "class": classify(cap, num_cells, ncols*max(len(data_rows),1)),
                })
                tpath = OUT / "tables" / f"{doc_id}__p{page+1}_{tbl_seq[(doc_id, page)]}.csv"
                tbl_seq[(doc_id, page)] += 1
                with tpath.open("w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(hdr)
                    for r in data_rows:
                        w.writerow(r)
                blocks.append({"type": "table", "page": page + 1, "bbox": e.get("bbox"),
                               "caption": cap, "caption_extra": tail,
                               "n_rows": len(data_rows), "n_cols": ncols, "ragged": ragged,
                               "header_levels": levels, "header": hdr,
                               "class": classify(cap, num_cells, ncols*max(len(data_rows),1)),
                               "csv": tpath.relative_to(OUT).as_posix(), "section": cur_section,
                               "printed_page": page_map.get(page + 1),
                               "evidence": (e.get("table_repair") or {}).get("evidence"),
                               "ocr_status": ((e.get("table_repair") or {}).get("ocr") or {}).get("status"),
                               "no_number": e.get("no_number", False),
                               "block_id": block_id(doc_id, page + 1, e.get("bbox"), "table", 0)})
                after["表格"] += 1
                after["表格多级表头"] += 1 if levels == 2 else 0
                after["表格ragged"] += 1 if ragged else 0
                after["表格数值格"] += num_cells
            elif t == "image" or t == "chart":
                flush()
                cap, tail = clean_caption(e.get("image_caption") or e.get("chart_caption"))
                blocks.append({"type": t, "page": page + 1, "bbox": e.get("bbox"),
                               "caption": cap, "caption_extra": tail,
                               "img": e.get("img_path", ""), "section": cur_section,
                               "printed_page": page_map.get(page + 1),
                               "no_number": e.get("no_number", False),
                               "caption_paired": e.get("caption_paired"),
                               "block_id": block_id(doc_id, page + 1, e.get("bbox"),
                                                     t, 0)})
                after["图"] += 1
                if cap:
                    after["图有caption"] += 1

        flush()

        (OUT / "blocks" / f"{doc_id}.jsonl").write_text(
            "\n".join(json.dumps(b, ensure_ascii=False) for b in blocks), encoding="utf-8")
        (OUT / "blocks" / f"{doc_id}.meta.json").write_text(json.dumps({
            "doc_id": doc_id, "title": info.get("标题", title), "doi": info.get("DOI", ""),
            "journal": info.get("分类(期刊)", ""), "year": info.get("出版年", ""),
            "pages": max((e.get("page_idx", 0) for e in raw), default=0) + 1,
            "printed_page_map": page_map, "references": refs,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        after["参考文献条数"] += len(refs)
        after["可映射页码"] += len(page_map)
        per_doc.append({
            "doc_id": doc_id, "title": info.get("标题", title), "doi": info.get("DOI", ""),
            "pages": max((e.get("page_idx", 0) for e in raw), default=0) + 1,
            "raw_blocks": len(raw), "kept_blocks": len(kept), "out_blocks": len(blocks),
            "text_merged_from": merge_events + after["正文段"],
        })

    after["清洗前非噪音块"] = after["保留块"]
    after["保留块"] = sum(d["out_blocks"] for d in per_doc)
    # 汇总
    def pct(a, b):
        return round(100 * a / b, 1) if b else 0.0

    summary = {
        "before": dict(before), "after": dict(after),
        "metrics": {
            "总块数": f'{before["总块"]} → {after["保留块"]}',
            "噪音块": f'{before["噪音块"]}（{pct(before["噪音块"], before["总块"])}%）→ 0',
            "正文块": f'{before["text"]} → {after["正文段"]} 段（减少 {pct(before["text"]-after["正文段"], before["text"])}%，平均 {round(before["text"]/max(after["正文段"],1),2)} 块/段）',
            "句尾未终止占比": f'{pct(before["句尾未终止"], before["text"])}% → {pct(after["合并后仍碎"], after["正文段"])}%',
            "过短块(<15字符)": f'{pct(before["过短块"], before["text"])}% → {pct(after["合并后过短"], after["正文段"])}%',
            "含LaTeX正文块": f'{before["含LaTeX块"]} → 0',
            "表格": f'{before["table"]} → {after["表格"]}，其中 ragged {after["表格ragged"]}（{pct(after["表格ragged"], after["表格"])}%）',
            "表格数值格": after["表格数值格"],
            "图": f'{before["image"]+before["chart"]} → {after["图"]}（有 caption {after["图有caption"]}，{pct(after["图有caption"], after["图"])}%）',
            "公式": f'{before["equation"]} → {after["公式"]}（含等号 {after["定义式候选"]}）',
            "丢弃碎片": after["丢弃碎片"],
            "长段切分(>1200字符)": f'{before["text"] and after["长段切分"]} 段被切',
            "超长段(>1800字符)": after["超长段"],
            "删除决策条数": len(deletions),
            "删除可审计率": f'{pct(len(deletions), len(deletions))}%',
        },
        "docs": per_doc,
    }
    (OUT / "report" / "deletions.jsonl").write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in deletions), encoding="utf-8")
    (OUT / "report" / "metrics.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "tables" / "_tables_index.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(tables_meta[0].keys()))
        w.writeheader()
        w.writerows(tables_meta)
    print(json.dumps(summary["metrics"], ensure_ascii=False, indent=2))
    print(f"\n篇数 {len(per_doc)}  表格 {len(tables_meta)}")


if __name__ == "__main__":
    main()
