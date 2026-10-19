"""Check proposal coverage and references, not semantic quality."""
from pathlib import Path
from collections import Counter
import json,hashlib
root=Path(__file__).resolve().parent
raw=json.loads((root/'01_candidates.json').read_text(encoding='utf-8'))
x=json.loads((root/'02_induced_proposals.json').read_text(encoding='utf-8'))
errors=[]
def index_unique(rows,key):
 ids=[r[key] for r in rows]
 for k,n in Counter(ids).items():
  if n!=1:errors.append({'kind':'duplicate','field':key,'id':k})
 return {r[key]:r for r in rows}
types=index_unique(x['canonical_types'],'type_id');rels=index_unique(x['canonical_relations'],'relation_id')
mm=index_unique(x['mention_mapping'],'mention_id');fm=index_unique(x['fact_mapping'],'fact_id')
expected_m={m['mention_id'] for m in raw['mentions']};expected_f={f['fact_id'] for f in raw['facts']}
if set(mm)!=expected_m:errors.append({'kind':'mention_coverage','missing':sorted(expected_m-set(mm)),'extra':sorted(set(mm)-expected_m)})
if set(fm)!=expected_f:errors.append({'kind':'fact_coverage','missing':sorted(expected_f-set(fm)),'extra':sorted(set(fm)-expected_f)})
for mid,m in mm.items():
 if m['type_id'] not in types:errors.append({'kind':'type_reference','id':mid})
for tid,t in types.items():
 if t['recommended_representation'] not in {'entity','attribute','context','defer'}:errors.append({'kind':'representation','id':tid})
 actual={mid for mid,m in mm.items() if m['type_id']==tid}
 if actual!=set(t['positive_mention_ids']):errors.append({'kind':'type_backreference','id':tid})
for fid,f in fm.items():
 for rid in f['relation_ids']:
  if rid not in rels:errors.append({'kind':'relation_reference','id':fid,'rid':rid})
for rid,r in rels.items():
 actual={fid for fid,f in fm.items() if rid in f['relation_ids']}
 if actual!=set(r['source_fact_ids']):errors.append({'kind':'relation_backreference','id':rid})
manifest=json.loads((root/'input_manifest.json').read_text(encoding='utf-8'))
if hashlib.sha256((root/'input_blocks.jsonl').read_bytes()).hexdigest()!=manifest['input_sha256']:errors.append({'kind':'input_changed'})
raw_audit=json.loads((root/'01_audit.json').read_text(encoding='utf-8'))
if hashlib.sha256((root/'01_candidates.json').read_bytes()).hexdigest()!=raw_audit['sha256']['01_candidates.json']:errors.append({'kind':'raw_candidates_changed'})
report={'counts':{k:len(x[k]) for k in x},'representation_counts':dict(Counter(t['recommended_representation'] for t in types.values())),'split_suggestions':[fid for fid,f in fm.items() if f['requires_split']],'errors':errors,'input_and_raw_unchanged':not any(e['kind'] in {'input_changed','raw_candidates_changed'} for e in errors),'semantic_correctness_verified':False,'supervised_bert_run':False}
(root/'02_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(int(bool(errors)))
