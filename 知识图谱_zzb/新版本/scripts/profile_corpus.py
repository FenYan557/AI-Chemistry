"""只读范围普查；只生成范围与检索线索，不声称精读、语义覆盖或抽取准确率。"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
DEFAULT_CORPUS = REPO / "清洗/02_清洗/out"
TERMS = {
    "electrodeposition": r"electrodeposit|electroplat|电镀|电沉积",
    "electroless": r"electroless|化学镀|无电镀",
    "cmp": r"chemical mechanical polish|\bCMP\b|化学机械抛光",
    "thermal_treatment": r"anneal|热处理|退火",
    "simulation": r"molecular dynamics|density functional|\bDFT\b|模拟|计算",
    "review": r"\breview\b|综述",
    "catalysis": r"catalys|催化",
}

def profile(corpus):
    documents = []
    for path in sorted((corpus / "blocks").glob("*.jsonl")):
        raw = path.read_bytes()
        blocks = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
        meta_path = path.with_suffix(".meta.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig")) if meta_path.exists() else {}
        text_blocks = [b for b in blocks if b.get("type") == "text" and b.get("text")]
        title = str(meta.get("title") or path.stem)
        # 只取少量文本线索；不将全文交给模型。
        preview = "\n".join(str(b["text"]) for b in text_blocks[:2] + text_blocks[-2:])[:4000]
        hit = [label for label, regex in TERMS.items() if re.search(regex, title + "\n" + preview, re.I)]
        documents.append({
            "document_id": path.stem, "title": title, "doi": meta.get("doi"),
            "source_file": path.relative_to(corpus).as_posix(),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "block_count": len(blocks), "text_block_count": len(text_blocks),
            "table_block_count": sum(b.get("type") == "table" for b in blocks),
            "topic_hints": hit, "manual_scope_review": "pending",
            "scope_note": "包含催化等周边研究，不能把48篇一概当作电镀实验；检索命中不是内容标签金标。",
        })
    if not documents:
        raise ValueError("未找到 blocks/*.jsonl，拒绝生成空普查成功报告")
    return {
        "method": "local_metadata_and_keyword_screening",
        "not_full_text_semantic_review": True,
        "expected_documents_from_prior_work": 48, "actual_documents": len(documents),
        "snapshot_matches_expected_count": len(documents) == 48,
        "topic_hints_are_nonexclusive_and_unvalidated": True,
        "documents": documents,
    }

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    p.add_argument("--output", type=Path, default=ROOT / "data/corpus_manifest.json")
    args = p.parse_args()
    result = profile(args.corpus.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "documents"}, ensure_ascii=False))
