import sys, unittest, tempfile, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from entity_extract_pilot import ground,locate,SCHEMA
from jsonschema import Draft202012Validator

def entity(**changes):
    x={"name":"polyethylene glycol","source_id":"b1","category":"chemical","kind":"polymer",
       "aliases":[{"surface":"PEG","source_id":"b1"}],
       "distinctions":[{"kind":"molecular_weight","value":"6000","source_id":"b1"}]}
    x.update(changes);return x
class EntityPilotTests(unittest.TestCase):
    segments=[{"source_id":"b1","text":"polyethylene glycol (PEG, mol. wt. 6000)"}]
    def test_exact_offsets_reconstruct_source(self):
        accepted,rejected=ground({"entities":[entity()]},self.segments)
        self.assertFalse(rejected)
        for a in accepted[0]["anchors"].values():
            self.assertEqual(self.segments[0]["text"][a["start"]:a["end"]],a["quote"])
    def test_wrong_source_is_rejected(self):
        a,q=ground({"entities":[entity(source_id="b2")]},self.segments)
        self.assertFalse(a);self.assertEqual(q[0]["issues"][0]["field"],"name")
    def test_invented_alias_is_rejected(self):
        a,q=ground({"entities":[entity(aliases=[{"surface":"PEO","source_id":"b1"}])]},self.segments)
        self.assertFalse(a);self.assertTrue(q)
    def test_invented_specification_is_rejected(self):
        a,q=ground({"entities":[entity(distinctions=[{"kind":"molecular_weight","value":"10000","source_id":"b1"}])]},self.segments)
        self.assertFalse(a);self.assertTrue(q)
    def test_invalid_category_schema(self):
        errors=list(Draft202012Validator(SCHEMA).iter_errors({"entities":[entity(category="suppressor")],"unresolved_names":[]}))
        self.assertTrue(errors)
    def test_no_automatic_chemical_name_normalization(self):
        self.assertIsNone(locate("CuSO4","b1",{"b1":"CuSO_4"}))
class IdentityBoundaryTests(unittest.TestCase):
    def test_approved_group_cannot_override_specification(self):
        from finalize_entity_pilot import identity_key
        self.assertNotEqual(identity_key(entity(),"same"),identity_key(entity(distinctions=[]),"same"))
    def test_formula_case_is_not_normalized(self):
        from finalize_entity_pilot import identity_key
        self.assertNotEqual(identity_key(entity(name="Co")),identity_key(entity(name="CO")))
    def test_nonchemical_ocr_whitespace_recovers_original(self):
        a,q=ground({"entities":[entity(name="photoelectron spectroscopy",category="method",kind="not_chemical",aliases=[],distinctions=[])]},[{"source_id":"b1","text":"photoelectron spec troscopy"}])
        self.assertFalse(q);self.assertEqual(a[0]["name"],"photoelectron spec troscopy")
        self.assertEqual(a[0]["canonical_name"],"photoelectron spectroscopy")
    def test_chemical_formula_whitespace_is_not_repaired(self):
        a,q=ground({"entities":[entity(name="CoSO4",aliases=[],distinctions=[])]},[{"source_id":"b1","text":"CoSO 4"}])
        self.assertTrue(q);self.assertFalse(a)
    def test_general_rules_no_entity_specific_case(self):
        from entity_pilot_review import flags
        self.assertIn("process_classification",flags(entity(name="electroplating",category="method",kind="not_chemical",aliases=[],distinctions=[])))
        self.assertIn("alias_definition_missing",flags(entity()))
    def test_alias_evidence_must_be_literal(self):
        a,q=ground({"entities":[entity(aliases=[{"surface":"PEG","source_id":"b1","basis_quote":"invented definition"}])]},EntityPilotTests.segments)
        self.assertTrue(q)
    def test_different_polymer_molecular_weights_remain_distinct(self):
        from finalize_entity_pilot import identity_key
        a=entity();b=entity(distinctions=[{"kind":"molecular_weight","value":"10000","source_id":"b1"}])
        self.assertNotEqual(identity_key(a),identity_key(b))
    def test_generic_and_specified_polymer_remain_distinct(self):
        from finalize_entity_pilot import identity_key
        self.assertNotEqual(identity_key(entity()),identity_key(entity(distinctions=[])))
    def test_source_explicit_alias_group_can_link_two_names(self):
        from finalize_entity_pilot import identity_key
        self.assertEqual(identity_key(entity(name="full name"),"approved"),identity_key(entity(name="short name"),"approved"))

class CacheAndFailureTests(unittest.TestCase):
    def test_cache_replays_without_network_and_rejects_changed_processing(self):
        import entity_extract_pilot as module
        from unittest.mock import patch
        task={"task_id":"unit","document_id":"unit_doc","segments":EntityPilotTests.segments,"target_names":[]}
        config={"model":"unit_model","base_url":"https://unit.invalid"}
        response={"choices":[{"message":{"content":json.dumps({"entities":[entity()],"unresolved_names":[]})},"finish_reason":"stop"}],"usage":{"total_tokens":1}}
        with tempfile.TemporaryDirectory() as folder,patch.object(module,"request_json",return_value=(response,0)) as api:
            first=module.run(task,config,Path(folder));second=module.run(task,config,Path(folder))
            self.assertEqual(first,second);self.assertEqual(api.call_count,1)
            with patch.object(module,"processing_fingerprint",return_value="changed"):
                with self.assertRaises(ValueError):module.run(task,config,Path(folder))
    def test_failed_request_preserves_failure_without_success_cache(self):
        import entity_extract_pilot as module
        from extraction_llm import ExtractionAPIError
        from unittest.mock import patch
        task={"task_id":"unit","document_id":"unit_doc","segments":[],"target_names":[]}
        with tempfile.TemporaryDirectory() as folder,patch.object(module,"request_json",side_effect=ExtractionAPIError("HTTP 400")):
            result=module.run(task,{"model":"unit_model","base_url":"https://unit.invalid"},Path(folder))
            self.assertIn("error",result)
            self.assertTrue(list((Path(folder)/"responses/unit").glob("failure_*.json")))
            self.assertFalse((Path(folder)/"responses/unit/result.json").exists())
if __name__=="__main__":unittest.main()
