import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from finalize_entity_corpus_reuse import normalize,guard_entity,stable_preview_and_patch

class SavedResponseRecoveryTests(unittest.TestCase):
    def fixture(self):
        return {"status":"success","finish_reason":"stop","data":{"updates":[],"not_entities":[],"additions":[],"coverage_notes":""}}
    def task(self):
        return {"candidates":[{"id":"c","name":"PEG","source_id":"b","context_start":0,"context":"PEG (MW 6000)"}],"segments":[]}
    blocks={"b":{"id":"b","document_id":"d","text":"PEG (MW 6000); CuSO_4"}}
    def entity(self,**changes):
        e={"name":"PEG","source_id":"b","category":"chemical","kind":"polymer","aliases":[],"distinctions":[]};e.update(changes);return e
    def test_recover_only_from_actually_supplied_context(self):
        r=self.fixture();r['data']['additions']=[self.entity()]
        out,issues=normalize(r,self.task(),self.blocks)
        self.assertEqual(len(out['grounded']),1);self.assertTrue(out['grounded'][0]['identity_uncertain'])
    def test_outside_sent_excerpt_is_quarantined(self):
        r=self.fixture();r['data']['additions']=[self.entity(name="CuSO_4")]
        out,_=normalize(r,self.task(),self.blocks)
        self.assertFalse(out['grounded']);self.assertTrue(out['quarantined'])
    def test_conflicting_decisions_do_not_drop_record_or_other_updates(self):
        r=self.fixture();r['status']='invalid';r['data']['updates']=[{'id':'c','category':'chemical','kind':'polymer','identity_uncertain':False,'reason':'x'}];r['data']['not_entities']=[{'id':'c','reason':'x'}]
        out,issues=normalize(r,self.task(),self.blocks)
        self.assertEqual(out['status'],'success');self.assertFalse(out['data']['updates']);self.assertEqual(out['data']['not_entities'][0]['id'],'c')
        self.assertIn('conflicting_decisions_kept_pending',[i['reason'] for i in issues])
    def test_bad_alias_does_not_discard_literal_name(self):
        r=self.fixture();r['data']['additions']=[self.entity(aliases=[{'surface':'invented','source_id':'b'}])]
        out,issues=normalize(r,self.task(),self.blocks)
        self.assertEqual(out['grounded'][0]['name'],'PEG');self.assertFalse(out['grounded'][0]['aliases']);self.assertTrue(out['grounded'][0]['identity_uncertain'])
    def test_bad_alias_preserves_valid_specification(self):
        r=self.fixture();r['data']['additions']=[self.entity(aliases=[{'surface':'invented','source_id':'b'}],distinctions=[{'kind':'molecular_weight','value':'6000','source_id':'b'}])]
        out,_=normalize(r,self.task(),self.blocks)
        self.assertEqual(out['grounded'][0]['distinctions'][0]['value'],'6000')
    def test_chemical_formula_not_repaired(self):
        r=self.fixture();r['data']['additions']=[self.entity(name='CuSO4')]
        out,_=normalize(r,self.task(),self.blocks)
        self.assertFalse(out['grounded'])
    def test_truncated_response_not_promoted(self):
        r=self.fixture();r.update(status='incomplete',finish_reason='length')
        out,_=normalize(r,self.task(),self.blocks)
        self.assertEqual(out['status'],'incomplete')
    def test_invalid_subclass_salvages_literal_name_as_uncertain(self):
        r=self.fixture();r['status']='invalid';r['data']['additions']=[self.entity(kind='unsupported')]
        out,issues=normalize(r,self.task(),self.blocks)
        self.assertEqual(out['grounded'][0]['name'],'PEG');self.assertEqual(out['grounded'][0]['kind'],'unknown');self.assertTrue(out['grounded'][0]['identity_uncertain'])
    def test_crystal_plane_is_not_ion(self):
        e,notes=guard_entity(self.entity(name='Cu(111)',kind='metal_ion'))
        self.assertEqual(e['category'],'material');self.assertEqual(e['kind'],'not_chemical')
    def test_concentration_not_polymer_specification(self):
        e,notes=guard_entity(self.entity(distinctions=[{'kind':'molecular_weight','value':'2000','source_id':'b'},{'kind':'other','value':'100 ppm','source_id':'b'}]))
        self.assertEqual(len(e['distinctions']),1);self.assertEqual(e['distinctions'][0]['value'],'2000')
    def test_corrupt_formula_is_never_confirmed(self):
        e,notes=guard_entity(self.entity(name='H_2S0_4',kind='acid',identity_uncertain=False))
        self.assertTrue(e['identity_uncertain']);self.assertEqual(e['name'],'H_2S0_4')
    def test_existing_ids_preserved_and_delta_only_adds(self):
        ev={'block_id':'b','start':0,'end':3,'quote':'PEG'}
        base={'mentions':[{'id':'old','document_id':'d','surface':'PEG','evidence':ev}],'entities':[{'id':'old_entity','from_mention_id':'old'}]}
        preview={'mentions':[{'id':'new_generated','document_id':'d','surface':'PEG','evidence':ev}],'entities':[{'id':'new_entity','from_mention_id':'new_generated'}],'identities':[{'id':'i','document_id':'d'}],'identity_links':[{'mention_id':'new_generated','identity_id':'i'}],'facts':[],'edges':[]}
        pool=[{'id':'c','mention_id':'new_generated','category':'chemical','kind':'polymer','proposed_type_id':None,'semantic_qa':'pending'}]
        out,rows,delta,patch=stable_preview_and_patch(preview,pool,base)
        self.assertEqual(out['mentions'][0]['id'],'old');self.assertEqual(out['entities'][0]['id'],'old_entity');self.assertEqual(out['identity_links'][0]['mention_id'],'old')
        self.assertFalse(delta['mentions']);self.assertFalse(patch['automatic_application'])

if __name__=='__main__':unittest.main()
