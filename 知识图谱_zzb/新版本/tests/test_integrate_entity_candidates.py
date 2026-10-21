import sys,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from integrate_entity_candidates import merge,relation_queue

class IntegrationTests(unittest.TestCase):
    def fixtures(self):
        b={k:[] for k in ("documents","blocks","mentions","entities","identities","identity_links","facts","edges","role_assignments","experiments","runs","samples","identity_merges","external_records")}
        b['documents']=[{'id':'d'}];b['blocks']=[{'id':'b','document_id':'d','text':'name'}]
        b['facts']=[{'id':'f','document_id':'d','relation':{'candidate_relation_id':None},'evidence':[{'kind':'block','block_id':'b'}]}];b['edges']=[{'id':'edge'}]
        d={k:copy.deepcopy(b[k]) for k in ('documents','blocks')};d.update(mentions=[{'id':'m','document_id':'d','evidence':{'block_id':'b'}}],entities=[{'id':'e','identity_id':None}],identities=[{'id':'i','status':'candidate'}],identity_links=[{'mention_id':'m','identity_id':'i','review':'pending'}])
        return b,d
    def test_existing_facts_and_edges_immutable(self):
        b,d=self.fixtures();original=copy.deepcopy(b);out=merge(b,d)
        self.assertEqual(b,original);self.assertEqual(out['facts'],b['facts']);self.assertEqual(out['edges'],b['edges']);self.assertEqual(len(out['mentions']),1)
    def test_candidate_cannot_claim_reviewed_identity(self):
        b,d=self.fixtures();d['identity_links'][0]['review']='reviewed'
        with self.assertRaises(ValueError):merge(b,d)
    def test_source_mismatch_rejected(self):
        b,d=self.fixtures();d['blocks'][0]['text']='changed'
        with self.assertRaises(ValueError):merge(b,d)
    def test_queue_does_not_generate_edges(self):
        b,d=self.fixtures();queue=relation_queue(b,d)
        self.assertEqual(queue[0]['existing_fact_ids'],['f']);self.assertEqual(queue[0]['review'],'pending');self.assertNotIn('edges',queue[0])

if __name__=='__main__':unittest.main()
