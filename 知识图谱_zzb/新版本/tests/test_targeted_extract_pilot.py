import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from targeted_extract_pilot import anchor_issues,fingerprint
class TargetedPilotTests(unittest.TestCase):
 def test_literal_entities(self):
  d={"entities":[{"name":"Malachite green","aliases":["MG"],"quote":"Malachite green (MG)"}]}
  self.assertFalse(anchor_issues(d,["Malachite green (MG) was used."],"entities"))
 def test_invented_alias_rejected(self):
  d={"entities":[{"name":"MG","aliases":["guessed name"],"quote":"MG was used."}]}
  self.assertIn("alias_not_in_evidence",[e["issue"] for e in anchor_issues(d,["MG was used."],"entities")])
 def test_quote_and_number_locality(self):
  d={"cases":[{"conditions":[],"results":[{"value":"181.79","quote":"Resistance was 24.46 Ω."}]}]}
  self.assertIn("numeric_value_not_local",[e["issue"] for e in anchor_issues(d,["Resistance was 24.46 Ω."],"cases")])
  d["cases"][0]["results"][0]["quote"]="invented"
  self.assertIn("quote_not_literal",[e["issue"] for e in anchor_issues(d,["Resistance was 24.46 Ω."],"cases")])
 def test_atomic_rejects_conflicting_concentrations(self):
  d={"cases":[{"conditions":[{"parameter":"concentration","owner":"MTT","value":"0 mg/L","quote":"MTT 0 mg/L"},{"parameter":"concentration","owner":"MTT","value":"60 mg/L","quote":"MTT 60 mg/L"}],"results":[{"value":"181.79","quote":"181.79"}]}]}
  self.assertIn("conflicting_concentrations_in_single_case",[e["issue"] for e in anchor_issues(d,["MTT 0 mg/L, MTT 60 mg/L, 181.79"],"cases",atomic=True)])
 def test_atomic_schema_allows_unknown_recipe_amount(self):
  from targeted_extract_pilot import ATOMIC_SCHEMA
  from jsonschema import Draft202012Validator
  d={"recipes":[{"components":[{"name":"MTT","amount":None,"unit":None,"quote":"MTT"}],"context_quote":"MTT"}],"methods":[],"cases":[],"interpretations":[]}
  self.assertFalse(list(Draft202012Validator(ATOMIC_SCHEMA).iter_errors(d)))
 def test_cache_depends_on_full_input(self):
  self.assertNotEqual(fingerprint({"source":"a","prompt":"x"}),fingerprint({"source":"b","prompt":"x"}))
  self.assertNotEqual(fingerprint({"source":"a","prompt":"x"}),fingerprint({"source":"a","prompt":"y"}))
