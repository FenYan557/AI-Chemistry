import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from knowledge_pipeline import reuse_checkpoints
from batch_extract import write,read

class ReuseTests(unittest.TestCase):
    def test_only_unchanged_documents_reuse_without_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            old,new=Path(folder)/"old",Path(folder)/"new"
            profile={"model":"m","enable_thinking":False,"protocol":"same"}
            doc={"key":"k","document":{"id":"d","sha256":"a"*64},"units":[{"block":{"id":"b"}}]}
            write(old/"profile.json",profile);write(old/"input_manifest.json",{"documents":[doc]})
            write(old/"units/b.json",{"unit_id":"b","document_id":"d","status":"success","response":{"facts":[]}})
            report=reuse_checkpoints(old,new,{"documents":[doc]},profile)
            self.assertEqual(report["unit_checkpoints_reused"],1)
            self.assertTrue((new/"units/b.json").exists())
            self.assertFalse((new/".local").exists())
            changed={**doc,"document":{"id":"d","sha256":"b"*64}}
            newer=Path(folder)/"newer"
            self.assertEqual(reuse_checkpoints(old,newer,{"documents":[changed]},profile)["unit_checkpoints_reused"],0)

    def test_protocol_change_cannot_reuse(self):
        with tempfile.TemporaryDirectory() as folder:
            old,new=Path(folder)/"old",Path(folder)/"new"
            write(old/"profile.json",{"model":"old","enable_thinking":False,"protocol":"v1"})
            with self.assertRaises(ValueError):
                reuse_checkpoints(old,new,{"documents":[]},{"model":"new","enable_thinking":False,"protocol":"v1"})

if __name__=="__main__":unittest.main()
