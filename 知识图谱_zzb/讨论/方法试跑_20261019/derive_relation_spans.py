"""Preserve raw candidates; derive ordered literal spans for relation phrases.
This is a traceability repair, not a semantic correction or a model rerun.
"""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parent
blocks={r['block_id']:r for r in map(json.loads,(ROOT/'input_blocks.jsonl').read_text(encoding='utf-8').splitlines())}
raw=(ROOT/'01_candidates.json').read_bytes(); data=json.loads(raw.decode('utf-8')); changes=[]
for f in data['facts']:
    text=blocks[f['block_id']]['text']; phrase=f['relation_raw']
    parts=[phrase] if phrase in text else [p.strip() for p in re.split(r'\.\.\.|…',phrase) if p.strip()]
    spans=[]; cursor=0; valid=True
    for part in parts:
        start=text.find(part,cursor)
        if start<0:valid=False;break
        spans.append({'text':part,'start':start,'end':start+len(part),'block_id':f['block_id']});cursor=start+len(part)
    f['relation_spans']=spans if valid else []
    f['relation_span_status']='exact' if phrase in text else ('fragments_only_needs_semantic_review' if valid else 'unresolved')
    if phrase not in text:changes.append({'fact_id':f['fact_id'],'original_relation_raw':phrase,'derived_spans':f['relation_spans'],'status':f['relation_span_status']})
(ROOT/'01_candidates_with_spans.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
report={'source_sha256':hashlib.sha256(raw).hexdigest(),'method':'literal split at ellipsis, ordered exact substring alignment; preserve original phrase','changes':changes,'semantic_validation':False}
(ROOT/'01_span_derivation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
