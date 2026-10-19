"""发布结构验收与数值一致性诊断（标准库，无需 OCR/PDF 依赖）。"""
from __future__ import annotations

import csv
import hashlib
import html
import json
from pathlib import Path
import re
import statistics
import sys
import unicodedata
from collections import Counter
from decimal import Decimal

BASE = Path(__file__).resolve().parents[2]
REPO = BASE.parent
OUT = BASE / "02_清洗/out"
NUM = re.compile(r"[-+−–]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+−]?\d+)?")


def records(path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]


def numeric_tokens(text):
    """保留符号/科学计数法/出现次数；_0.7 与 _ 0.7 按同一规则识别。"""
    counts = Counter()
    for match in NUM.finditer(unicodedata.normalize("NFKC", html.unescape(text))):
        value = Decimal(match.group().replace("−", "-").replace("–", "-").replace(",", ""))
        counts[str(value.normalize()) if value else "0"] += 1
    return counts


def before_text(b):
    parts = []
    if b.get("type") in ("text", "equation"):
        parts.append(b.get("text") or "")
    if b.get("type") == "table":
        parts.extend(b.get("table_caption") or [])
        parts.extend(b.get("table_footnote") or [])
        parts.append(html.unescape(re.sub(r"<[^>]*>", " ", b.get("table_body") or "")))
    if b.get("type") in ("image", "chart"):
        parts.extend(b.get("image_caption") or b.get("chart_caption") or [])
        parts.extend(b.get("image_footnote") or b.get("chart_footnote") or [])
    return " ".join(parts)


def after_text(b):
    parts = [str(b.get(k) or "") for k in ("text", "caption", "caption_extra")]
    if b.get("csv"):
        path = OUT / b["csv"].replace("\\", "/")
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8-sig"))
    return " ".join(parts)


def evaluate():
    index = json.loads((BASE / "inputs/documents_index.json").read_text(encoding="utf-8"))
    expected = {r["doc_id"] for r in index}
    blocks = {p.stem: records(p) for p in (OUT / "blocks").glob("*.jsonl")}
    chunks = {p.stem: records(p) for p in (OUT / "chunks").glob("*.jsonl")}
    errors, differences, truncated = [], [], []
    types, evidence, ocr = Counter(), Counter(), Counter()
    raw_count = repaired_count = image_count = reference_count = 0
    source_missing = source_empty = cross = terminal = section = ntext = 0
    nbase = nhit = ubase = uhit = 0
    if set(blocks) != expected or set(chunks) != expected or not expected:
        errors.append("document sets do not match nonempty input index")
    for r in index:
        did = r["doc_id"]
        raw_path = REPO / r["content_list"]
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        repaired = json.loads((BASE / r["repaired"]).read_text(encoding="utf-8"))
        raw_count += len(raw)
        repaired_count += len(repaired)
        if len(raw) != len(repaired):
            errors.append(f"{did}: stage-one block count changed")
        if hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest() != r["content_list_json_sha256"]:
            errors.append(f"{did}: original input hash mismatch")
        for pdf in r["pdfs"]:
            if not (REPO / pdf).is_file():
                errors.append(f"{did}: missing PDF")
        rows = blocks.get(did, [])
        by_id = {b.get("block_id"): b for b in rows}
        if len(by_id) != len(rows) or None in by_id:
            errors.append(f"{did}: duplicate or missing block_id")
        meta = json.loads((OUT / "blocks" / f"{did}.meta.json").read_text(encoding="utf-8"))
        reference_count += len(meta.get("references", []))
        for b in rows:
            kind = b.get("type")
            types[kind] += 1
            if kind not in {"text", "heading", "image", "chart", "table", "equation"}:
                errors.append(f"{did}: illegal block type")
            if not b.get("page") or len(b.get("bbox") or []) != 4:
                errors.append(f"{did}: missing page or bbox")
            if kind == "text":
                text = (b.get("text") or "").strip()
                ntext += 1
                terminal += bool(re.search(r"[.。!?！？:：;；)\]”\"']$", text))
                section += bool(b.get("section"))
                if not text:
                    errors.append(f"{did}: empty text")
            if kind == "table":
                path = OUT / str(b.get("csv") or "").replace("\\", "/")
                evidence[str(b.get("evidence"))] += 1
                ocr[str(b.get("ocr_status"))] += 1
                if not path.is_file():
                    errors.append(f"{did}: missing CSV")
                else:
                    with path.open(encoding="utf-8-sig", newline="") as f:
                        matrix = list(csv.reader(f))
                    if not matrix or any(len(row) != len(matrix[0]) for row in matrix):
                        errors.append(f"{did}: empty or ragged CSV")
            if b.get("img"):
                image_count += 1
                if not (REPO / r["source_dir"] / b["img"].replace("\\", "/")).is_file():
                    errors.append(f"{did}: missing image {b['img']}")
        for c in chunks.get(did, []):
            ids = c.get("source_block_ids") or []
            source_empty += not bool(ids)
            source_missing += sum(ident not in by_id for ident in ids)
            sections = {by_id[ident].get("section") for ident in ids if ident in by_id}
            cross += len(sections) > 1
            if c.get("table_truncated"):
                truncated.append({"doc_id": did, "csv": c.get("csv")})
        before = numeric_tokens(" ".join(before_text(b) for b in repaired))
        after = numeric_tokens(" ".join(after_text(b) for b in rows))
        nbase += sum(before.values())
        nhit += sum((before & after).values())
        ubase += len(before)
        uhit += len(set(before) & set(after))
        missing = before - after
        if missing:
            examples = []
            for b in repaired:
                text = before_text(b)
                absent = set(numeric_tokens(text)) & set(missing)
                if absent and len(examples) < 5:
                    examples.append({"page": (b.get("page_idx") or 0) + 1, "type": b.get("type"),
                                     "values": sorted(absent), "text": text[:700]})
            differences.append({"doc_id": did, "missing_occurrences": sum(missing.values()),
                                "missing_values": dict(missing), "examples": examples})
    if source_missing or source_empty or cross:
        errors.append("chunk provenance is unresolved or crosses sections")
    deletions = records(OUT / "report/deletions.jsonl")
    if any(not d.get("doc") or not d.get("rule") for d in deletions):
        errors.append("deletion log lacks document or rule")
    all_chunks = [c for rows in chunks.values() for c in rows]
    lens = [len(c.get("text") or "") for c in all_chunks if c.get("type") == "text"]
    summary = {
        "status": "structural_checks_passed" if not errors else "failed",
        "scope": "stage-one to stage-two consistency; not PDF accuracy or losslessness",
        "documents": len(expected), "raw_blocks": raw_count, "repaired_blocks": repaired_count,
        "blocks": sum(map(len, blocks.values())), "chunks": len(all_chunks), "types": dict(types),
        "table_csvs": types["table"], "image_references_resolved": image_count,
        "structured_references": reference_count, "deletion_records": len(deletions),
        "chunk_source_missing": source_missing, "chunk_source_empty": source_empty,
        "cross_section_chunks": cross, "truncated_tables": truncated,
        "text_terminal_rate": round(terminal / max(ntext, 1), 6),
        "text_section_rate": round(section / max(ntext, 1), 6),
        "text_chunk_mean_chars": round(statistics.mean(lens), 2) if lens else None,
        "chunks_over_900_chars": sum(len(c.get("text") or "") > 900 for c in all_chunks),
        "table_evidence": dict(evidence), "table_ocr_status": dict(ocr),
        "numeric_diagnostic": {
            "method": "per-document signed decimal tokens; full captions and CSV; multiset intersection",
            "baseline_occurrences": nbase, "matched_occurrences": nhit,
            "occurrence_recall": round(nhit / max(nbase, 1), 6),
            "baseline_distinct_per_doc": ubase, "matched_distinct_per_doc": uhit,
            "distinct_recall": round(uhit / max(ubase, 1), 6),
            "documents_with_occurrence_differences": len(differences),
            "caveat": "Includes citations, formula subscripts and removed author data; not experimental-data loss rate.",
        },
        "known_limitations": [
            "Sentence-terminal target 95% is not met; punctuation is a heuristic.",
            "PDF semantic/numeric correctness has not been fully manually reviewed.",
            "Truncated table chunks are recall previews; full CSV must be read.",
            "Historical retention.json measures stage one against PDF text, not stage two.",
            "Deletion log exists; correctness/completeness of every deletion is not established.",
        ],
        "errors": errors,
    }
    return summary, differences


def main():
    summary, differences = evaluate()
    report = OUT / "report"
    for name, data in (("release_validation.json", summary), ("numeric_differences.json", differences)):
        (report / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    provenance = {k: summary[k] for k in ("documents", "blocks", "chunks")}
    provenance.update({"source_resolvable": summary["chunks"] if not summary["chunk_source_empty"] and not summary["chunk_source_missing"] else None,
                       "cross_section": summary["cross_section_chunks"],
                       "source_mapping_coverage": 1.0 if not summary["chunk_source_empty"] and not summary["chunk_source_missing"] else None})
    (report / "rag_provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
