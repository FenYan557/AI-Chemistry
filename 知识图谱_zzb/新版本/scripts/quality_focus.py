"""Targeted semantic recheck for failure classes found in primary blind calibration."""
import argparse
import json
import re
from pathlib import Path
import quality_verify as qa
from batch_extract import read,write,now
from quality_rules import dump_jsonl

FOCUS="""本轮对以下边界严格核对：
1 observation是观测或测量结果。扫描范围、速度、循环数、软件等实验/计算设置本身应是reported_claim，不因为实验实际实施就称作观测结果。
2 future_work是尚待开展的后续研究建议。本研究“上一节/接下来/下一节”行文安排或已实施的方法不是未来工作。
3 effect必须有原文支持的作用或影响关系。某性能指标与另一指标相关，不足以把指标写成施加作用的添加剂或因果影响。
4 单纯“计算了ESP/用软件绘图/采用某方法”不是机制解释。mechanism需有解释作用过程的内容，而不只是研究方法或算过某参数。
5 不把“某抑制效应存在于孔内”改成“抑制效应影响孔结构”；作用物、被影响对象及发生位置必须区分。
判定的是整个raw记录。若核心事实正确但已填写陈述性质或关系实质错误，仍判unsupported，注明字段；字段缺省本身不构成错误。"""

def flags(row):
    f=row["raw"];q=f["quote"];source=row["source"];found=[]
    if f["relation"]=="effect" and re.search(r"correlat|associated with|relationship between|相关|关联",q,re.I):
        found.append("correlation_not_cause")
    if f["statement"]=="observation" and not f.get("outcomes") and f.get("conditions") and re.search(r"scan|test|experiment|frequency|speed|cycle|实验|测试|扫描|频率",source,re.I):
        found.append("protocol_as_observation")
    if (f["statement"]=="future_work" or f["relation"]=="future_work") and re.search(r"上一节|接下来|本节|下一节|next section|this section|following section",source,re.I):
        found.append("section_plan_as_future_work")
    if f["relation"]=="mechanism" and not f.get("outcomes") and re.search(r"software|Gaussian|DFT|simulation|calculated|determined|计算|模拟",source,re.I):
        found.append("calculation_method_as_mechanism")
    if f["relation"]=="effect" and re.search(r"effect$|behavior$|mechanism$|抑制效果|抑制效应",f["subject"],re.I):
        found.append("event_instead_of_acting_entity")
    return found

def main():
    p=argparse.ArgumentParser();p.add_argument("--cases",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--workers",type=int,default=2);p.add_argument("--model",default="qwen3.7-plus");a=p.parse_args()
    rows=[json.loads(x) for x in a.cases.read_text(encoding="utf-8").splitlines() if x.strip()]
    selected=[]
    for r in rows:
        reasons=flags(r)
        if reasons:selected.append({**r,"focus_flags":reasons})
    a.out.mkdir(parents=True,exist_ok=True)
    dump_jsonl(a.out/"cases.jsonl",selected)
    from collections import Counter
    write(a.out/"selection.json",{"selected":len(selected),"flags":dict(Counter(x for r in selected for x in r["focus_flags"])),
        "purpose":"calibration-driven targeted recheck; not a new independent precision sample"})
    original=qa.INSTRUCTION
    try:
        qa.INSTRUCTION=original+"\n"+FOCUS
        verifier=qa.Verifier(a.out,a.model,a.workers)
        verifier.run(sorted(selected,key=lambda r:(r["unit_id"],r["id"])))
        if verifier.stop.is_set():raise SystemExit("定向核验认证或路由失败，保留检查点")
        write(a.out/"summary.json",{"completed_at":now(),"selected":len(selected),**verifier.progress(),
            "application":"only downgrade previous acceptance on unsupported/unclear; preserve stricter earlier rejection"})
    finally:qa.INSTRUCTION=original

if __name__=="__main__":main()
