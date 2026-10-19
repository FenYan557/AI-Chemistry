# -*- coding: utf-8 -*-
"""源材料缺陷总账：对 48 篇 MinerU 原始输出做 25 类缺陷的确定性扫描。
只看 SRC（知识图谱所需文献\文献提取），不读清洗产物。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

SRC = pathlib.Path(__file__).resolve().parents[3] / "知识图谱所需文献" / "文献提取"
OUT = pathlib.Path(__file__).resolve().parents[1] / "out" / "report"

NUM = re.compile(r"^[-−–]?\d+(\.\d+)?$")
# 缺陷签名
SIG = {
    "上标丢失_×10n": re.compile(r"×\s*10\s*\d(?!\d)"),
    "上标丢失_单位幂": re.compile(r"(?<![A-Za-z])(cm|mm|nm|dm|m|s|g|L|mol)\s*[-–]?\s*[23](?![A-Za-z0-9])"),
    "上标丢失_R方": re.compile(r"\bR\s*2\s*[=＝]"),
    "数字内空格": re.compile(r"\d\.\s+\d|\d\s+\.\d"),
    "千分位逗号": re.compile(r"(?<![\[\d,])\d{1,3},\d{3}(?:\.\d+)?(?![\d\]])"),
    "下标0疑似": re.compile(r"[_]\{?\s*0\s*\}?|\\_\{\s*0\s*\}"),
    "残留下划线": re.compile(r"[A-Za-z]_[A-Za-z0-9{]"),
    "残留LaTeX": re.compile(r"\$|\\[a-zA-Z]{2,}|\^\{|_\{"),
    "花括号残留": re.compile(r"[{}]"),
    "cid乱码": re.compile(r"\(cid:\d+\)"),
    "替换字符": re.compile(r"\ufffd"),
    "零宽字符": re.compile(r"[\u200b-\u200d\ufeff]"),
    "全角混排": re.compile(r"[０-９Ａ-Ｚａ-ｚ]"),
    "负号混用同篇": re.compile(r"[\u2212]"),
    "单位写法不规范": re.compile(r"(mg\s*[lL]\s*-1|mgL-1|g\s*[lL]-1|mol\s*[lL]-1|mA\s*cm-2|A\s*dm-2)"),
    "混合连字符": re.compile(r"(?<![A-Za-z])-(?=\d)"),
    "邮箱": re.compile(r"\S+@\S+\.\w+"),
    "DOI或URL": re.compile(r"(doi\.org|10\.\d{4,}/|https?://)", re.I),
    "页眉式重复串": re.compile(r"(Journal of|Vol\.\s*\d|ISSN|Available online)"),
    "连字符结尾": re.compile(r"[A-Za-z]-$"),
    "无终止符": re.compile(r"[^.。!?！？:：;；)\]]$"),
    "占位缺失值": re.compile(r"^[-−–—/]$"),
}


def doc_name(d: pathlib.Path) -> str:
    return d.name.split(".pdf-")[0] if ".pdf-" in d.name else d.name


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dirs = sorted(p for p in SRC.iterdir() if p.is_dir())
    hit_docs = defaultdict(set)
    cnt = Counter()
    samples = defaultdict(list)
    per_doc = []

    for d in dirs:
        cl = list(d.glob("*_content_list.json"))
        if not cl:
            continue
        raw = json.loads(cl[0].read_text(encoding="utf-8"))
        name = doc_name(d)
        rows = Counter()
        texts = [e for e in raw if e.get("type") == "text"]
        body_join = "\n".join(e.get("text", "") for e in texts)

        def note(key, sample=None):
            cnt[key] += 1
            hit_docs[key].add(name)
            rows[key] += 1
            if sample and len(samples[key]) < 3:
                samples[key].append(f"{name[:24]} p{sample[0]}: {sample[1][:90]}")

        for e in texts:
            t = e.get("text", "")
            for k, pat in SIG.items():
                m = pat.search(t)
                if m:
                    note(k, (e.get("page_idx", 0) + 1, t[max(0, m.start() - 30):m.start() + 40]))
        # 结构类
        for k in ("text", "image", "chart", "table", "equation"):
            cnt[f"块_{k}"] += sum(1 for e in raw if e.get("type") == k)

        # 重复块
        c = Counter(e.get("text", "").strip() for e in texts if len(e.get("text", "").strip()) > 20)
        dup = sum(v - 1 for v in c.values() if v > 1)
        if dup:
            cnt["重复正文块"] += dup
            hit_docs["重复正文块"].add(name)
            rows["重复正文块"] = dup

        # 页眉页脚反复出现（同文本跨≥3页）
        pg = defaultdict(set)
        for e in raw:
            if e.get("type") in ("header", "footer", "page_number"):
                pg[(e.get("text") or "").strip()].add(e.get("page_idx", 0))
        rep = sum(1 for k, v in pg.items() if len(v) >= 3 and k)
        cnt["重复页眉页脚条数"] += rep
        if rep:
            hit_docs["重复页眉页脚条数"].add(name)

        # 表格结构缺陷
        for e in raw:
            if e.get("type") != "table":
                continue
            body = e.get("table_body") or ""
            trs = re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S)
            widths = [len(re.findall(r"<td", tr)) for tr in trs]
            if not widths:
                note("表格_空表体", (e.get("page_idx", 0) + 1, ""))
                continue
            w = [x for x in widths if x]
            if len(set(w)) > 1:
                note("表格_原始行宽不齐", (e.get("page_idx", 0) + 1, f"widths={w[:8]}"))
            if max(w) == 1:
                note("表格_只有1列", (e.get("page_idx", 0) + 1, ""))
            if max(w) > 14:
                note("表格_列数异常多", (e.get("page_idx", 0) + 1, f"cols={max(w)}"))
            if not (e.get("table_caption") or []):
                note("表格_无题注", (e.get("page_idx", 0) + 1, ""))
            if re.search(r"rowspan|colspan", body):
                cnt["表格_含合并单元格"] += 1
                hit_docs["表格_含合并单元格"].add(name)
            if not any(NUM.match(re.sub(r"<[^>]+>", "", c).strip())
                       for c in re.findall(r"<td[^>]*>(.*?)</td>", body, re.S)):
                note("表格_无任何数值", (e.get("page_idx", 0) + 1, ""))
            if re.search(r"\$[^$]", body):
                cnt["表格_含LaTeX"] += 1
                hit_docs["表格_含LaTeX"].add(name)

        # 图题注
        for e in raw:
            if e.get("type") not in ("image", "chart"):
                continue
            caps = e.get("image_caption") or e.get("chart_caption") or []
            j = " ".join(caps).strip()
            if not j:
                cnt["图_无题注"] += 1
                hit_docs["图_无题注"].add(name)
            elif re.fullmatch(r"(\([a-zA-Z]\)\s*)+", j) or len(j) <= 8:
                cnt["图_题注仅子图标签"] += 1
                hit_docs["图_题注仅子图标签"].add(name)
            elif re.search(r"(Reprinted|Reproduced|Copyright|CC BY)", j, re.I):
                cnt["图_题注混版权声明"] += 1
                hit_docs["图_题注混版权声明"].add(name)

        # 公式
        for e in raw:
            if e.get("type") != "equation":
                continue
            t = (e.get("text") or e.get("latex") or "").strip()
            if not t:
                note("公式_空", (e.get("page_idx", 0) + 1, ""))
            elif t.count("{") != t.count("}"):
                note("公式_花括号不平衡", (e.get("page_idx", 0) + 1, t[:60]))
            elif re.fullmatch(r"\$\$[\s\S]*\$\$", t) and len(re.sub(r"[$\s\\]", "", t)) < 4:
                note("公式_只有编号", (e.get("page_idx", 0) + 1, t[:60]))

        # 中文论文碎行
        zh = sum(1 for t in texts if re.search(r"[\u4e00-\u9fff]", t.get("text", "")))
        if zh and zh / max(len(texts), 1) > 0.5:
            avg = sum(len(t.get("text", "")) for t in texts) / max(len(texts), 1)
            if avg < 40:
                note("中文_碎行", (0, f"avg_len={avg:.0f}, blocks={len(texts)}"))

        # 单篇缺陷总数
        per_doc.append({"doc": name[:46], "defects": sum(rows.values()),
                        "distinct": len(rows), "top": dict(rows.most_common(4))})

    # 输出
    print("=== 缺陷类别 × 出现总次数 × 影响篇数 ===")
    for k in SIG:
        if hit_docs[k]:
            print(f"  {k:<18} 次数 {cnt[k]:>5}  篇数 {len(hit_docs[k]):>2}/48")
    print("\n=== 表格 / 图 / 公式 结构缺陷 ===")
    for k, v in cnt.items():
        if k.startswith(("表格_", "图_", "公式_", "块_")):
            print(f"  {k:<18} {v:>5}  篇数 {len(hit_docs[k]):>2}/48")
    print("\n=== 样例 ===")
    for k, ss in samples.items():
        if ss:
            print(f"  [{k}]")
            for s in ss[:2]:
                print(f"    {s}")
    print("\n=== 缺陷最集中的 8 篇 ===")
    for r in sorted(per_doc, key=lambda x: -x["defects"])[:8]:
        print(f"  {r['doc']:<48} 缺陷 {r['defects']:>5} ({r['distinct']} 类) {list(r['top'])[:3]}")

    rec = {"counts": dict(cnt), "docs_affected": {k: len(v) for k, v in hit_docs.items()},
           "samples": {k: v for k, v in samples.items()}, "per_doc": per_doc}
    (OUT / "defect_inventory.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    print("\n已写", OUT / "defect_inventory.json")


if __name__ == "__main__":
    main()
