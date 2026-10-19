# -*- coding: utf-8 -*-
"""C11 切块：600 字符 / 80 重叠，不跨 section，带页码、章节路径与来源溯源。

输入：out/blocks/<doc>.jsonl（阶段二清洗产物）
输出：out/chunks/<doc>.jsonl、out/chunks/_index.json

修复（2026-10-19，溯源对齐 知识图谱/schema/id_conventions.md）：
  * 逐句挂 source_block_ids：任何出现在正文 chunk 里的句子都登记其来源 block_id、
    页码、原文句号；overlap 尾句同样登记 → 章节/表格/公式边界不重算块号。
  * 跨页合并段保留页面范围 pages=[p1, p2]，而不是只记合并起始页。
  * 表格 chunk 标注 table_truncated：CSV 展开超 900 字符时截断，仅供召回，
    整表以 csv 路径为准，chunk 文本不算完整表。
  * 公式 / 图 / 表 chunk 同样带 source_block_ids。

每块的字段：
  chunk_id, doc_id, type(text|table|figure|equation), section, page, pages, printed_page,
  n_chars, text, source_block_ids, source_pages,
  (表格另有 csv / table_truncated / n_rows_csv / n_rows_kept / evidence / ocr_status)
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BASE = pathlib.Path(__file__).resolve().parents[2]
OUT = BASE / "02_清洗" / "out"
BLOCKS = OUT / "blocks"
CHUNKS = OUT / "chunks"
REPORT = OUT / "report"

SIZE, OVERLAP = 600, 80


def split_sentences(t: str) -> list[str]:
    parts = re.split(r"(?<=[。！？；])\s*|(?<=[.!?;])(?=\s(?:[A-Z0-9(（\[]|$))\s*", t)
    return [p.strip() for p in parts if p.strip()]


def block_id_of(b: dict, doc_id: str) -> str:
    """块位置哈希：sha1(doc_id|page|bbox_ints|type|part)[:16]，与 id_conventions §2 一致。"""
    bb = ",".join(str(round(float(x))) for x in (b.get("bbox") or []))
    raw = f"{doc_id}|{b.get('page')}|{bb}|{b.get('type')}|{b.get('part', 0)}"
    return "blk:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def make_chunks(blocks: list[dict], doc_id: str) -> list[dict]:
    # 句级溯源：每句记 (block_id, 页范围tuple, 原句)；跨页合并段整段共享页范围
    chunks, cur, cur_section = [], [], ""
    cur_items: list[tuple[str, tuple[int, ...], str]] = []

    def flush(keep_overlap=False):
        nonlocal cur, cur_items
        if not cur:
            cur_items = []
            return
        txt = " ".join(cur).strip()
        if txt:
            pages = sorted({p for _, ps, _ in cur_items for p in ps})
            chunks.append({
                "doc_id": doc_id, "type": "text",
                "section": cur_section,
                "page": pages[0],
                "pages": pages,
                "printed_page": None,
                "n_chars": len(txt), "text": txt,
                "source_block_ids": sorted({bid for bid, _, _ in cur_items}),
                "source_pages": pages,
            })
        if not keep_overlap:
            cur, cur_items = [], []
            return
        # 80 字符重叠：从尾部回取整句（每句都带溯源）
        tail, tail_items, acc = [], [], 0
        for s, it in zip(reversed(cur), reversed(cur_items)):
            tail.insert(0, s)
            tail_items.insert(0, it)
            acc += len(s) + 1
            if acc >= OVERLAP:
                break
        if acc < SIZE:
            cur, cur_items = tail, tail_items
        else:
            cur, cur_items = [], []

    for b in blocks:
        t = b.get("type")
        bid = b.get("block_id") or block_id_of(b, doc_id)
        page = b.get("page")
        if t == "heading":
            flush()
            cur_section = b.get("section") or b.get("text", "")
            continue
        if t == "text":
            section = b.get("section") or ""
            if section != cur_section:
                flush()
                cur_section = section
            sents = split_sentences(b.get("text") or "")
            for s in sents:
                if sum(len(x) + 1 for x in cur) + len(s) > SIZE and cur:
                    flush(keep_overlap=True)
                cur.append(s)
                cur_items.append((bid, tuple(b.get("pages") or [page]), s))
        elif t == "equation":
            flush()
            body = (b.get("text") or "").strip()
            if body:
                chunks.append({"doc_id": doc_id, "type": "equation",
                               "section": b.get("section") or cur_section,
                               "page": page, "pages": [page],
                               "printed_page": b.get("printed_page"),
                               "n_chars": len(body), "text": body,
                               "source_block_ids": [bid],
                               "source_pages": [page],
                               "tag": b.get("tag"),
                               "raw_latex": (b.get("raw_latex") or "")[:400]})
        elif t == "table":
            flush()
            body, n_rows_csv, truncated = "", 0, False
            csv_rel = b.get("csv")
            if csv_rel:
                cf = OUT / csv_rel.replace("\\", "/")
                if cf.exists():
                    raw_csv = cf.read_text(encoding="utf-8-sig")
                    n_rows_csv = sum(1 for ln in raw_csv.splitlines() if ln.strip())
                    body = raw_csv.replace("\n", " | ")
                    if len(body) > 900:
                        truncated = True
                        body = body[:900]
            txt = (b.get("caption") or "") + ("\n" + body if body else "")
            chunks.append({"doc_id": doc_id, "type": "table",
                           "section": b.get("section") or cur_section,
                           "page": page, "pages": [page],
                           "printed_page": b.get("printed_page"),
                           "n_chars": len(txt), "text": txt[:1500],
                           "source_block_ids": [bid],
                           "source_pages": [page],
                           "csv": b.get("csv"),
                           "table_truncated": truncated,
                           "n_rows_csv": n_rows_csv,
                           "n_rows_kept": n_rows_csv if not truncated else None,
                           "evidence": b.get("evidence"),
                           "ocr_status": b.get("ocr_status"),
                           "table_class": b.get("class")})
        elif t in ("image", "chart"):
            flush()
            cap = b.get("caption") or ""
            if len(cap) >= 8:           # 只挡掉 "(a)" 之类碎片
                chunks.append({"doc_id": doc_id, "type": "figure",
                               "section": b.get("section") or cur_section,
                               "page": page, "pages": [page],
                               "printed_page": b.get("printed_page"),
                               "n_chars": len(cap), "text": cap,
                               "source_block_ids": [bid],
                               "source_pages": [page]})
    flush()
    for i, c in enumerate(chunks):
        c["chunk_id"] = f"{doc_id[:40]}#{i:04d}"
    return chunks


def main() -> None:
    CHUNKS.mkdir(parents=True, exist_ok=True)
    rows = []
    total = Counter()
    for f in sorted(BLOCKS.glob("*.jsonl")):
        doc_id = f.stem
        blocks = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        chunks = make_chunks(blocks, doc_id)
        (CHUNKS / f"{doc_id}.jsonl").write_text(
            "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding="utf-8")
        kinds = Counter(c["type"] for c in chunks)
        lens = [c["n_chars"] for c in chunks if c["type"] == "text"]
        n_src = sum(1 for c in chunks if c.get("source_block_ids"))
        rows.append({"doc_id": doc_id, "chunks": len(chunks), "text": kinds["text"],
                     "table": kinds["table"], "figure": kinds["figure"],
                     "equation": kinds["equation"],
                     "avg_text_len": round(sum(lens) / len(lens), 1) if lens else 0,
                     "max_text_len": max(lens) if lens else 0,
                     "with_source": n_src, "src_cov": round(n_src / len(chunks), 4) if chunks else 0})
        for k, v in kinds.items():
            total[k] += v
        total["all"] += len(chunks)
        total["with_source"] += n_src
        total["table_truncated"] += sum(
            1 for c in chunks if c.get("type") == "table" and c.get("table_truncated"))

    print(f"篇数 {len(rows)}")
    print(f"  chunk 总数 {total['all']}（正文 {total['text']} / 表 {total['table']} / "
          f"图 {total['figure']} / 公式 {total['equation']}）")
    print(f"  带溯源 source_block_ids 的 chunk {total['with_source']}"
          f"（覆盖率 {total['with_source']/max(total['all'],1)*100:.2f}%）")
    print(f"  表格截断（仅召回，整表以 csv 为准） {total['table_truncated']} 张")
    avg = [r["avg_text_len"] for r in rows if r["avg_text_len"]]
    print(f"  正文 chunk 平均长度 {sum(avg)/len(avg):.1f} 字符；最大 {max(r['max_text_len'] for r in rows)}")
    print(f"  超过 600 字符的 chunk 所在篇数 "
          f"{sum(1 for r in rows if r['max_text_len'] > 600)} 篇")
    (REPORT / "chunks_summary.json").write_text(
        json.dumps({"totals": dict(total), "docs": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("\n已写", REPORT / "chunks_summary.json")


if __name__ == "__main__":
    main()
