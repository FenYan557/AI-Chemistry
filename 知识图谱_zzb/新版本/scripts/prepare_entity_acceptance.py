"""Freeze a bounded entity acceptance set and independent source reference BEFORE calls."""
import argparse, json, hashlib
from pathlib import Path
from batch_extract import read, write, now
from targeted_extract_pilot import fingerprint
from entity_extract_pilot import processing_fingerprint, INSTRUCTION

ROOT=Path(__file__).resolve().parents[1]
SELECTION=[
 ("1_s2_0_S0013468609007385_main",["blk:32a40ea36c779246e666","blk:d0f811a9df59cef50277"],"作者定义DB、PEG MW8000、含磷铜阳极、OCR酸式与光学设备"),
 ("3_巯基_1_丙磺酸盐与聚乙烯吡咯烷酮对电沉积钴生长的影响",["blk:4d2defcf77949baf425f"],"钴盐七水/六水、硼酸、电极材料与仪器；不修0/O损坏式"),
 ("DMG_丁二酮肟_",["blk:9d408bc9dc51e64811e9"],"电极设备与Co箔/Pt材料，不能删电极或当金属离子"),
 ("ao3c05248",["blk:e5e6dd9d0aae6971f37a"],"明确化学名、未定义JGB、DFT/MD/CV/EIS与铜离子"),
 ("d4nj05470a",["blk:6e3582360e43f6757a44","blk:8817f52101a1ec8dc53e"],"水合盐、非金属离子、作者定义缩写、材料与方法"),
]

# Each entry is one reference concept, alternatives are verbatim mentions which
# suffice for recognition. Specifications and alias correctness are checked apart.
FULL_REFERENCES={
 "blk:9d408bc9dc51e64811e9":[
  (["three electrode cell"],"equipment"),(["glass frit"],"equipment"),
  (["Saturated calomel electrode","SCE"],"equipment"),(["Co foil"],"material"),
  (["Platinum rotating disk electrode","RDE"],"material"),(["rotation rate"],"property")],
 "blk:6e3582360e43f6757a44":[
  (["CuSO _4·5H_2 O","CuSO _4 5H_2O"],"chemical"),(["H_2SO_4"],"chemical"),
  (["NaCl"],"chemical"),(["virgin make-up solution","VMS"],"material"),(["Cl -"],"chemical"),
  (["Acid Blue 1","AB1"],"chemical"),(["PEG"],"chemical"),(["SPS"],"chemical"),(["deionized water"],"chemical")],
 "blk:4d2defcf77949baf425f":[
  (["MPS"],"chemical"),(["PVP"],"chemical"),(["cyclic voltammetry","CV"],"method"),
  (["galvanostatic method","GM"],"method"),(["Metrohm electrochemical workstation","PGSTT302N"],"equipment"),
  (["platinum rotating disk electrode","Pt-RDE"],"material"),(["Pt rod"],"material"),
  (["saturated Hg/Hg _ 2 SO _ 4 reference electrode"],"equipment"),
  (["cobalt sulfate heptahydrate"],"chemical"),(["boric acid"],"chemical"),
  (["cobalt chloride hexahydrate"],"chemical"),(["solution I"],"material"),(["solution II"],"material")]
}

def collect_docs(x,found):
    if isinstance(x,dict):
        for k,v in x.items():
            if k in ("document_id","doc_id") and isinstance(v,str):found.add(v)
            else:collect_docs(v,found)
    elif isinstance(x,list):
        for v in x:collect_docs(v,found)

def prepare(out):
    if (out/"tasks.json").exists():raise ValueError("frozen set exists; do not overwrite")
    graphpath=ROOT/"reports/full_extraction_20261020/quality/precision_graph.json"
    g=read(graphpath); blocks={b["id"]:b for b in g["blocks"]}
    prior=list((ROOT/"reports/entity_pilot_20261021").glob("tasks.json"))+list((ROOT/"reports/targeted_reextraction_20261021").glob("**/tasks.json"))
    prior += [ROOT/"reports/model_selection_20261020/source_bundle.json", ROOT/"reports/extraction_pilot_20261020/source_bundle.json",ROOT/"reports/model_selection_20261020/selected_bundle.json"]
    excluded=set(); history=[]
    for f in prior:
        collect_docs(read(f),excluded);history.append({"path":str(f.relative_to(ROOT)),"sha256":hashlib.sha256(f.read_bytes()).hexdigest()})
    tasks=[]
    manifest={d["document_id"]:d for d in read(ROOT/"data/corpus_manifest.json")["documents"]}
    for i,(doc,ids,reason) in enumerate(SELECTION,1):
        assert doc not in excluded
        segments=[{"source_id":sid,"text":blocks[sid]["text"]} for sid in ids]
        assert all(blocks[sid]["document_id"]==doc for sid in ids)
        pool=[m["surface"] for m in g["mentions"] if m["document_id"]==doc and m.get("evidence",{}).get("block_id") in ids and m["surface"] in blocks[m["evidence"]["block_id"]]["text"]]
        tasks.append({"task_id":f"holdout_{i}","document_id":doc,"segments":segments,"target_names":list(dict.fromkeys(pool))[:20],"sample_group":"frozen_holdout","selection_reason":reason,"source_sha256":fingerprint(segments),"corpus_file_sha256":manifest[doc]["source_sha256"]})
    refs=[]
    for sid,items in FULL_REFERENCES.items():
        for alternatives,category in items:
            assert all(x in blocks[sid]["text"] for x in alternatives),(sid,alternatives)
            refs.append({"source_id":sid,"alternatives":alternatives,"category":category})
    write(out/"tasks.json",tasks)
    write(out/"reference_checkpoints.json",{"frozen_at":now(),"frozen_before_calls":True,"production_graph_sha256":hashlib.sha256(graphpath.read_bytes()).hexdigest(),"processing_fingerprint":processing_fingerprint(),"prompt_fingerprint":fingerprint(INSTRUCTION),"history_checked":history,"excluded_document_ids":sorted(excluded),"prior_full_corpus_exposure":"These documents exist in the earlier full extraction graph; new to entity/targeted pilots, not never processed by any model.","reference_basis":"主智能体先读来源标注，非独立领域专家金标准；未用于修改流程", "scope":"具体化学物、材料、工艺、方法、设备及可测量性质；纯角色、供应商、数值、结构片段不作为独立实体。溶液整体保留粗类，不判分子身份。", "full_reference_blocks":list(FULL_REFERENCES),"reference_entities":refs,"checks":["PEG的8000是规格不是别名","DB/JGB相近不能合并","两种钴盐水合态不同不得合并","OCR式不得修正后确认身份","金属电极不得标为metal_ion","JGB/PEG/SPS未定义处不扩写","作者定义可保留，方法与设备区别","自动通过记录按每任务索引0/5/10…抽查；主审另检查全部输出"]})
    write(out/"frozen_pipeline.json",{"frozen_at":now(),"processing_fingerprint":processing_fingerprint(),"instruction":INSTRUCTION,"files":{name:hashlib.sha256((ROOT/"scripts"/name).read_bytes()).hexdigest() for name in ("entity_extract_pilot.py","entity_pilot_review.py","finalize_entity_pilot.py")}})
    print(json.dumps({"documents":len(tasks),"blocks":sum(len(t["segments"]) for t in tasks),"reference_concepts":len(refs)},ensure_ascii=False))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);prepare(p.parse_args().run)
