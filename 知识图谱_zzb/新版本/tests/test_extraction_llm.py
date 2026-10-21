"""Credential isolation and safe API failure handling; no real key or network."""
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extraction_llm import ExtractionAPIError, load_config, request_json, parse_extraction


class DedicatedExtractionTests(unittest.TestCase):
    def test_missing_config_does_not_fall_back_to_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict("os.environ", {"OPENAI_API_KEY": "other-credential"}):
                with self.assertRaises(ExtractionAPIError):
                    load_config(Path(folder) / "missing.json")

    def test_override_changes_model_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({"api_key": "dedicated-test-key", "base_url": "https://example.invalid/v1",
                                        "model": "old"}), encoding="utf-8")
            config = load_config(path, "chosen")
            self.assertEqual(config["api_key"], "dedicated-test-key")
            self.assertEqual(config["model"], "chosen")
            self.assertEqual(json.loads(path.read_text())["model"], "old")

    def test_http_error_never_exposes_server_body_or_key(self):
        config = {"api_key": "dedicated-test-key", "base_url": "https://example.invalid/v1"}
        error = urllib.error.HTTPError("https://example.invalid/v1", 401, "dedicated-test-key",
                                       {}, io.BytesIO(b"dedicated-test-key"))
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ExtractionAPIError) as caught:
                request_json(config, "/models")
        self.assertEqual(str(caught.exception), "抽取API返回HTTP 401")
        self.assertNotIn(config["api_key"], str(caught.exception))

    def test_invalid_schema_not_imported(self):
        with self.assertRaises(ExtractionAPIError):
            parse_extraction('{"facts":[{"subject":"ADO"}]}')
        self.assertEqual(parse_extraction('{"facts":[]}'), {"facts": []})


if __name__ == "__main__":
    unittest.main()
