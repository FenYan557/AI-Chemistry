# -*- coding: utf-8 -*-
"""阶段03 步骤5：合并抽取与消歧结果，规则降级，落盘 JSONL + 质检。

输入：
  out/extraction/{doc_id}.json      抽取结果（JSON 数组）
  out/disambiguation/{doc_id}.json  消歧结果（JSON 数组）
输出：
  out/final/{doc_id}.json           每篇一份，chemicals 列表
  out/final/_qc.json                质检汇总

规则（按参考稿）：
  1. 同一 span 跨来源（text/table/figure_caption）合并为一条，
     正文 context 为主，其余进 alt_contexts。
  2. source_type=figure_caption 且有备选 CID 时，即使 LLM 判 matched
     也降级为 ambiguous，review_note 记录"图注来源强制降级"。
  3. spec_of_general / unmatched_new 原样保留，不做任何硬匹配修补。

仅依赖标准库。在仓库根目录运行：
    python -X utf8 清洗/03_化学物质抽取消歧/scripts/merge_results.py
"""
import json
import sys
from pathlib import Path

STAGE = Path(__file__).resolve().parents[1]
EXTRACT_DIR = STAGE / "out" / "extraction"
DISAM_DIR = STAGE / "out" / "disambiguation"
FINAL_DIR = STAGE / "out" / "final"

SOURCE_RANK = {"text": 0, "table": 1, "figure_caption": 2}


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def merge_doc(doc_id):
    extractions = load_json(EXTRACT_DIR / f"{doc_id}.json")
    disam_path = DISAM_DIR / f"{doc_id}.json"
    disam = {}
    if disam_path.is_file():
        for d in load_json(disam_path):
            disam[(d.get("span"), d.get("unit_id"))] = d

    by_span = {}
    for e in extractions:
        span = (e.get("span") or "").strip()
        if not span:
            continue
        d = disam.get((e.get("span"), e.get("unit_id"))) or {}
        rec = by_span.setdefault(span, {
            "span": span,
            "span_form": e.get("span_form", ""),
            "context": "",
            "alt_contexts": [],
            "source_type": "",
            "table_id": "",
            "figure_id": "",
            "unit_ids": [],
            "link_status": d.get("link_status", "pending"),
            "pubchem_cid": d.get("pubchem_cid"),
            "alt_cids": d.get("alt_cids", []),
            "reason": d.get("reason", ""),
            "review_note": d.get("review_note", ""),
            "_best": (9, ""),
        })
        rec["unit_ids"].append(e.get("unit_id", ""))
        ctx = e.get("context", "")
        src = e.get("source_type", "text")
        rank = SOURCE_RANK.get(src, 9)
        if not rec["context"]:
            rec["context"] = ctx
            rec["source_type"] = src
            rec["table_id"] = e.get("table_id", "")
            rec["figure_id"] = e.get("figure_id", "")
            rec["_best"] = (rank, ctx)
        elif rank < rec["_best"][0]:
            rec["alt_contexts"].append(rec["context"])
            rec["context"] = ctx
            rec["source_type"] = src
            rec["table_id"] = e.get("table_id", "")
            rec["figure_id"] = e.get("figure_id", "")
            rec["_best"] = (rank, ctx)
        else:
            rec["alt_contexts"].append(ctx)

    chemicals = []
    for rec in by_span.values():
        rec.pop("_best", None)
        if (rec["source_type"] == "figure_caption"
                and rec["link_status"] == "matched"
                and len(rec.get("alt_cids") or []) >= 1):
            rec["link_status"] = "ambiguous"
            rec["review_note"] = (rec["review_note"]
                                  + " [图注来源候选>=2，强制降级]").strip()
        chemicals.append(rec)
    chemicals.sort(key=lambda r: (r["source_type"], r["span"]))
    return chemicals


def main():
    if not EXTRACT_DIR.is_dir():
        print(f"未找到 {EXTRACT_DIR}，请先完成步骤2（抽取）。", file=sys.stderr)
        return 1
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    qc = {"docs": 0, "chemicals": 0, "by_status": {}, "pending_docs": []}
    for path in sorted(EXTRACT_DIR.glob("*.json")):
        doc_id = path.stem
        chemicals = merge_doc(doc_id)
        out = {"paper_id": doc_id, "chemicals": chemicals}
        with (FINAL_DIR / f"{doc_id}.json").open("w", encoding="utf-8",
                                                 newline="\n") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        qc["docs"] += 1
        qc["chemicals"] += len(chemicals)
        if any(c["link_status"] == "pending" for c in chemicals):
            qc["pending_docs"].append(doc_id)
        for c in chemicals:
            qc["by_status"][c["link_status"]] = \
                qc["by_status"].get(c["link_status"], 0) + 1
    with (FINAL_DIR / "_qc.json").open("w", encoding="utf-8") as f:
        json.dump(qc, f, ensure_ascii=False, indent=2)
    print(json.dumps(qc, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())