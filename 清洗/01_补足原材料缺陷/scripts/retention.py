# -*- coding: utf-8 -*-
"""信息保留度评估（v3，按审查意见 P2-6 修正度量）。

修正点：
  1. 数字改为**多重集**比较（`10 10 10` ≠ `10`），并保留符号
  2. 识别 U+2212 负号、科学计数法 `1e-3`、千分位 `1,234.56`
  3. 单位归一走共享库（修 `[cm/]` 字符类错误）
  4. IR 纳入 precision
  5. 宏平均与中位数从同一份数据生成，不再手抄
  6. 明确标注这是"文本层一致性诊断"，不是正确率

输出：out/report/retention.json
"""
from __future__ import annotations

import json
import pathlib
import re
import statistics
import sys
import unicodedata
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BASE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "lib"))
sys.path.insert(0, str(BASE / "02_清洗" / "scripts"))
import textnorm  # noqa: E402
import clean  # noqa: E402

SRC = clean.SRC
REP = BASE / "01_补足原材料缺陷" / "out" / "repaired"
REPORT = BASE / "01_补足原材料缺陷" / "out" / "report"

UNIT = re.compile(r"(mg/L|g/L|mol/L|mmol/L|ppm|mA/cm2|A/dm2|mV|mJ/m2|μm|nm|°C|mM|wt%|RPM|rpm|%)", re.I)
WEIGHTS = {"value_recall": 0.30, "value_precision": 0.10, "sent_recall": 0.30,
           "unit_recall": 0.15, "cell_value_recall": 0.15}
NUM = re.compile(r"[-−–+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-−]?\d+)?")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s)).lower()


def num_counter(s: str) -> Counter:
    c: Counter = Counter()
    for m in NUM.finditer(s or ""):
        v = m.group(0).replace("−", "-").replace("–", "-").replace(",", "")
        try:
            c["%g" % float(v)] += 1
        except ValueError:
            pass
    return c


def unit_set(s: str) -> set[str]:
    return {textnorm.norm_units(m.group(0)).lower() for m in UNIT.finditer(s or "")}


def pdf_pages(path: pathlib.Path) -> list[str]:
    try:
        import fitz
        doc = fitz.open(path)
        pages = [p.get_text() for p in doc]
        doc.close()
        return pages
    except Exception:
        return []


REF_START = re.compile(r"^\s*(References|REFERENCES|Reference|参考文献|REFERENCES AND NOTES)\s*$", re.M)
NOISE_LINE = re.compile(r"(ISSN|https?://|doi\.org|©|Available online|E-mail|"
                        r"Corresponding author|Journal of|Vol\.\s*\d|Received .*accepted)", re.I)


def body_text(pages: list[str]) -> str:
    """去掉参考文献之后的部分与页眉页脚样行，作为"该保留的内容"基线。"""
    txt = "\n".join(pages)
    m = REF_START.search(txt)
    if m and m.start() > len(txt) * 0.3:
        txt = txt[: m.start()]
    keep = [ln for ln in txt.splitlines() if not NOISE_LINE.search(ln)]
    return "\n".join(keep)


def sentences(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.。!?！？])\s+", s) if len(x.strip()) > 25]


def main() -> None:
    docs = []
    for d in sorted(x for x in SRC.iterdir() if x.is_dir()):
        pdfs = list(d.glob("*.pdf"))
        rf = REP / f"{d.name}.json"
        if not pdfs or not rf.exists():
            continue
        blocks = json.loads(rf.read_text(encoding="utf-8"))
        pages = pdf_pages(pdfs[0])
        pdf_text = "\n".join(pages)

        mine_parts, cap_parts = [], []
        for b in blocks:
            t = b.get("type")
            if t in ("text", "equation"):
                mine_parts.append(b.get("text") or "")
            elif t == "table":
                mine_parts.append(re.sub(r"<[^>]+>", " ", b.get("table_body") or ""))
                cap_parts.extend(b.get("table_caption") or [])
            elif t in ("image", "chart"):
                cap_parts.extend(b.get("image_caption") or b.get("chart_caption") or [])
        mine = "\n".join(mine_parts)
        caps = "\n".join(cap_parts)

        body = body_text(pages)
        pc, mc = num_counter(body), num_counter(mine + "\n" + caps)
        pc_all = num_counter(pdf_text)
        hit = sum(min(v, mc.get(k, 0)) for k, v in pc.items())
        added = sum(max(0, mc.get(k, 0) - pc.get(k, 0)) for k in mc)
        vrec = hit / sum(pc.values()) if pc else None
        vprec = hit / (hit + added) if (hit + added) else None
        hit_all = sum(min(v, mc.get(k, 0)) for k, v in pc_all.items())
        vrec_all = hit_all / sum(pc_all.values()) if pc_all else None

        sents = sentences(body)
        if sents:
            hay = norm(mine + "\n" + caps)
            def hit(sent: str) -> bool:
                t = norm(sent)
                if not t:
                    return False
                if t[:80] in hay:
                    return True
                # PDF 换行会打断句子：用 40 字窗口做滑窗匹配（旧口径）
                return any(t[i:i + 40] in hay for i in range(0, max(1, len(t) - 40), 20))
            ok = sum(1 for s in sents if hit(s))
            srec = ok / len(sents)
        else:
            srec = None

        pu, mu = unit_set(pdf_text), unit_set(mine + "\n" + caps)
        urec = len(pu & mu) / len(pu) if pu else None

        cell = []
        for b in blocks:
            if b.get("type") != "table":
                continue
            tb = num_counter(re.sub(r"<[^>]+>", " ", b.get("table_body") or ""))
            if not tb:
                continue
            cell.append(sum(min(v, pc.get(k, 0)) for k, v in tb.items()) / sum(tb.values()))
        crec = sum(cell) / len(cell) if cell else None

        docs.append({"doc": clean.doc_title(d)[:56],
                     "value_recall": round(vrec, 3) if vrec is not None else None,
                     "value_precision": round(vprec, 3) if vprec is not None else None,
                     "value_recall_wholepdf": round(vrec_all, 3) if vrec_all is not None else None,
                     "sent_recall": round(srec, 3) if srec is not None else None,
                     "unit_recall": round(urec, 3) if urec is not None else None,
                     "cell_value_recall": round(crec, 3) if crec is not None else None,
                     "n_values": sum(pc.values()), "n_values_wholepdf": sum(pc_all.values()),
                     "n_sent": len(sents), "n_tables": len(cell)})

    def med(k):
        v = [d[k] for d in docs if d.get(k) is not None]
        return round(statistics.median(v), 3) if v else None

    def mean(k):
        v = [d[k] for d in docs if d.get(k) is not None]
        return round(sum(v) / len(v), 3) if v else None

    keys = ("value_recall", "value_precision", "sent_recall", "unit_recall",
            "cell_value_recall", "value_recall_wholepdf")
    macro = {k: mean(k) for k in keys}
    medians = {k: med(k) for k in keys}
    score = []
    for d in docs:
        parts, ws = 0.0, 0.0
        for k, w in WEIGHTS.items():
            if d.get(k) is not None:
                parts += w * d[k]
                ws += w
        if ws:
            score.append(parts / ws)
    macro["IR"] = round(sum(score) / len(score), 3) if score else None
    medians["IR"] = round(statistics.median(score), 3) if score else None

    worst = sorted(docs, key=lambda d: d.get("value_recall") or 0)[:5]
    out = {"note": "文本层一致性诊断，不是正确率；已修符号/科学计数法/多重集",
           "weight_scheme": WEIGHTS, "macro": macro, "median": medians,
           "n_docs": len(docs), "docs": docs, "worst": worst}
    (REPORT / "retention.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print("== 信息保留度 v3 ==")
    print("  宏平均:", json.dumps(macro, ensure_ascii=False))
    print("  中位数:", json.dumps(medians, ensure_ascii=False))
    print("  最差 3 篇:", [(d["doc"][:22], d["value_recall"], d["sent_recall"]) for d in worst[:3]])


if __name__ == "__main__":
    main()
