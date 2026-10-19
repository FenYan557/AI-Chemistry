"""在临时目录复跑阶段二，比较全部 blocks/meta、tables 和 chunks；不覆盖正式数据。"""
import contextlib
import csv
import io
import json
from pathlib import Path
import sys
import tempfile

import clean
import chunk

BASE = Path(__file__).resolve().parents[2]
PUBLISHED = BASE / "02_清洗/out"


def content(path):
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f))
    return path.read_bytes()


def main():
    differences, checked = [], 0
    with tempfile.TemporaryDirectory(prefix="chemistry-stage2-") as temporary:
        out = Path(temporary)
        clean.OUT = out
        chunk.OUT = out
        chunk.BLOCKS = out / "blocks"
        chunk.CHUNKS = out / "chunks"
        chunk.REPORT = out / "report"
        with contextlib.redirect_stdout(io.StringIO()):
            clean.main()
            chunk.main()
        for sub in ("blocks", "tables", "chunks"):
            expected = {p.name for p in (PUBLISHED / sub).iterdir() if p.is_file()}
            generated = {p.name for p in (out / sub).iterdir() if p.is_file()}
            if expected != generated:
                differences.append({"directory": sub, "missing": sorted(expected - generated),
                                    "extra": sorted(generated - expected)})
            for name in sorted(expected & generated):
                checked += 1
                if content(PUBLISHED / sub / name) != content(out / sub / name):
                    differences.append({"file": sub + "/" + name, "reason": "content differs"})
    result = {"status": "passed" if not differences else "failed",
              "scope": "stage two from bundled repaired data and repository source directories",
              "files_compared": checked, "differences": differences,
              "stage_one_ocr_rerun": False}
    (PUBLISHED / "report/reproducibility.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if differences else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
