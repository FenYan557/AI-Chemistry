"""Conservative quarantine for semantic failure classes found in the frozen holdout.
Flags express residual risk, not proof every matching fact is false. Never rewrite facts.
"""
import re
RESULT=re.compile(r"observed|reveal|show(?:ed|s)?|demonstrat|exhibit|increas|decreas|suppress|inhibit|accelerat|refin|shift|发现|表明|增加|降低|减小|抑制|观察|显示|变为",re.I)
RECIPE=re.compile(r"composition.*(?:bath|solution)|(?:bath|solution).*composition|solution included|solution was composed|镀液.*(?:组成|配方)|配方.*(?:为|组成)",re.I)
STUDY=re.compile(r"(?:in this work|this study|本研究|本文).*(?:investigat|characteriz|analys|clarif|studied|研究|分析|表征)|(?:aim|objective|目的).*",re.I)

def flags(row):
    f=row["raw"];q=f["quote"];reasons=[]
    if f["statement"]=="observation" and f["relation"] in ("other","measurement"):
        if RECIPE.search(q):reasons.append("recipe_not_observed_result")
        elif not f.get("outcomes") and not RESULT.search(q):reasons.append("unresolved_protocol_vs_observation")
    if f["statement"]=="calculation_result" and f["relation"] in ("other","measurement") and not f.get("outcomes"):
        reasons.append("unresolved_calculation_setup_vs_result")
    values=" ".join(str(o.get("value","")) for o in f.get("outcomes",[]))
    if f["relation"]=="effect" and re.search(r"association|correlat|相关|关联",values,re.I):
        reasons.append("association_or_prediction_not_causal_effect")
    if f["relation"] in ("effect","adsorption","measurement") and f["statement"]=="reported_claim" and not f.get("outcomes") and STUDY.search(q):
        reasons.append("study_description_not_demonstrated_result")
    subject=f["subject"]
    if re.search(r"tests?$|measurements?$|experiments?$|测试|实验",subject,re.I):
        if any(c.get("about")=="subject" and re.search(r"concentrat|浓度",c.get("parameter",""),re.I) for c in f.get("conditions",[])):
            reasons.append("concentration_assigned_to_method")
    target=f.get("target")
    if f["relation"]=="effect" and target and re.search(r"compar(?:ed|ison)\s+(?:to|with)\s+(?:the\s+)?"+re.escape(target)+r"(?:\W|$)",q,re.I):
        reasons.append("comparison_target_may_not_be_affected_object")
    if f["relation"]=="effect" and not target:
        indicators=[o.get("indicator","").strip().casefold() for o in f.get("outcomes",[])]
        if subject.strip().casefold() in indicators or re.search(r"^(?:coating|cobalt|copper|nickel|钴|铜|镍)$|(?:coating|deposit|layer|efficiency|resistance|镀层|电流效率|电位)$",subject,re.I):
            reasons.append("affected_property_or_material_as_causal_subject")
    if f["relation"]=="adsorption" and target and re.search(r"(?:Cu|Co|Ni|铜|钴|镍).*(?:[1-4].*[+＋]|ions?|离子)",target,re.I) and not re.search(r"surface|substrate|表面|基底",target,re.I):
        reasons.append("ionic_complexation_not_surface_adsorption")
    concentrations=[c.get("value") for c in f.get("conditions",[]) if re.search(r"concentrat|浓度",c.get("parameter",""),re.I)]
    if len(set(str(v) for v in concentrations))>1 and len(f.get("outcomes",[]))>1:
        reasons.append("multiple_concentration_regimes_without_result_binding")
    if f["relation"]=="effect" and re.search(r"synerg|co.?adsorb|协同",row.get("source",""),re.I) and re.search(r"subsequent|随后|再次",q,re.I):
        reasons.append("sequential_synergistic_system_requires_binding")
    return reasons
