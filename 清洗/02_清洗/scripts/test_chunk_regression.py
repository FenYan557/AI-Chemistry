# -*- coding: utf-8 -*-
"""chunk.py 回归测试：章节不串入 + 来源可回查（2026-10-19 溯源修复）。

不读写磁盘产物，直接调用 make_chunks 构造输入验证：
  T1 章节边界：heading 触发 flush，chunk 不携带下一章节正文句；
  T2 跨页合并段：pages 保留页面范围，不只起始页；
  T3 overlap 溯源：上一 chunk 的尾句在下一 chunk 重现时，来源 block_id 一致；
  T4 表格截断：>900 字符 CSV 标记 table_truncated 且 n_rows_kept=None；
  T5 公式/图 chunk 也带 source_block_ids；
  T6 全部 chunk 100% 有非空 source_block_ids。
"""
from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")

SPEC = importlib.util.spec_from_file_location(
    "chunk", pathlib.Path(__file__).parent / "chunk.py")
chunk = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chunk)

DOC = "testdoc"


def bid(page, bbox, ty, part=0):
    bb = ",".join(str(x) for x in bbox)
    return "blk:" + hashlib.sha1(f"{DOC}|{page}|{bb}|{ty}|{part}".encode()).hexdigest()[:16]


def sent(n):
    """约 90 字符、单句号的英文句，避免双句号干扰分句。"""
    return "Sentence number %d has enough words to make it reasonably long for splitting." % n


def run(name, blocks):
    chunks = chunk.make_chunks(blocks, DOC)
    print(f"-- {name}: {len(chunks)} chunks")
    for c in chunks:
        print(f"   [{c['chunk_id'][-4:]}] {c['type']:8s} pages={c.get('pages')} "
              f"src={len(c.get('source_block_ids') or [])} chars={c['n_chars']}")
    return chunks


def expect(cond, msg):
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"ok: {msg}")


# ---- 构造：5 句同块（足以触发 600 切分 + overlap）+ heading + 下节 1 句 ----
b1 = {"type": "text", "page": 3, "bbox": [10, 20, 500, 40],
      "text": " ".join(sent(i) for i in range(1, 16)),
      "section": "Sec A", "part": 0}
b1["block_id"] = bid(3, b1["bbox"], "text")
b2 = {"type": "text", "page": 3, "bbox": [10, 50, 500, 60],
      "text": sent(99), "section": "Sec B", "part": 0}
b2["block_id"] = bid(3, b2["bbox"], "text")
blocks = [b1, {"type": "heading", "page": 3, "bbox": [10, 45, 500, 49],
               "text": "Sec B", "section": "Sec B"}, b2]
chunks = run("章节边界+重叠", blocks)

texts = [c for c in chunks if c["type"] == "text"]
expect(len(texts) >= 2, "600 字符切分产生多个正文 chunk")
s99 = sent(99)
expect(any(s99 in c["text"] for c in texts), "下节句子出现在某 chunk")
holder = [c for c in texts if s99 in c["text"]][0]
expect(holder["section"] == "Sec B", "T1 章节不串入：含下节句子的 chunk section=Sec B")
expect(holder["source_block_ids"] == [b2["block_id"]], "章节B不得带入章节A来源")
expect(all(sent(i) not in holder["text"] for i in range(1, 16)), "章节B不得带入章节A尾句")
first = [c for c in texts if s99 not in c["text"]]
expect(all("Sentence number 99" not in c["text"] for c in first),
       "T1 其余 chunk 不含下节句子")

# T3 overlap 溯源：相邻 chunk 若共享同一非下节句子，来源 block 必须一致
joined = [c for c in texts]
overlap_found = False
for a, b in zip(joined, joined[1:]):
    if a["section"] != b["section"]:
        continue
    common = [s for s in chunk.split_sentences(b1["text"]) if s in a["text"] and s in b["text"]]
    if common:
        overlap_found = True
        expect(b1["block_id"] in a["source_block_ids"] and b1["block_id"] in b["source_block_ids"],
               "T3 overlap 句（来自 b1）在两侧 chunk 均可溯源到 b1")
expect(overlap_found, "T3 存在 ≥80 字符重叠的相邻 chunk")
expect(all(c["source_block_ids"] and c["source_pages"] for c in chunks), "T6 全部 chunk 有溯源")

# ---- 跨页合并段：page 4 与 5 合并（block 页=4，pages 应含 4、5）----
bx = {"type": "text", "page": 4, "pages": [4, 5],
      "bbox": [10, 20, 500, 40],
      "text": sent(1) + " " + sent(2),
      "section": "Sec A", "part": 0}
bx["block_id"] = bid(4, bx["bbox"], "text")
chunks2 = run("跨页合并段", [bx])
expect(chunks2[0]["pages"] == [4, 5], "T2 跨页段 pages=[4,5]")
expect(chunks2[0]["page"] == 4, "T2 page 取范围首页")

# ---- 表格截断：CSV 超长 ----
out_csv = chunk.OUT / "tables" / "__test__long.csv"
long_rows = "\n".join(",".join([f"v{r}c{c}" for c in range(12)]) for r in range(80))
out_csv.parent.mkdir(parents=True, exist_ok=True)
out_csv.write_text("h1,h2\n" + long_rows, encoding="utf-8-sig")
tb = {"type": "table", "page": 7, "bbox": [10, 20, 500, 400],
      "caption": "Table 9. Test.", "csv": "tables\\__test__long.csv",
      "section": "Sec A", "class": "result", "part": 0}
tb["block_id"] = bid(7, tb["bbox"], "table")
chunks3 = run("表格截断", [tb])
tc = chunks3[0]
expect(tc["table_truncated"] is True, "T4 长 CSV 标记 table_truncated=True")
expect(tc["n_rows_kept"] is None and tc["n_rows_csv"] == 81, "T4 截断时不报保留行数，只报 csv 总行数")
expect(tc["source_block_ids"] == [tb["block_id"]], "T4 表格 chunk 溯源到表块")
out_csv.unlink()

# ---- 公式 / 图 ----
eq = {"type": "equation", "page": 8, "bbox": [10, 20, 500, 30],
      "text": "j = nFD", "tag": "3", "section": "Sec A"}
eq["block_id"] = bid(8, eq["bbox"], "equation")
fig = {"type": "image", "page": 8, "bbox": [10, 40, 300, 300],
       "caption": "Fig. 3. Polarization curves of the test coupon.", "section": "Sec A"}
fig["block_id"] = bid(8, fig["bbox"], "image")
chunks4 = run("公式+图", [eq, fig])
expect(all(c["source_block_ids"] for c in chunks4), "T5 公式/图 chunk 带溯源")

print("\nALL TESTS PASSED")
