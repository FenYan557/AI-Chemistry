import sys,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import entity_corpus_reuse as reuse

class CorpusReuseTests(unittest.TestCase):
    def test_material_and_ion_separate(self):
        self.assertEqual(reuse.classify("cobalt film")[0:2],("material","not_chemical"))
        self.assertEqual(reuse.classify("Co 2+")[0:2],("chemical","metal_ion"))
        self.assertEqual(reuse.classify("Cl -")[1],"nonmetal_ion")
    def test_equipment_not_method(self):
        self.assertEqual(reuse.classify("optical microscope")[0],"equipment")
        self.assertEqual(reuse.classify("scanning electron microscopy")[0],"method")
    def test_source_quote_required(self):
        b={"id":"b","document_id":"d","text":"PEG, grade 6000"}
        self.assertIsNone(reuse.anchor("PEG",b,"invented PEG"))
        self.assertIsNone(reuse.anchor("PEO",b))
    def test_dedup_occurrence_preserves_provenance(self):
        b={"id":"b","document_id":"d","text":"Co foil"};pool={}
        reuse.pool_add(pool,"d",b,"Co foil",{"artifact":"raw"})
        reuse.pool_add(pool,"d",b,"Co foil",{"artifact":"curated"})
        self.assertEqual(len(pool),1);self.assertEqual(len(next(iter(pool.values()))["provenance"]),2)
    def test_primary_review_not_overridden_by_completion(self):
        b={"id":"b","document_id":"d","text":"Co foil"};pool={}
        good={"category":"material","kind":"not_chemical","aliases":[],"distinctions":[]}
        reuse.pool_add(pool,"d",b,"Co foil",{},entity=good,primary=True)
        bad={**good,"category":"chemical","kind":"metal_ion"}
        reuse.pool_add(pool,"d",b,"Co foil",{},entity=bad)
        self.assertEqual(next(iter(pool.values()))["category"],"material")
    def test_foreign_document_not_accepted(self):
        pool={};self.assertIsNone(reuse.pool_add(pool,"d2",{"id":"b","document_id":"d1","text":"Co"},"Co",{}))
        self.assertFalse(pool)
    def test_invented_addition_quarantined(self):
        task={"candidates":[],"segments":[{"source_id":"b","text":"PEG"}]}
        data={"updates":[],"not_entities":[],"coverage_notes":"","additions":[{"name":"PEO","source_id":"b","category":"chemical","kind":"polymer","aliases":[],"distinctions":[]}]}
        error,good,bad=reuse.valid_response(data,task)
        self.assertIsNone(error);self.assertFalse(good);self.assertTrue(bad)
    def test_unknown_candidate_id_rejected(self):
        data={"updates":[],"not_entities":[{"id":"foreign","reason":"x"}],"additions":[],"coverage_notes":""}
        self.assertIsNotNone(reuse.valid_response(data,{"candidates":[],"segments":[]})[0])
    def test_cache_uses_no_second_call(self):
        task={"task_id":"t","document_id":"d","source_fingerprint":"source","candidates":[],"segments":[],"covered_names":[]}
        data={"updates":[],"not_entities":[],"additions":[],"coverage_notes":""}
        response={"model":"unit","usage":{"total_tokens":2},"choices":[{"finish_reason":"stop","message":{"content":json.dumps(data)}}]}
        with tempfile.TemporaryDirectory() as d,patch.object(reuse,"request_json",return_value=(response,0)) as api:
            config={"model":"unit","base_url":"https://unit.invalid"}
            a=reuse.execute_task(task,config,Path(d));b=reuse.execute_task(task,config,Path(d))
            self.assertEqual(a,b);self.assertEqual(api.call_count,1)
            with self.assertRaises(ValueError):reuse.execute_task({**task,"source_fingerprint":"changed"},config,Path(d))

if __name__=="__main__":unittest.main()
