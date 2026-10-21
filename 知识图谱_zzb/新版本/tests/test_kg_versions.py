import sys,json,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import kg_versions as versions

class VersionTests(unittest.TestCase):
    def setup_project(self,root):
        graph={key:[] for key in versions.COLLECTIONS};graph['schema_version']='test-schema'
        for spec in versions.SPECS:versions.save(root/spec['source'],graph)
        versions.save(root/'reports/full_extraction_20261020/quality/precision_graph.json',graph)
        versions.save(root/'reports/entity_corpus_reuse_20261021/normalized/candidate_delta.json',graph)
    def test_two_versions_and_current(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.setup_project(root);versions.initialize(root)
            result=versions.check(root);self.assertTrue(result['valid']);self.assertEqual(result['versions'],2)
            self.assertEqual(versions.load(root/'CURRENT.json')['current_version_id'],'kg-v2-entity-20261021')
    def test_cannot_overwrite_registered_versions(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.setup_project(root);versions.initialize(root)
            with self.assertRaises(ValueError):versions.initialize(root)
    def test_mutated_snapshot_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.setup_project(root);versions.initialize(root)
            p=root/'versions/v1_direct_extraction/knowledge_graph.json';p.write_text(p.read_text()+' ',encoding='utf-8')
            self.assertFalse(versions.check(root)['valid'])
    def test_wrong_current_pointer_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.setup_project(root);versions.initialize(root)
            current=versions.load(root/'CURRENT.json');current['sha256']='wrong';versions.save(root/'CURRENT.json',current)
            self.assertFalse(versions.check(root)['valid'])
    def test_paths_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):versions.within(Path(d),'../outside.json')

if __name__=='__main__':unittest.main()
