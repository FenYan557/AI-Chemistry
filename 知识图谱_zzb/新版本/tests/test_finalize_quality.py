import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from batch_extract import empty_bundle,write,read
from extraction import ingest
from quality_rules import fid,dump_jsonl,triage
from finalize_quality import merge,make_holdout

class FinalizeTests(unittest.TestCase):
    def fixture(self,root):
        doc={"id":"d","title":"D","source_file":"source","sha256":"a"*64,"source_kind":"cleaned_text"}
        block={"id":"b","document_id":"d","page":1,"section":"Results","text":"A inhibits B. C affects D."}
        f1={"subject":"A","target":"B","relation":"effect","statement":"observation","quote":"A inhibits B."}
        f2={"subject":"C","target":"D","relation":"effect","statement":"observation","quote":"C affects D."}
        graph=ingest(empty_bundle(doc,[block]),"b",{"facts":[f1,f2]},"test")
        write(root/"knowledge_graph.json",graph)
        rows=[]
        for f in (f1,f2):
            r={"id":fid("b",f),"unit_id":"b","document_id":"d","source":block["text"],"raw":f}
            r["rule"]=triage(r);rows.append(r)
        dump_jsonl(root/"quality/cases.jsonl",rows)
        write(root/"quality/AI_phase_complete.json",{"complete":True})
        write(root/"quality/decisions.json",{
            rows[0]["id"]:{"id":rows[0]["id"],"decision":"accept","method":"AI"},
            rows[1]["id"]:{"id":rows[1]["id"],"decision":"quarantine","method":"AI"}})
        return rows

    def test_primary_can_restore_true_fact_and_remove_false_one(self):
        with tempfile.TemporaryDirectory() as folder:
            r=Path(folder);rows=self.fixture(r)
            write(r/"quality/holdout_review.json",{"reviews":[{"id":rows[0]["id"],"verdict":"unsupported","reason":"test rejection"}]})
            write(r/"quality/uncertain_review.json",{"reviews":[{"id":rows[1]["id"],"verdict":"supported","reason":"source supports","evidence_quote":"C affects D."}]})
            result=merge(r)
            self.assertEqual(result["accepted_total"],1)
            graph=read(r/"quality/precision_graph.json")
            self.assertEqual(graph["facts"][0]["id"],rows[1]["id"])
            self.assertEqual({m["surface"] for m in graph["mentions"]},{"C","D"})

    def test_holdout_is_not_resampled_after_labels_arrive(self):
        with tempfile.TemporaryDirectory() as folder:
            rows=[{"id":str(i),"unit_id":str(i),"document_id":"d","source":"source","raw":{},"acceptance_method":"AI"} for i in range(40)]
            make_holdout(rows,set(),folder)
            before=(Path(folder)/"holdout_blind.jsonl").read_bytes()
            make_holdout(rows[:5],set(),folder)
            self.assertEqual(before,(Path(folder)/"holdout_blind.jsonl").read_bytes())

    def test_primary_source_quote_must_be_verbatim(self):
        with tempfile.TemporaryDirectory() as folder:
            r=Path(folder);rows=self.fixture(r)
            write(r/"quality/uncertain_review.json",{"reviews":[{"id":rows[1]["id"],"verdict":"supported","reason":"fake evidence","evidence_quote":"not in source"}]})
            with self.assertRaises(ValueError):merge(r)

if __name__=="__main__":unittest.main()
