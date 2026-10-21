"""Hidden-label positive/negative controls derived from actual source excerpts."""
import argparse
import copy
import json
import hashlib
import random
from pathlib import Path
from batch_extract import read,write
from quality_verify import Verifier

ROOT=Path(__file__).resolve().parents[1]

def controls():
    source=read(ROOT/"examples/literature_bundle.json")
    ado=next(b for b in source["blocks"] if b["id"]=="blk:7cf3c70d130e763f")
    sac=next(b for b in source["blocks"] if b["id"]=="blk:cf5b948c8b59760d")
    measurement="The resistivity of the cobalt film decreased to 14.4 μΩ·cm, and further decreased to 10.7 μΩ·cm after the annealing treatment."
    mechanism="Based on the changes of the ADO adsorption sites from the MD and E-FTIR analyses, an intramolecular synergistic acceleration–suppression mechanism was proposed to explain the effects of low-concentration acceleration but high-concentration suppression in cobalt deposition."
    morphology="When the amount of saccharin was 3 mg·L –1, the cobalt coating transformed from disordered large grains to a honeycomb structure, with a preferred orientation of (002) facet on hexagonal close-packed (HCP) cobalt crystals."
    base=[
        (sac,{"subject":"cobalt film","relation":"measurement","statement":"observation","quote":measurement,
              "outcomes":[{"indicator":"resistivity","value":"14.4","unit":"μΩ·cm","kind":"numeric","quote":"decreased to 14.4 μΩ·cm"},
                          {"indicator":"resistivity","value":"10.7","unit":"μΩ·cm","kind":"numeric","quote":"further decreased to 10.7 μΩ·cm after the annealing treatment","stage":"after the annealing treatment"}]}),
        (ado,{"subject":"ADO","target":"cobalt deposition","relation":"effect","statement":"reported_claim","quote":mechanism,
              "conditions":[{"parameter":"concentration","value":"low","quote":"low-concentration acceleration","about":"subject"}],
              "outcomes":[{"indicator":"cobalt deposition","value":"acceleration","kind":"qualitative","direction":"increase","quote":"low-concentration acceleration"}]}),
        (ado,{"subject":"ADO","target":"cobalt deposition","relation":"mechanism","statement":"author_interpretation","quote":mechanism}),
        (sac,{"subject":"saccharin","target":"cobalt coating","relation":"effect","statement":"observation","quote":morphology,
              "conditions":[{"parameter":"saccharin amount","value":"3","unit":"mg·L –1","quote":"3 mg·L –1","about":"subject"}],
              "outcomes":[{"indicator":"structure","value":"honeycomb structure","kind":"qualitative","quote":"transformed from disordered large grains to a honeycomb structure"}]})
    ]
    rows=[];labels={}
    for i,(block,fact) in enumerate(base):
        ident=f"control:P{i+1}"
        rows.append({"id":ident,"unit_id":block["id"],"source":block["text"],"raw":copy.deepcopy(fact)})
        labels[ident]={"expected":"supported","reason":"source-supported positive"}
    mutations=[]
    f=copy.deepcopy(base[0][1]);f["outcomes"][0]["value"]="1440";mutations.append((0,f,"changed numerical value"))
    f=copy.deepcopy(base[0][1]);f["outcomes"][1]["stage"]="before the annealing treatment";mutations.append((0,f,"reversed treatment stage"))
    f=copy.deepcopy(base[1][1]);f["outcomes"][0].update(value="suppression",direction="decrease");mutations.append((1,f,"reversed low-concentration effect"))
    f=copy.deepcopy(base[2][1]);f["statement"]="observation";mutations.append((2,f,"author mechanism upgraded to observation"))
    f=copy.deepcopy(base[0][1]);f["outcomes"][0].update(indicator="grain size",unit="nm");mutations.append((0,f,"wrong measured property and unit"))
    f=copy.deepcopy(base[3][1]);f["conditions"][0]["value"]="30";mutations.append((3,f,"wrong additive concentration"))
    f=copy.deepcopy(base[3][1]);f["subject"]="ADO";mutations.append((3,f,"wrong additive identity"))
    f=copy.deepcopy(base[0][1]);f["outcomes"][1].update(baseline="3",baseline_quote="decreased to 14.4 μΩ·cm");mutations.append((0,f,"fabricated baseline value"))
    f=copy.deepcopy(base[1][1]);f["conditions"][0]["value"]="high";mutations.append((1,f,"wrong concentration regime"))
    f=copy.deepcopy(base[3][1]);f["conditions"][0]["unit"]="mol/L";mutations.append((3,f,"incompatible concentration unit"))
    for i,(b,f,reason) in enumerate(mutations):
        block=base[b][0];ident=f"control:N{i+1}"
        rows.append({"id":ident,"unit_id":block["id"],"source":block["text"],"raw":f})
        labels[ident]={"expected":"not_supported","reason":reason}
    # Opaque IDs and shuffled order prevent labels leaking through P/N prefixes.
    blinded={r["id"]:"control:"+hashlib.sha256(("blind-"+r["id"]).encode()).hexdigest()[:12] for r in rows}
    labels={blinded[k]:v for k,v in labels.items()}
    for row in rows:row["id"]=blinded[row["id"]]
    random.Random(76351).shuffle(rows)
    return rows,labels

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--model",default="qwen3.7-plus")
    a=p.parse_args()
    rows,gold=controls()
    write(a.out/"gold_labels.json",gold)
    verifier=Verifier(a.out,a.model,workers=2)
    results=verifier.run(rows)
    positives=[k for k,v in gold.items() if v["expected"]=="supported"]
    negatives=[k for k,v in gold.items() if v["expected"]=="not_supported"]
    pos=sum(results.get(k,{}).get("verdict")=="supported" for k in positives)
    neg=sum(results.get(k,{}).get("verdict") in ("unsupported","unclear") for k in negatives)
    report={"positive_supported":pos,"positive_total":len(positives),"negative_rejected_or_unclear":neg,
            "negative_total":len(negatives),"usable_for_bulk_check":pos>=3 and neg>=9 and not verifier.stop.is_set(),
            "not_a_real_corpus_precision_estimate":True,"results":[{"id":k,**gold[k],"actual":results.get(k,{}).get("verdict")} for k in gold]}
    write(a.out/"control_report.json",report)
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":main()
