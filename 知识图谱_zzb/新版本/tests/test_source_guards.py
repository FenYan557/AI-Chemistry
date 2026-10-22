import copy,sys,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'scripts'));sys.path.insert(0,str(P/'construction'))
from condition_values import classify_condition,parse_numeric,parse_range,numeric_bounds
from merge_validation import gate_proposal,apply_gated_merges
from extraction import ingest
from entity_resolution_retrieval import select
from test_pipeline import make_bundle
class SourceGuards(unittest.TestCase):
 def rows(self,labels,quote):
  return [{'id':str(i),'label':label,'canonical_label':label,'document_id':'d','kind':'chemical','distinctions':[],'contexts':[{'source_id':'b','start':0,'text':quote}]} for i,label in enumerate(labels)]
 def test_cooccurrence_not_identity(self):
  rows=self.rows(['JGB','SPS'],'JGB (leveler) and SPS (accelerator) were added.')
  p={'ids':['0','1'],'decision':'merge','basis':'source_definition','reason':'same substance','evidence':[{'source_id':'b','quote':'JGB (leveler) and SPS (accelerator) were added.'}]}
  ok,_=gate_proposal(p,{r['id']:r for r in rows},p['ids'],phase='document');self.assertFalse(ok)
 def test_definition_proves_alias(self):
  quote='Polyvinylpyrrolidone (PVP) was used.'
  rows=self.rows(['Polyvinylpyrrolidone','PVP'],quote)
  p={'ids':['0','1'],'decision':'merge','basis':'source_definition','reason':'source defines abbreviation','evidence':[{'source_id':'b','quote':quote}]}
  ok,_=gate_proposal(p,{r['id']:r for r in rows},p['ids'],phase='document');self.assertTrue(ok)
 def test_cross_phase_without_doc_ids_still_rejects_acronym(self):
  rows=self.rows(['JGB','JGB'],'JGB')
  for r in rows:r.pop('document_id')
  p={'ids':['0','1'],'decision':'merge','basis':'format_equivalence','reason':'same letters','evidence':[{'source_id':'b','quote':'JGB'}]}
  self.assertFalse(gate_proposal(p,{r['id']:r for r in rows},p['ids'],phase='cross')[0])
 def test_missing_identity_basis_rejected(self):
  rows=self.rows(['A','B'],'A (B)')
  p={'ids':['0','1'],'decision':'merge','reason':'same','evidence':[{'source_id':'b','quote':'A (B)'}]}
  self.assertFalse(gate_proposal(p,{r['id']:r for r in rows},p['ids'])[0])
 def test_transitive_keep_separate_enforced(self):
  rows=self.rows(['X','X','X'],'X')
  proof={'decision':'merge','basis':'format_equivalence','reason':'same literal format','evidence':[{'source_id':'b','quote':'X'}]}
  ps=[{'ids':['0','2'],'decision':'keep_separate','reason':'different specified objects'},dict(proof,ids=['0','1']),dict(proof,ids=['1','2'])]
  groups,accepted,rejected,_=apply_gated_merges(rows,ps,'document',lambda _:None)
  self.assertEqual(len(groups),2);self.assertEqual(len(accepted),1);self.assertTrue(rejected)
 def test_canonical_label_cannot_forge_identity(self):
  rows=self.rows(['JGB','SPS'],'JGB and SPS were used. SPS (SPS).')
  rows[0]['canonical_label']='SPS'
  p={'ids':['0','1'],'decision':'merge','basis':'source_definition','reason':'same chemical','evidence':[{'source_id':'b','quote':'JGB and SPS were used. SPS (SPS).'}]}
  self.assertFalse(gate_proposal(p,{r['id']:r for r in rows},p['ids'])[0])
 def test_empty_merge_rejected(self):
  self.assertFalse(gate_proposal({'decision':'merge','reason':'x'}, {},[])[0])
 def test_negative_sign_preserved(self):
  q=classify_condition('−0.21','potential −0.21 V','V');self.assertEqual(q['value_raw'],'−0.21');self.assertEqual(q['value_kind'],'numeric')
 def test_material_is_not_a_unit(self):
  q=classify_condition('200','containing 200 PEG',None);self.assertIsNone(q['unit_raw']);self.assertEqual(q['value_raw'],'200')
 def test_unit_prefix_cannot_change_scale(self):
  q=classify_condition('2','at 2 mg/L after addition','g/L');self.assertEqual(q['unit_raw'],'mg/L')
 def test_compound_unit_not_truncated(self):
  self.assertEqual(classify_condition('5','scan rate 5 mV/s','mV/s')['unit_raw'],'mV/s')
  self.assertIsNone(classify_condition('2','rate 2 mg/L/h','mg/L/h')['unit_raw'])
 def test_unknown_owner_is_not_subject(self):
  b=make_bundle();b['blocks'][0]['text']='PVP was used at 5 ppm.'
  raw={'subject':'PVP','relation':'other','statement':'reported_claim','quote':'PVP was used at 5 ppm.','conditions':[{'parameter':'concentration','value':'5','unit':'ppm','quote':'5 ppm'}]}
  f=ingest(b,'blk1',{'facts':[raw]})['facts'][0];self.assertEqual(f['conditions'][0]['about_mention_ids'],[]);self.assertEqual(f['conditions'][0]['scope_status'],'pending')
 def test_range_not_scalar(self):
  q=classify_condition('10-20','NBT 10-20 ppm','ppm');self.assertEqual(q['value_kind'],'range');self.assertEqual(numeric_bounds(q),(10.,20.))
 def test_inequality_not_collapsed(self):
  self.assertEqual(classify_condition('more than 1 ppm','more than 1 ppm','ppm')['value_kind'],'qualitative')
 def test_scientific_scalar_not_range(self):
  q=classify_condition('1e-3','value 1e-3 V','V');self.assertEqual(q['value_kind'],'numeric');self.assertEqual(numeric_bounds(q),(.001,.001))
 def test_explicit_anchor_handles_repeated_acronym(self):
  bundle=make_bundle();bundle['blocks'][0]['text']='PVP was prepared. polyvinylpyrrolidone (PVP) was studied. The HOMO was −6.877 eV.'
  raw={'subject':'PVP','subject_quote':'polyvinylpyrrolidone (PVP)','relation':'calculated_property','statement':'calculation_result','quote':'The HOMO was −6.877 eV.','outcomes':[{'indicator':'HOMO','value':'−6.877','unit':'eV','kind':'numeric','quote':'−6.877 eV'}]}
  g=ingest(bundle,'blk1',{'facts':[raw]});self.assertEqual(len(g['facts']),1);self.assertEqual(len(g['facts'][0]['evidence']),2)
 def test_protocol_is_not_effect(self):
  b=make_bundle();b['blocks'][0]['text']='The basic electrolyte contains CoSO4 at 0.3 M.'
  raw={'subject':'basic electrolyte','target':'CoSO4','relation':'composition','statement':'reported_claim','quote':b['blocks'][0]['text']}
  g=ingest(b,'blk1',{'facts':[raw]});self.assertEqual(len(g['edges']),0);self.assertEqual(g['facts'][0]['relation']['raw'],'composition')
 def test_incomplete_coverage_is_retained(self):
  b=make_bundle();b['blocks'][0]['text']='PVP was used.'
  g=ingest(b,'blk1',{'facts':[{'subject':'PVP','relation':'other','statement':'reported_claim','quote':'PVP was used.'}],'coverage_complete':False,'remaining_topics':['table']})
  self.assertIn('bounded follow-up',' '.join(g['facts'][0]['notes']))
 def artifact(self):
  return {'concepts':[{'id':'m','kind':'chemical','canonical_label':'MTT','aliases':['MTT']},{'id':'p','kind':'property','canonical_label':'cathodic onset potential','aliases':['cathodic onset potential']}],
    'contextual_facts':[{'fact_id':'mtt','participants':[{'concept_id':'m'}],'evidence':[],'conditions':[],'outcomes':[]},{'fact_id':'unrelated','participants':[{'concept_id':'p'}],'evidence':[],'conditions':[],'outcomes':[]}]}
 def test_named_object_beats_long_generic_property(self):
  self.assertEqual(select(self.artifact(),'MTT cathodic onset potential',8)['fact_ids'],['mtt'])
 def test_generic_property_query_still_works(self):
  self.assertIn('unrelated',select(self.artifact(),'cathodic onset potential',8)['fact_ids'])
 def test_no_focus_facts_does_not_return_unrelated_facts(self):
  a=self.artifact();a['contextual_facts']=a['contextual_facts'][1:];self.assertEqual(select(a,'MTT cathodic onset potential',8)['fact_ids'],[])
if __name__=='__main__':unittest.main()
