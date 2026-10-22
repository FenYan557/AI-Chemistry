"""Shared offline runtime helpers; no model calls or credential dependencies."""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lexical(text, fold_natural=True):
    # Formatting changes only. Case folding of formulae/unknown acronyms is unsafe.
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"<sup>(.*?)</sup>", r"^\1", text)
    text = text.replace("−", "-").replace("–", "-").replace("‑", "-")
    text = re.sub(r"\s+", " ", text).strip()
    if fold_natural and re.fullmatch(r"[A-Za-z][A-Za-z -]{3,}", text) and re.search(r"[a-z]{3}", text):
        return text.casefold()
    return text
