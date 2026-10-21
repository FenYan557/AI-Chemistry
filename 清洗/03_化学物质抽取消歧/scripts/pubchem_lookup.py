# -*- coding: utf-8 -*-
"""阶段03 步骤3：span -> PubChem 候选（PUG REST，带本地缓存）。

输入：out/extraction/ 下各文献的抽取结果 JSON（数组，含 span 字段）。
对全部唯一 span 逐一查询，候选写入 out/pubchem/candidates.jsonl；
缓存 out/pubchem/cache.json，中断后重跑自动续查。

策略（按参考稿）：
  1. 分子量规格代号（PEG-6000、PVP-10000 等）剥掉规格后缀查通式，
     并标记 spec_code，不硬匹配具体 CID。
  2. 先按 name 查 CID；查不到再查 synonyms。
  3. 每个 span 最多保留 5 个候选，每个候选带 CID + 前 5 个同义词。
  4. 全部失败标 no_candidate，交消歧阶段判 unmatched_new。

限速：请求间隔 0.25s。仅依赖标准库。在仓库根目录运行：
    python -X utf8 清洗/03_化学物质抽取消歧/scripts/pubchem_lookup.py
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

STAGE = Path(__file__).resolve().parents[1]
EXTRACT_DIR = STAGE / "out" / "extraction"
OUT_DIR = STAGE / "out" / "pubchem"
CACHE_PATH = OUT_DIR / "cache.json"
PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
MAX_CANDIDATES = 5
MAX_SYNONYMS = 5
SLEEP = 0.25

SPEC_CODE = re.compile(
    r"^(PEG|PPG|PEO|PVP|PVA|Tween|Triton|CTAB|SPS|MPS|PEGME)[- ]?(\d{3,6})$",
    re.IGNORECASE,
)

# 连续网络失败计数：超过阈值即报错退出，防止"全部 no_candidate"的静默假结果
NET_ERRORS = {"count": 0}
MAX_CONSECUTIVE_NET_ERRORS = 10


def pug_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "kg-extract/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            NET_ERRORS["count"] = 0
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # PubChem 对"查无此物"返回 404，属正常结果，不算网络错误
            NET_ERRORS["count"] = 0
        else:
            NET_ERRORS["count"] += 1
        return None
    except Exception:
        NET_ERRORS["count"] += 1
        return None


def clean_formula(span):
    """清洗 MinerU 式下标噪声：'Hg _2 SO _4' -> 'Hg2SO4'。

    仅当 span 含 '_' 下标标记时启用；普通多词名称（boric acid）不动。
    """
    if "_" not in span:
        return span
    return re.sub(r"\s+", "", span.replace("_", ""))


def cids_for(term):
    enc = urllib.parse.quote(term, safe="")
    data = pug_get(f"{PUG}/compound/name/{enc}/cids/JSON")
    if data and "IdentifierList" in data:
        return data["IdentifierList"].get("CID", [])
    data = pug_get(f"{PUG}/compound/name/{enc}/synonyms/JSON")
    if data and "InformationList" in data:
        out = []
        for info in data["InformationList"].get("Information", []):
            if "CID" in info:
                out.append(info["CID"])
        return out
    return []


def synonyms_for(cid):
    data = pug_get(f"{PUG}/compound/cid/{cid}/synonyms/JSON")
    if data and "InformationList" in data:
        infos = data["InformationList"].get("Information", [])
        if infos:
            return infos[0].get("Synonym", [])[:MAX_SYNONYMS]
    return []


def lookup(span, cache):
    if span in cache:
        return cache[span]
    entry = {"span": span, "query_term": span, "spec_code": "",
             "candidates": [], "status": "no_candidate"}
    term = span
    cleaned = clean_formula(span.strip())
    if cleaned != span.strip():
        entry["query_term"] = cleaned
        term = cleaned
    m = SPEC_CODE.match(term)
    if m:
        term = m.group(1).upper()
        entry["query_term"] = term
        entry["spec_code"] = m.group(2)
    cids = cids_for(term)
    time.sleep(SLEEP)
    for cid in cids[:MAX_CANDIDATES]:
        entry["candidates"].append({"cid": cid, "synonyms": synonyms_for(cid)})
        time.sleep(SLEEP)
    if entry["candidates"]:
        entry["status"] = "has_candidates"
    cache[span] = entry
    return entry


def main():
    if not EXTRACT_DIR.is_dir():
        print(f"未找到 {EXTRACT_DIR}，请先完成步骤2（抽取）。", file=sys.stderr)
        return 1
    spans = []
    seen = set()
    for path in sorted(EXTRACT_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            for item in json.load(f):
                s = (item.get("span") or "").strip()
                if s and s not in seen:
                    seen.add(s)
                    spans.append(s)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = {}
    if CACHE_PATH.is_file():
        with CACHE_PATH.open("r", encoding="utf-8") as f:
            cache = json.load(f)
    done = 0
    out_path = OUT_DIR / "candidates.jsonl"
    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        for s in spans:
            entry = lookup(s, cache)
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")
            done += 1
            if NET_ERRORS["count"] >= MAX_CONSECUTIVE_NET_ERRORS:
                with CACHE_PATH.open("w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False)
                print("连续网络请求失败，疑似网络被拦截。"
                      "已保存缓存，请检查网络后重跑。", file=sys.stderr)
                return 2
            if done % 50 == 0:
                with CACHE_PATH.open("w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False)
                print(f"progress {done}/{len(spans)}")
    with CACHE_PATH.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    print(f"done: {done} spans -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
