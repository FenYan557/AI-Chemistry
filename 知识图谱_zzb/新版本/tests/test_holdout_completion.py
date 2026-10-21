import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from finalize_quality import holdout_statistics
from quality_rules import dump_jsonl
from batch_extract import write
class HoldoutCompletionTests(unittest.TestCase):
 def test_partial_or_stale_review_not_complete(self):
  with tempfile.TemporaryDirectory() as d:
   dump_jsonl(Path(d)/"holdout_sample.jsonl",[{"id":"a","sampling_stratum":"AI"},{"id":"b","sampling_stratum":"AI"}])
   write(Path(d)/"holdout_review.json",{"reviews":[{"id":"a","verdict":"supported"}]})
   self.assertFalse(holdout_statistics(d,{"a","b"})["complete"])
   write(Path(d)/"holdout_review.json",{"reviews":[{"id":"a","verdict":"supported"},{"id":"b","verdict":"unsupported"}]})
   result=holdout_statistics(d,{"a","b"})
   self.assertTrue(result["complete"]);self.assertEqual(result["verdicts"]["unsupported"],1)
   self.assertFalse(holdout_statistics(d,{"a"})["complete"])
