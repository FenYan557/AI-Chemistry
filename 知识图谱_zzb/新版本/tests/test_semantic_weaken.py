import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from semantic_weaken import weaken

class SemanticWeakeningTests(unittest.TestCase):
    def test_protocol_downgrade_never_changes_source_values(self):
        raw={"subject":"CV test","relation":"measurement","statement":"observation","quote":"The scan range is -0.8 to 0.4 V and scanning speed is 0.01 V/s.","conditions":[{"value":"0.01 V/s"}]}
        new,flags=weaken(raw,raw["quote"])
        self.assertEqual(new["relation"],"other");self.assertEqual(new["statement"],"reported_claim")
        self.assertEqual(new["quote"],raw["quote"]);self.assertEqual(new["conditions"],raw["conditions"])

    def test_real_observation_not_downgraded_due_to_protocol_words(self):
        raw={"subject":"film","relation":"measurement","statement":"observation","quote":"At a scan rate of 1 V/s a new peak was observed."}
        self.assertFalse(weaken(raw,raw["quote"])[1])

    def test_correlation_does_not_generate_effect_edge(self):
        raw={"subject":"indicator","relation":"effect","statement":"author_interpretation","quote":"The indicator correlates with performance."}
        self.assertEqual(weaken(raw,raw["quote"])[0]["relation"],"other")

    def test_section_plan_and_true_future_work_distinguished(self):
        raw={"subject":"MD","relation":"future_work","statement":"future_work","quote":"采用MD计算"}
        self.assertEqual(weaken(raw,"上一节已经讨论，下一节采用MD计算")[0]["statement"],"reported_claim")
        self.assertFalse(weaken(raw,"未来有必要采用MD计算验证该预测")[1])

if __name__=="__main__":unittest.main()
