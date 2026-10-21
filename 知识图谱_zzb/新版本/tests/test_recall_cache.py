import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from quality_recall import cached_request
from batch_extract import write
import hashlib

class RecallCacheTests(unittest.TestCase):
    def test_changed_existing_facts_and_model_are_not_reused(self):
        with tempfile.TemporaryDirectory() as d:
            batch=[{"unit_id":"u"}];a={"model":"m","facts":["a"]}
            ident,path=cached_request(d,batch,a);write(path,{"candidates":[]})
            self.assertEqual(cached_request(d,batch,a)[1],path)
            self.assertNotEqual(cached_request(d,batch,{**a,"facts":["b"]})[0],ident)
            self.assertNotEqual(cached_request(d,batch,{**a,"model":"other"})[0],ident)
    def test_legacy_requires_identical_request(self):
        with tempfile.TemporaryDirectory() as d:
            batch=[{"unit_id":"u"}];payload={"model":"m","facts":["a"]}
            legacy=hashlib.sha256(b"u").hexdigest()[:16]
            write(Path(d)/(legacy+".json"),{"candidates":[]})
            write(Path(d)/(legacy+".request.json"),{**payload,"facts":["old"]})
            self.assertFalse(cached_request(d,batch,payload)[1].exists())
            write(Path(d)/(legacy+".request.json"),payload)
            self.assertTrue(cached_request(d,batch,payload)[1].exists())
