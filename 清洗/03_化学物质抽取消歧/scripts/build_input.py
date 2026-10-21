# -*- coding: utf-8 -*-
"""阶段03 步骤1：从 02_清洗 产物组装化学物质抽取单元。

输出 out/extraction_input/{doc_id}.jsonl，每行一个抽取单元：
  text           正文检索块（来自 chunks）
  table          表格行记录（[TABLE ...] 开头，列名 + 行值，整表不切开）
  figure_caption 图片题注（[FIGURE ...] 开头）

同时输出 out/extraction_input/_summary.json 汇总计数。
仅依赖标准库。在仓库根目录运行：
    python -X utf8 清洗/03_化学物质抽取消歧/scripts/build_input.py
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLEAN_OUT = ROOT / "清洗" / "02_清洗" / "out"
STAGE_OUT = Path(__file__).resolve().parents[1] / "out" / "extraction_input"

MAX_TABLE_ROWS = 60  # 超出则截断并标记，防止单表撑爆上下文


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def table_unit(doc_id, tidx, block):
    """把一个表格块转成 [TABLE] 行记录文本。"""
    csv_rel = block.get("csv") or ""
    csv_path = CLEAN_OUT / csv_rel
    table_id = Path(csv_rel).stem if csv_rel else f"{doc_id}#t{tidx}"
    header = [h.strip() for h in (block.get("header") or [])]
    lines = [
        f'[TABLE id={table_id} section="{block.get("section", "")}" '
        f'caption="{block.get("caption", "")}"]'
    ]
    if header:
        lines.append("列名：" + " | ".join(header))
    truncated = False
    if csv_path.is_file():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        # 跳过与表头重复的首行
        if rows and header and [c.strip() for c in rows[0]] == header:
            rows = rows[1:]
        if len(rows) > MAX_TABLE_ROWS:
            rows = rows[:MAX_TABLE_ROWS]
            truncated = True
        for i, row in enumerate(rows, 1):
            lines.append(f"行{i}：" + " | ".join(c.strip() for c in row))
    else:
        lines.append("（CSV 缺失，仅有表头）")
    if truncated:
        lines.append(f"（表格超过 {MAX_TABLE_ROWS} 行，已截断）")
    return {
        "unit_id": f"{doc_id}#table{tidx}",
        "source_type": "table",
        "table_id": table_id,
        "figure_id": "",
        "section": block.get("section", ""),
        "page": block.get("page"),
        "text": "\n".join(lines),
    }


def build_doc(doc_id):
    blocks_path = CLEAN_OUT / "blocks" / f"{doc_id}.jsonl"
    chunks_path = CLEAN_OUT / "chunks" / f"{doc_id}.jsonl"
    units = []
    if chunks_path.is_file():
        for ch in read_jsonl(chunks_path):
            if ch.get("type") != "text":
                continue
            units.append({
                "unit_id": ch["chunk_id"],
                "source_type": "text",
                "table_id": "",
                "figure_id": "",
                "section": ch.get("section", ""),
                "page": ch.get("page"),
                "text": ch.get("text", ""),
            })
    if blocks_path.is_file():
        tidx = fidx = 0
        for blk in read_jsonl(blocks_path):
            if blk.get("type") == "table" and blk.get("csv"):
                tidx += 1
                units.append(table_unit(doc_id, tidx, blk))
            elif blk.get("type") == "image":
                caption = (blk.get("caption") or "").strip()
                if not caption:
                    continue  # 无题注的图形型图片不进抽取流
                fidx += 1
                figure_id = f"{doc_id}#fig{fidx}"
                units.append({
                    "unit_id": figure_id,
                    "source_type": "figure_caption",
                    "table_id": "",
                    "figure_id": figure_id,
                    "section": blk.get("section", ""),
                    "page": blk.get("page"),
                    "text": f'[FIGURE id={figure_id} section="{blk.get("section", "")}"]\n'
                            f"图注：{caption}",
                })
    return units


def main():
    chunks_dir = CLEAN_OUT / "chunks"
    doc_ids = sorted(p.stem for p in chunks_dir.glob("*.jsonl"))
    STAGE_OUT.mkdir(parents=True, exist_ok=True)
    summary = {"docs": 0, "text": 0, "table": 0, "figure_caption": 0,
               "total_chars": 0, "per_doc": {}}
    for doc_id in doc_ids:
        units = build_doc(doc_id)
        out_path = STAGE_OUT / f"{doc_id}.jsonl"
        with out_path.open("w", encoding="utf-8", newline="\n") as f:
            for u in units:
                f.write(json.dumps(u, ensure_ascii=False) + "\n")
        summary["docs"] += 1
        counts = {"text": 0, "table": 0, "figure_caption": 0}
        chars = 0
        for u in units:
            counts[u["source_type"]] += 1
            chars += len(u["text"])
        for k in counts:
            summary[k] += counts[k]
        summary["total_chars"] += chars
        summary["per_doc"][doc_id] = {**counts, "chars": chars}
    with (STAGE_OUT / "_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: summary[k] for k in
                      ("docs", "text", "table", "figure_caption", "total_chars")},
                     ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
