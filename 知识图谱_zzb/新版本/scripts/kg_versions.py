"""Local, immutable KG snapshots with separate schema and data versions. No API calls."""
import argparse,hashlib,json,shutil
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
COLLECTIONS=("documents","blocks","mentions","entities","identities","identity_links","facts","edges")
SPECS=[
 {"id":"kg-v1-direct-20261020","folder":"v1_direct_extraction","label":"旧版：直接全库抽取","data_version":"1.0.0","role":"historical_baseline","workflow_status":"raw_extraction_frozen","source":"reports/full_extraction_20261020/knowledge_graph.json","source_report":"reports/full_extraction_20261020/README.md","limitations":"首轮原始结果；保留partial/failed造成的覆盖限制，未作为已审核事实发布。"},
 {"id":"kg-v2-entity-20261021","folder":"v2_entity_enhanced","label":"工作版：实体已完善，关系待继续完善","data_version":"2.0.0-dev.20261021","role":"active_working","workflow_status":"entities_integrated_relations_pending","source":"reports/entity_integrated_20261021/knowledge_graph.json","source_report":"reports/entity_integrated_20261021/整合与后续工作.md","limitations":"新增实体与身份仍有pending/unresolved；关系保留既有结果，未执行新关系抽取。"}
]

def load(path):return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def within(root,relative):
    root=Path(root).resolve();path=(root/relative).resolve()
    if not path.is_relative_to(root):raise ValueError("version path escapes project")
    return path

def initialize(root=ROOT):
    root=Path(root).resolve()
    if (root/"CURRENT.json").exists() or (root/"versions/index.json").exists():raise ValueError("version catalog exists; do not overwrite registered snapshots")
    # Check all inputs before creating a registered version.
    sources=[within(root,spec["source"]) for spec in SPECS]
    for source in sources:
        if not source.is_file():raise FileNotFoundError(source)
    entries=[];created=datetime.now(timezone.utc).isoformat(timespec="seconds")
    for spec,source in zip(SPECS,sources):
        directory=root/"versions"/spec["folder"];graph_path=directory/"knowledge_graph.json"
        if graph_path.exists():raise ValueError("snapshot destination exists: "+str(graph_path))
        directory.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,graph_path)
        graph=load(graph_path);fingerprint=digest(graph_path)
        assert fingerprint==digest(source)
        manifest={"manifest_version":1,"version_id":spec["id"],"label":spec["label"],"data_version":spec["data_version"],"schema_version":graph["schema_version"],"role":spec["role"],"workflow_status":spec["workflow_status"],"registered_at":created,"snapshot_frozen":True,"freeze_meaning":"registered file bytes are fixed; semantic review is not implied","graph":"knowledge_graph.json","sha256":fingerprint,"size_bytes":graph_path.stat().st_size,"counts":{key:len(graph[key]) for key in COLLECTIONS},"human_review":"pending","source_artifacts":[{"path":spec["source"],"sha256":fingerprint}],"source_report":spec["source_report"],"limitations":spec["limitations"],"historical_producer_commit":None,"code_provenance_note":"Governance commit captures current code; original extraction-time commit is not retrospectively asserted."}
        if spec["role"]=="active_working":
            manifest["parent_data_version_id"]=SPECS[0]["id"]
            for name,stage in (("reports/full_extraction_20261020/quality/precision_graph.json","precision_filtered_intermediate"),("reports/entity_corpus_reuse_20261021/normalized/candidate_delta.json","entity_delta")):
                path=within(root,name);manifest["source_artifacts"].append({"path":name,"sha256":digest(path),"stage":stage})
            manifest["lineage_note"]="v1 raw -> conservative filtering intermediate -> entity integration; fact reduction precedes entity enhancement."
        save(directory/"manifest.json",manifest)
        relative=directory.relative_to(root).as_posix()
        entries.append({"version_id":spec["id"],"label":spec["label"],"role":spec["role"],"manifest":relative+"/manifest.json"})
        readme=f"# {spec['label']}\n\n完整图谱：[knowledge_graph.json](knowledge_graph.json)。版本清单：[manifest.json](manifest.json)。\n\n数据版本：`{spec['data_version']}`；schema：`{graph['schema_version']}`。\n\n"+spec['limitations']+"\n\n已登记快照不覆盖修改。工作版后续更新应创建新快照并同步CURRENT与版本索引；本目录名称表示数据分支，不代表新schema。\n\n来源和校验指纹在manifest中；对应原始报告保留在项目reports目录。\n"
        (directory/"README.md").write_text(readme,encoding="utf-8")
    save(root/"versions/index.json",{"catalog_version":1,"versions":entries,"current_selector":"../CURRENT.json","policy":"two data lineages; reports are provenance and intermediates, not additional current graph versions"})
    working=entries[1];manifest=load(root/working["manifest"])
    save(root/"CURRENT.json",{"catalog_version":1,"current_version_id":working["version_id"],"manifest":working["manifest"],"graph":"versions/"+SPECS[1]["folder"]+"/knowledge_graph.json","sha256":manifest["sha256"],"baseline_version_id":entries[0]["version_id"],"status":manifest["workflow_status"],"human_review":"pending"})

def check(root=ROOT):
    root=Path(root).resolve();catalog=load(root/"versions/index.json");current=load(root/"CURRENT.json");versions={};errors=[]
    for entry in catalog["versions"]:
        manifest_path=within(root,entry["manifest"]);manifest=load(manifest_path)
        graph_path=within(root,(manifest_path.parent/manifest["graph"]).relative_to(root))
        if entry["version_id"] in versions:errors.append("duplicate_version_id")
        if entry["version_id"]!=manifest["version_id"]:errors.append("manifest_version_id_mismatch")
        if digest(graph_path)!=manifest["sha256"]:errors.append("snapshot_hash_mismatch:"+entry["version_id"])
        graph=load(graph_path)
        if graph["schema_version"]!=manifest["schema_version"]:errors.append("schema_version_mismatch")
        if {key:len(graph[key]) for key in COLLECTIONS}!=manifest["counts"]:errors.append("graph_counts_mismatch")
        if graph_path.stat().st_size!=manifest["size_bytes"]:errors.append("snapshot_size_mismatch")
        versions[entry["version_id"]]=(entry,manifest,graph_path)
    if len(versions)!=2:errors.append("expected_two_data_lineages")
    if current["current_version_id"] not in versions or current["baseline_version_id"] not in versions:errors.append("current_or_baseline_missing")
    else:
        entry,manifest,path=versions[current["current_version_id"]]
        if current["manifest"]!=entry["manifest"] or within(root,current["graph"])!=path or current["sha256"]!=manifest["sha256"]:errors.append("current_selector_mismatch")
        if entry["role"]!="active_working":errors.append("current_role_mismatch")
    return {"valid":not errors,"errors":errors,"versions":len(versions),"current":current["current_version_id"],"network_calls":0}

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("command",choices=("init","check","current"));a=parser.parse_args()
    if a.command=="init":initialize()
    if a.command=="current":print(json.dumps(load(ROOT/"CURRENT.json"),ensure_ascii=False))
    else:
        result=check();print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if result["valid"] else 1)
