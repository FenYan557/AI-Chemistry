# -*- coding: utf-8 -*-
"""阶段03 辅助：把某篇文献的抽取单元渲染成紧凑文本，便于 LLM 通读全文。

用法（仓库根目录）：
    python -X utf8 清洗/03_化学物质抽取消歧/scripts/dump_units.py <doc_id>

只做展示裁剪（去掉单元头里冗余的 section="..."），不改动原始输入文件。
"""
import json
import re
import sys
from pathlib import Path

STAGE = Path(__file__).resolve().parents[1]
INPUT_DIR = STAGE / "out" / "extraction_input"
SECTION_RE = re.compile(r'\s+section="[^"]*"')


def main():
    if len(sys.argv) < 2:
        print("用法: dump_units.py <doc_id>", file=sys.stderr)
        return 1
    doc_id = sys.argv[1]
    path = INPUT_DIR / f"{doc_id}.jsonl"
    if not path.is_file():
        print(f"未找到 {path}", file=sys.stderr)
        return 1
    total = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            u = json.loads(line)
            text = u.get("text", "")
            text = SECTION_RE.sub("", text)
            total += len(text)
            print(f"### {u['unit_id']} | {u.get('source_type')}")
            print(text)
    print(f"\n# units_total_chars={total}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
