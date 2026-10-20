"""最多两个物质、每物质PubChem/ChEBI各一次；已有缓存不联网，不自动身份合并。"""
import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUERIES = {
    "pubchem": "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/property/IUPACName,MolecularFormula,InChIKey/JSON",
    "chebi_ols": "https://www.ebi.ac.uk/ols4/api/search?q={name}&ontology=chebi&exact=true&rows=3",
}
def lookup(output=None, refresh=False):
    output = output or ROOT / "data/external"
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for name in ["adenosine", "saccharin"]:
        for resource, template in QUERIES.items():
            path = output / (name + "_" + resource + ".json")
            if path.exists() and not refresh:
                records.append(json.loads(path.read_text(encoding="utf-8")))
                continue
            url = template.format(name=urllib.parse.quote(name))
            item = {"query":name,"resource":resource,"url":url,"retrieved_at":datetime.now(timezone.utc).isoformat(),
                    "match_status":"candidate","auto_merge":False,"license_note":"保留原资源来源；ChEBI CC BY 4.0；PubChem具体注释遵循原贡献源。"}
            try:
                request = urllib.request.Request(url,headers={"User-Agent":"A2lab-SchemaPilot/0.1"})
                with urllib.request.urlopen(request,timeout=15) as response:
                    raw = response.read(1_000_001)
                if len(raw)>1_000_000:
                    raise ValueError("response exceeds one MB bound")
                item.update(status="ok",response_sha256=hashlib.sha256(raw).hexdigest(),response=json.loads(raw))
            except Exception as exc:
                # 单次失败记录，不更换通道重试，也不报告成匹配成功。
                item.update(status="error",error_type=type(exc).__name__,error=str(exc))
            path.write_text(json.dumps(item,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            records.append(item)
    summary={"requests":len(records),"ok":sum(r["status"]=="ok" for r in records),
             "errors":sum(r["status"]=="error" for r in records),"all_matches_unreviewed":True,"records":[
                 {k:r.get(k) for k in ["query","resource","status","url","retrieved_at","response_sha256","error"]} for r in records]}
    (output/"lookup_report.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--refresh",action="store_true",help="显式再次查询；默认复用缓存，含失败记录")
    a=p.parse_args()
    r=lookup(refresh=a.refresh)
    print(json.dumps({k:v for k,v in r.items() if k!="records"},ensure_ascii=False))
    raise SystemExit(0 if not r["errors"] else 1)
