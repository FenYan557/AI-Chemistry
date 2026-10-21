# -*- coding: utf-8 -*-
"""阶段03 辅助：取出某篇文献全部 span 的 PubChem 候选，紧凑打印。

用法（仓库根目录）：
    python -X utf8 清洗/03_化学物质抽取消歧/scripts/candidates_for_doc.py <doc_id>

只输出该篇涉及的 span，避免把整个 candidates.jsonl 读进上下文。
每个候选 CID 的同义词截断到前 3 个、单个同义词截断到 60 字符。
"""
import json
import sys
from pathlib import Path

STAGE = Path(__file__).resolve().parents[1]
EXTRACT_DIR = STAGE / "out" / "extraction"
CAND_PATH = STAGE / "out" / "pubchem" / "candidates.jsonl"


def main():
    if len(sys.argv) < 2:
        print("用法: candidates_for_doc.py <doc_id>", file=sys.stderr)
        return 1
    doc_id = sys.argv[1]
    ep = EXTRACT_DIR / f"{doc_id}.json"
    if not ep.is_file():
        print(f"未找到 {ep}", file=sys.stderr)
        return 1
    spans = []
    seen = set()
    for r in json.loads(ep.read_text(encoding="utf-8")):
        s = (r.get("span") or "").strip()
        if s and s not in seen:
            seen.add(s)
            spans.append(s)
    if not CAND_PATH.is_file():
        print("candidates.jsonl 不存在，请先跑 pubchem_lookup.py",
              file=sys.stderr)
        return 1
    by_span = {}
    with CAND_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            by_span[e["span"]] = e
    missing = 0
    for s in spans:
        e = by_span.get(s)
        if e is None:
            print(f"SPAN {s} | 未检索（请跑 pubchem_lookup.py）")
            missing += 1
            continue
        cand = "; ".join(
            f"{c['cid']}:" + "/".join(x[:60] for x in c["synonyms"][:3])
            for c in e["candidates"]
        )
        extra = ""
        if e.get("query_term") != s:
            extra += f" query={e['query_term']}"
        if e.get("spec_code"):
            extra += f" spec={e['spec_code']}"
        print(f"SPAN {s} | {e['status']}{extra} | {cand or '-'}")
    print(f"# spans={len(spans)} 未检索={missing}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
