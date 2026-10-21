import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from quality_rules import triage,select_audit,fid
from quality_verify import initial_decisions,manual_sample,Verifier,export_curated
from quality_controls import controls
from batch_extract import empty_bundle,write
from extraction import ingest

RAW={"subject":"A","target":"B","relation":"effect","statement":"observation","quote":"A inhibits B."}
def row(ident="f:1"):
    return {"id":ident,"unit_id":"b","document_id":"d","title":"test","source":"A inhibits B.","raw":copy.deepcopy(RAW),"origin_kind":"text"}

class QualityTests(unittest.TestCase):
    def test_quote_presence_does_not_hide_reversed_effect(self):
        r=row();r["raw"]["outcomes"]=[{"indicator":"effect","value":"inhibition","quote":"inhibits B","kind":"qualitative","direction":"increase"}]
        self.assertIn("possible_direction_mismatch",triage(r)["reasons"])

    def test_proposed_not_direct_observation(self):
        r=row();r["source"]=r["raw"]["quote"]="A mechanism was proposed for A and B."
        self.assertIn("certainty_or_statement_type",triage(r)["reasons"])

    def test_simple_numeric_measurement_can_be_low_risk_not_proven_gold(self):
        r=row();r["source"]="The resistivity of film A was 14.4 μΩ·cm."
        r["raw"]={"subject":"film A","relation":"measurement","statement":"observation","quote":r["source"],
            "outcomes":[{"indicator":"resistivity","value":"14.4","unit":"μΩ·cm","kind":"numeric","quote":"14.4 μΩ·cm"}]}
        self.assertEqual(triage(r)["tier"],"low_risk")
        r["raw"]["outcomes"][0]["value"]="1440"
        self.assertIn("numeric_value_not_local_to_evidence",triage(r)["reasons"])

    def test_low_risk_audit_random_and_repeatable(self):
        rows=[]
        for i in range(200):
            r=row(str(i));r["rule"]={"tier":"low_risk"};rows.append(r)
        self.assertEqual(select_audit(rows),select_audit(rows))
        self.assertEqual(len(select_audit(rows)[1]),120)

    def test_unknown_quarantined_and_manual_packet_blinded(self):
        with tempfile.TemporaryDirectory() as d:
            rows=[row("f:1"),row("f:2")]
            for r in rows:r["rule"]={"tier":"semantic_check"}
            decisions=initial_decisions(rows,{"f:1":{"verdict":"supported"},"f:2":{"verdict":"unclear"}})
            self.assertEqual(decisions["f:2"]["decision"],"quarantine")
            manual_sample(rows,decisions,d)
            blind=[json.loads(x) for x in (Path(d)/"manual_blind.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(all("rule" not in x and "sample_stratum" not in x and "decision" not in x for x in blind))

    def test_ai_cannot_override_unanchored_baseline(self):
        r=row();r["raw"]["outcomes"]=[{"indicator":"measurement","value":"14.4","quote":"A inhibits B.","kind":"numeric","baseline":"3","baseline_quote":"A inhibits B."}]
        r["rule"]=triage(r)
        decisions=initial_decisions([r],{r["id"]:{"verdict":"supported"}})
        self.assertEqual(decisions[r["id"]]["decision"],"quarantine")

    def test_controls_do_not_expose_gold_in_api_cases(self):
        rows,gold=controls()
        self.assertEqual(len(rows),14)
        self.assertTrue(all("expected" not in r for r in rows))
        self.assertTrue(all(not r["id"].startswith(("control:P","control:N")) for r in rows))
        self.assertEqual(sum(x["expected"]=="supported" for x in gold.values()),4)

    def test_fid_matches_existing_importer(self):
        doc={"id":"d","title":"D","source_file":"x","sha256":"a"*64,"source_kind":"cleaned_text"}
        b={"id":"b","document_id":"d","page":1,"section":"Results","text":"A inhibits B."}
        bundle=ingest(empty_bundle(doc,[b]),"b",{"facts":[RAW]},"test")
        self.assertEqual(bundle["facts"][0]["id"],fid("b",RAW))

    def test_only_failed_judgment_ids_are_retried(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("quality_verify.load_config",return_value={"model":"test","api_key":"fake","base_url":"https://example.invalid/v1"}):
                v=Verifier(d,"test")
            rows=[row("f:1"),row("f:2")]
            answer1=({"f:1":{"id":"f:1","verdict":"supported","issues":[],"reason":"source"}},"r1")
            answer2=({"f:2":{"id":"f:2","verdict":"unclear","issues":[],"reason":"unknown"}},"r2")
            with patch.object(v,"call",side_effect=[answer1,answer2]) as api:
                v.batch(rows)
            self.assertEqual([x["id"] for x in api.call_args_list[1].args[0]],["f:2"])
            self.assertEqual(len(v.decisions),2)

if __name__=="__main__":unittest.main()
