import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from batch_extract import Engine, empty_bundle, prepare, semantic_flags, split_ranges, write, read

DOC = {"id": "test", "title": "Test", "source_file": "test.jsonl", "sha256": "a"*64, "source_kind": "cleaned_text"}
FACT = {"subject": "A", "target": "B", "relation": "effect", "statement": "observation", "quote": "A inhibits B."}

def unit(ident):
    return {"block": {"id": ident, "document_id": "test", "page": 1, "section": "Results", "text": "A inhibits B."},
            "origin": {"source_block_id": ident, "kind": "text"}, "context": ""}

def manifest(units):
    return {"version": "test", "input_fingerprint": "fixed", "documents": [
        {"key": "test", "document": DOC, "units": units}],
        "skipped_source_blocks": [], "visual_inventory": []}


class BatchTests(unittest.TestCase):
    def test_split_keeps_all_original_characters(self):
        text = ("A long result.\nAnother result; more text. " * 120)
        ranges = list(split_ranges(text, 120))
        self.assertEqual("".join(text[a:b] for a,b in ranges), text)
        self.assertTrue(all(b-a <= 120 for a,b in ranges))

    def test_prepare_preserves_table_rows_and_defers_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"blocks").mkdir(); (root/"tables").mkdir()
            rows = [
                {"block_id":"h", "type":"heading", "page":1,"section":"Results","text":"Results"},
                {"block_id":"t", "type":"table", "page":1,"section":"Results","caption":"Table 1","csv":"tables/t.csv","header_levels":1},
                {"block_id":"i", "type":"image", "page":1,"section":"Results","caption":"","img":"figure.jpg"},
                {"block_id":"r", "type":"text", "page":2,"section":"References","text":"A bibliographic record."}]
            (root/"tables/t.csv").write_text("Case,Value\n1,10\n2,20\n3,30\n4,40\n5,50\n",encoding="utf-8")
            (root/"blocks/p.jsonl").write_text("\n".join(json.dumps(x) for x in rows),encoding="utf-8")
            m = prepare(root, root/"run")
            units = m["documents"][0]["units"]
            self.assertEqual(len(units),2)
            self.assertIn("Case,Value", units[1]["block"]["text"])
            self.assertIn("5,50", units[1]["block"]["text"])
            self.assertEqual(units[1]["origin"]["data_lines"],[6,6])
            self.assertEqual(len(m["skipped_source_blocks"]),3)
            self.assertFalse(m["visual_inventory"][0]["image_pixels_extracted"])
            self.assertEqual(prepare(root, root/"run")["input_fingerprint"],m["input_fingerprint"])

    def test_retry_only_failed_unit_then_resume_does_not_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            units = [unit("b1"),unit("b2")]
            m = manifest(units)
            engine = Engine({"model":"test"},m,Path(folder),retries=1)
            answers = [
                ({"results":[{"unit_id":"b1","facts":[FACT]},
                              {"unit_id":"b2","facts":[{**FACT,"quote":"fabricated quote"}]}]},"r1"),
                ({"results":[{"unit_id":"b2","facts":[FACT]}]},"r2")]
            with patch.object(engine,"call",side_effect=answers) as call, patch("batch_extract.time.sleep"):
                engine.batch(m["documents"][0],units,{"terms":[]})
            self.assertEqual(call.call_count,2)
            retry_payload=json.loads(call.call_args_list[1].args[1][1]["content"])
            self.assertEqual([x["unit_id"] for x in retry_payload["units"]],["b2"])
            self.assertTrue(all(r["status"]=="success" for r in engine.results.values()))
            resumed=Engine({"model":"test"},m,Path(folder))
            self.assertEqual(len(resumed.results),2)

    def test_final_failure_keeps_valid_facts_with_partial_status(self):
        with tempfile.TemporaryDirectory() as folder:
            u=unit("b1"); m=manifest([u]); engine=Engine({"model":"test"},m,Path(folder),retries=0)
            answer=({"results":[{"unit_id":"b1","facts":[FACT,{**FACT,"quote":"not in source"}]}]},"r")
            with patch.object(engine,"call",return_value=answer):
                engine.batch(m["documents"][0],[u],{"terms":[]})
            self.assertEqual(engine.results["b1"]["status"],"partial")
            self.assertEqual(len(engine.results["b1"]["response"]["facts"]),1)
            self.assertTrue(engine.results["b1"]["errors"])

    def test_export_with_unprocessed_other_document(self):
        with tempfile.TemporaryDirectory() as folder:
            u=unit("b1"); m=manifest([u])
            m["documents"].append({"key":"other","document":{**DOC,"id":"other"},"units":[]})
            engine=Engine({"model":"test"},m,Path(folder))
            engine.save_unit(m["documents"][0],u,{"facts":[FACT]},"success")
            engine.export_document(m["documents"][0])
            result=engine.export_all()
            self.assertEqual(result["documents_in_graph"],1)
            self.assertTrue(result["bundle_valid"])

    def test_empty_extraction_is_valid_without_empty_kg_import(self):
        with tempfile.TemporaryDirectory() as folder:
            u=unit("b1"); m=manifest([u]); engine=Engine({"model":"test"},m,Path(folder))
            with patch.object(engine,"call",return_value=({"results":[{"unit_id":"b1","facts":[]}]},"r")):
                engine.batch(m["documents"][0],[u],{"terms":[]})
            self.assertEqual(engine.results["b1"]["status"],"empty")
            engine.export_document(m["documents"][0])
            status=read(Path(folder)/"documents/test.status.json")
            self.assertIsNone(status["valid"])

    def test_single_long_document_uses_multiple_worker_threads(self):
        import threading,time
        with tempfile.TemporaryDirectory() as folder:
            units=[unit("b"+str(i)) for i in range(20)]
            m=manifest(units);engine=Engine({"model":"test"},m,Path(folder),workers=3)
            threads=set()
            def fake_batch(doc,batch,glossary):
                threads.add(threading.current_thread().name)
                time.sleep(0.03)
                for u in batch:engine.save_unit(doc,u,{"facts":[FACT]},"success")
            with patch.object(engine,"glossary",return_value={"terms":[]}),patch.object(engine,"batch",side_effect=fake_batch),patch("builtins.print"):
                self.assertTrue(engine.execute())
            self.assertGreater(len(threads),1)
            self.assertEqual(len(engine.results),20)

    def test_model_change_cannot_mix_checkpoints(self):
        with tempfile.TemporaryDirectory() as folder:
            m=manifest([unit("b1")])
            Engine({"model":"one"},m,Path(folder))
            with self.assertRaises(ValueError):
                Engine({"model":"two"},m,Path(folder))

    def test_limit_and_mixed_concentration_flags(self):
        f={**FACT,"subject":"a mechanism","conditions":[{"value":"low"},{"value":"high"}]}
        flags=semantic_flags({"facts":[f]*8})
        reasons={x["reason"] for x in flags}
        self.assertIn("multiple_concentration_regimes_in_one_fact",reasons)
        self.assertIn("fact_limit_reached_check_coverage",reasons)

if __name__=="__main__":
    unittest.main()
