"""Audit traceability, not scientific correctness or recall. Python stdlib only."""
from pathlib import Path
import collections,hashlib,json,re
ROOT=Path(__file__).resolve().parent

def run():
    blocks={r['block_id']:r for r in map(json.loads,(ROOT/'input_blocks.jsonl').read_text(encoding='utf-8').splitlines())}
    data=json.loads((ROOT/'01_candidates.json').read_text(encoding='utf-8'))
    errors=[]; cross_block=[]; offsets=[]
    mentions=data['mentions']; ids=[m['mention_id'] for m in mentions]
    for mid,n in collections.Counter(ids).items():
        if n>1:errors.append({'kind':'duplicate_mention_id','id':mid})
    index={m['mention_id']:m for m in mentions}
    def check_quote(kind,rid,bid,quote):
        text=blocks.get(bid,{}).get('text')
        if not isinstance(quote,str) or not quote or text is None or quote not in text:
            errors.append({'kind':kind,'id':rid,'block_id':bid,'quote':quote});return
        starts=[m.start() for m in re.finditer(re.escape(quote),text)]
        offsets.append({'kind':kind,'id':rid,'block_id':bid,'spans':[[s,s+len(quote)] for s in starts]})
    for m in mentions:check_quote('mention',m['mention_id'],m['block_id'],m['text'])
    facts=data['facts']; fids=[f['fact_id'] for f in facts]
    for fid,n in collections.Counter(fids).items():
        if n>1:errors.append({'kind':'duplicate_fact_id','id':fid})
    for f in facts:
        check_quote('fact_quote',f['fact_id'],f['block_id'],f['evidence_quote'])
        check_quote('relation_raw',f['fact_id'],f['block_id'],f['relation_raw'])
        for i,q in enumerate(f.get('qualifiers',[])):check_quote('qualifier',f['fact_id']+':q'+str(i),f['block_id'],q['raw'])
        if f['discourse_status'] not in {'reported_result','proposed_explanation','future_work','unknown'}:errors.append({'kind':'status','id':f['fact_id']})
        if f['evidence_mode'] not in {'measured','computed','unspecified'}:errors.append({'kind':'mode','id':f['fact_id']})
        for mid in f['participants']:
            if mid not in index:errors.append({'kind':'unknown_reference','id':f['fact_id'],'mention_id':mid})
            elif index[mid]['block_id']!=f['block_id']:cross_block.append({'fact_id':f['fact_id'],'mention_id':mid,'source':index[mid]['block_id'],'target':f['block_id']})
    for i,a in enumerate(data['alias_candidates']):
        check_quote('alias',str(i),a['block_id'],a['evidence_quote'])
        for mid in a['mention_ids']:
            if mid not in index:errors.append({'kind':'alias_unknown_reference','id':i,'mention_id':mid})
    report={'counts':{'blocks':len(blocks),'documents':len({b['doc_id'] for b in blocks.values()}),'mentions':len(mentions),'raw_type_labels':len({m['proposed_type'] for m in mentions}),'facts':len(facts),'raw_relation_labels':len({f['candidate_relation_label'] for f in facts}),'alias_candidates':len(data['alias_candidates'])},'checks':'exact substrings for mentions, relation phrases, evidence and qualifiers; IDs and enumerated states','errors':errors,'cross_block_references_for_review':cross_block,'semantic_accuracy_measured':False,'recall_measured':False,'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'input_blocks.jsonl',ROOT/'01_candidates.json']}}
    (ROOT/'01_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'01_offsets.json').write_text(json.dumps(offsets,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return int(bool(errors))
if __name__=='__main__':raise SystemExit(run())
