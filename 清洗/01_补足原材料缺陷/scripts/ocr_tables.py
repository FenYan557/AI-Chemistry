# -*- coding: utf-8 -*-
"""表格 OCR 独立复核（v2，修正坐标尺度）。

审查意见 P1-1：content_list 的 bbox 是 **0–1000 归一坐标**，不是 PDF 点。
本版显式换算并做边界校验；每张表用稳定 tid 记录，页面级与表级证据分开。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = pathlib.Path(__file__).resolve().parents[2]
SRC = pathlib.Path(__file__).resolve().parents[3] / "知识图谱所需文献" / "文献提取"
REP = BASE / "01_补足原材料缺陷" / "out" / "repaired"
REPORT = BASE / "01_补足原材料缺陷" / "out" / "report"

NUM = re.compile(r"[-−–]?\d+(?:\.\d+)?")
DPR = 300 / 72


def nums(s: str) -> set[str]:
    out = set()
    for m in NUM.finditer(s or ""):
        v = m.group(0).replace("−", "-").replace("–", "-")
        try:
            out.add("%g" % float(v))
        except ValueError:
            pass
    return out


def table_nums(html: str) -> set[str]:
    return nums(re.sub(r"<[^>]+>", " ", html or ""))


def bbox_to_points(b, w: float, h: float) -> tuple[tuple[float, float, float, float], str]:
    """返回 (点坐标, 坐标系)。max>1000 视为已是点坐标。"""
    if not b:
        return (0, 0, 0, 0), "missing"
    if max(b) > 1000:
        x0, y0, x1, y1 = b
        kind = "points"
    else:
        x0, y0, x1, y1 = b[0] / 1000 * w, b[1] / 1000 * h, b[2] / 1000 * w, b[3] / 1000 * h
        kind = "normalized0_1000"
    x0, x1 = sorted((max(0, x0), min(w, x1)))
    y0, y1 = sorted((max(0, y0), min(h, y1)))
    if x1 - x0 < 20 or y1 - y0 < 10:
        return (x0, y0, x1, y1), f"{kind}_degenerate"
    return (x0, y0, x1, y1), kind


def main() -> None:
    import fitz
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    out: dict[str, list] = {}
    coords: dict[str, int] = {}
    for d in sorted(x for x in SRC.iterdir() if x.is_dir()):
        pdfs = list(d.glob("*.pdf"))
        rf = REP / f"{d.name}.json"
        if not pdfs or not rf.exists():
            continue
        blocks = [b for b in json.loads(rf.read_text(encoding="utf-8")) if b.get("type") == "table"]
        if not blocks:
            continue
        doc = fitz.open(pdfs[0])
        entries = []
        for b in blocks:
            page_idx = b.get("page_idx") or 0
            if page_idx >= len(doc):
                continue
            page = doc[page_idx]
            w, h = page.rect.width, page.rect.height
            box, kind = bbox_to_points(b.get("bbox"), w, h)
            coords[kind] = coords.get(kind, 0) + 1
            mine = table_nums(b.get("table_body") or "")
            rec = {"tid": b.get("tid"), "page": page_idx + 1, "n_values": len(mine),
                   "coord": kind, "bbox_pts": [round(v, 1) for v in box]}
            for label, rect in (("bbox", box), ("page", (0, 0, w, h))):
                text = ""
                for dpi in (300, 200, 140):
                    rw, rh = (rect[2] - rect[0]) * dpi / 72, (rect[3] - rect[1]) * dpi / 72
                    if max(rw, rh) > 2400:
                        dpi = max(120, int(dpi * 2400 / max(rw, rh)))
                    try:
                        pix = page.get_pixmap(clip=fitz.Rect(*rect), dpi=dpi)
                        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                        res, _ = ocr(img)
                        text = " ".join(r[1] for r in (res or []))
                        break
                    except Exception as ex:      # 内存分配失败等：降分辨率重试
                        rec[f"{label}_ocr_error"] = f"{type(ex).__name__}@{dpi}dpi"
                        continue
                got = nums(text)
                rec[f"{label}_found"] = len(got)
                rec[f"{label}_agreement"] = round(len(mine & got) / len(mine), 3) if mine else None
            rec["bbox_content_mismatch"] = (
                rec["bbox_agreement"] is not None and rec["page_agreement"] is not None
                and rec["page_agreement"] - rec["bbox_agreement"] > 0.3)
            entries.append(rec)
            print(f"  {d.name[:26]} p{page_idx+1} {kind:20s} "
                  f"bbox={rec['bbox_agreement']} page={rec['page_agreement']} n={len(mine)}")
        doc.close()
        out[d.name] = entries
        (REPORT / "ocr_check.json").write_text(
            json.dumps({"coords": coords, "docs": out}, ensure_ascii=False, indent=2), encoding="utf-8")

    (REPORT / "ocr_check.json").write_text(
        json.dumps({"coords": coords, "docs": out}, ensure_ascii=False, indent=2), encoding="utf-8")

    n = sum(len(v) for v in out.values())
    bm = sum(1 for v in out.values() for e in v if e.get("bbox_content_mismatch"))
    bbox_ag = [e["bbox_agreement"] for v in out.values() for e in v if e["bbox_agreement"] is not None]
    page_ag = [e["page_agreement"] for v in out.values() for e in v if e["page_agreement"] is not None]
    print(f"\n表 {n} 张；坐标系 {coords}")
    print(f"  bbox 区域命中均值 {sum(bbox_ag)/len(bbox_ag):.3f}（{len(bbox_ag)} 张）")
    print(f"  整页命中均值     {sum(page_ag)/len(page_ag):.3f}（{len(page_ag)} 张）")
    print(f"  bbox 与整页差距>0.3 的表 {bm} 张")
    (REPORT / "ocr_summary.json").write_text(json.dumps({
        "tables": n, "coords": coords, "bbox_mean": round(sum(bbox_ag)/len(bbox_ag), 3),
        "page_mean": round(sum(page_ag)/len(page_ag), 3), "bbox_mismatch": bm,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
