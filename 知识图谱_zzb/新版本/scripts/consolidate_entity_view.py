"""Aggressive, reversible entity catalogue; never rewrites graph identity or fact endpoints."""
import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "entity-catalogue-1"


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def save(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fingerprint(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def key(s):
    # Preserve charge, hydration, digits, case and formula spelling. No OCR repair.
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip()


def shorthand(s):
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,11}", s)) and not bool(re.search(r"[a-z]{3,}", s))


def slot(document, label):
    return (document if shorthand(key(label)) else "*", key(label))


class Union:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def build(g):
    mentions = {m["id"]: m for m in g["mentions"]}
    blocks = {b["id"]: b for b in g["blocks"]}
    identities = {i["id"]: i for i in g["identities"]}
    per_block = defaultdict(list)
    for m in mentions.values():
        per_block[m["evidence"].get("block_id")].append(m)
    union, alias_evidence = Union(), []
    for m in mentions.values():
        union.find(slot(m["document_id"], m["surface"]))
    # Existing pool provides names; original definitions provide the actual alias evidence.
    # Bracket matching supports abbreviations only, never specifications as aliases.
    for bid, ms in sorted(per_block.items()):
        b = blocks.get(bid)
        if not b:
            continue
        text, doc = b["text"], b["document_id"]
        names = {m["surface"] for m in ms if 4 <= len(m["surface"]) <= 180 and not shorthand(m["surface"])}
        names.update(i["canonical_label"] for i in identities.values() if i.get("document_id") == doc
                     and 4 <= len(i["canonical_label"]) <= 180 and not shorthand(i["canonical_label"]))
        for match in re.finditer(r"[（(]\s*(?:named\s+)?([A-Za-z][A-Za-z0-9-]{0,11})\s*[)）]", text):
            abbr = match.group(1)
            if not shorthand(abbr):
                continue
            prefix = text[:match.start()].rstrip()
            matches = [n for n in names if prefix.endswith(n)]
            if not matches:
                continue
            full = max(matches, key=len)
            start = len(prefix) - len(full)
            ev = {"kind": "block", "block_id": bid, "start": start, "end": match.end(), "quote": text[start:match.end()]}
            alias_evidence.append({"document_id": doc, "name": full, "alias": abbr, "evidence": ev,
                                   "basis": "literal_parenthetical_definition", "human_review": "pending"})
    # Non-abbreviation aliases already identified by extraction must name both sides
    # in one direct parenthetical definition; author_explicit alone is insufficient.
    skipped = []
    for link in g["identity_links"]:
        ident, m = identities[link["identity_id"]], mentions[link["mention_id"]]
        a, b = m["surface"], ident["canonical_label"]
        if key(a) == key(b) or link["basis"] != "author_explicit":
            continue
        valid = []
        for ev in link["evidence"]:
            block = blocks.get(ev.get("block_id"))
            if not block or block["document_id"] != m["document_id"] or block["text"][ev.get("start", 0):ev.get("end", 0)] != ev.get("quote"):
                continue
            q = ev["quote"]
            patterns = [re.escape(a) + r"\s*[（(]\s*(?:named\s+)?" + re.escape(b) + r"\s*[)）]",
                        re.escape(b) + r"\s*[（(]\s*(?:named\s+)?" + re.escape(a) + r"\s*[)）]"]
            if any(re.search(p, q) for p in patterns):
                valid.append(ev)
        if valid and not any(ident.get("distinctions", {}).values()):
            alias_evidence.append({"document_id": m["document_id"], "name": b, "alias": a, "evidence": valid[0],
                                   "basis": "rechecked_existing_author_definition", "human_review": "pending"})
        elif not valid:
            skipped.append({"mention_id": m["id"], "identity_id": ident["id"], "reason": "author_explicit_label_without_direct_definition"})
    # An acronym can name incompatible materials even within a review article.
    # Resolve all definitions before union so a shared acronym cannot bridge them.
    definitions = defaultdict(set)
    unique = {}
    for a in alias_evidence:
        if shorthand(a["name"]) and not shorthand(a["alias"]):
            a["name"], a["alias"] = a["alias"], a["name"]
        n = key(a["name"])
        natural_case = n.casefold() if re.fullmatch(r"[A-Za-z -]+", n) and " " in n else n
        definitions[(a["document_id"], a["alias"])].add(natural_case)
        unique[(a["document_id"], a["name"], a["alias"], fingerprint(a["evidence"]))] = a
    alias_evidence = list(unique.values())
    ambiguous = {k for k, names in definitions.items() if len(names) > 1}
    for a in alias_evidence:
        conflict = (a["document_id"], a["alias"]) in ambiguous
        a["candidate_action"] = "ambiguous_definition_not_merged" if conflict else "grouped_as_pending_candidate"
        if not conflict:
            union.join(slot(a["document_id"], a["name"]), slot(a["document_id"], a["alias"]))
    # Same literal names are grouped aggressively. Known identity distinctions and
    # declared types remain separate candidate partitions, never discarded.
    links_by_mention = defaultdict(list)
    for link in g["identity_links"]:
        links_by_mention[link["mention_id"]].append(link)
    buckets = defaultdict(list)
    for m in mentions.values():
        distinctions = sorted({json.dumps(identities[l["identity_id"]].get("distinctions", {}), sort_keys=True, ensure_ascii=False)
                               for l in links_by_mention[m["id"]] if any(identities[l["identity_id"]].get("distinctions", {}).values())})
        signature = (union.find(slot(m["document_id"], m["surface"])), tuple(distinctions), tuple(sorted(m.get("candidate_type_ids", []))))
        buckets[signature].append(m)
    candidates, mapping = [], []
    for (root, distinctions, types), ms in sorted(buckets.items()):
        labels = Counter(m["surface"] for m in ms)
        iid = "candidate-group:" + fingerprint([root, distinctions, types])[:20]
        canonical = root[1]
        candidates.append({"id": iid, "label": canonical, "observed_labels": dict(sorted(labels.items())),
            "document_ids": sorted({m["document_id"] for m in ms}), "mention_ids": sorted(m["id"] for m in ms),
            "source_identity_ids": sorted({l["identity_id"] for m in ms for l in links_by_mention[m["id"]]}),
            "distinctions": [json.loads(d) for d in distinctions], "declared_type_ids": list(types),
            "scope": "document_shorthand" if root[0] != "*" else "cross_document_literal_or_defined_alias",
            "semantic_status": "retrieval_candidate_not_confirmed_identity", "human_review": "pending"})
        mapping.extend({"mention_id": m["id"], "candidate_group_id": iid} for m in ms)
    # Display cards deliberately collapse same-name partitions, including acronyms,
    # but retain partitions and do not propagate chemical identity or graph facts.
    display = defaultdict(list)
    for c in candidates:
        label = c["label"]
        # A numeric suffix/parenthetical is a family navigation key, not an alias.
        base = re.sub(r"[- ]\d+(?:\s*[-–]\s*\d+)?$", "", label)
        base = re.sub(r"\s*[（(][^()（）]*\d[^()（）]*[)）]$", "", base).strip() or label
        display[base].append(c)
    cards = [{"id": "catalogue:" + fingerprint(label)[:20], "label": label, "candidate_group_ids": sorted(c["id"] for c in cs),
              "mention_count": sum(len(c["mention_ids"]) for c in cs), "document_ids": sorted({d for c in cs for d in c["document_ids"]}),
              "kind": "name_or_family_navigation_not_identity_assertion", "human_review": "pending"}
             for label, cs in sorted(display.items())]
    return {"catalogue_cards": cards, "identity_candidates": candidates, "mention_mapping": mapping,
            "author_alias_evidence": alias_evidence, "unsupported_old_alias_labels": skipped,
            "ambiguous_definitions": [{"document_id": doc, "alias": alias, "names": sorted(definitions[(doc, alias)]),
                                       "decision": "do_not_bridge_distinct_names"} for doc, alias in sorted(ambiguous)],
            "policy": {"version": VERSION, "graph_endpoints_modified": False, "chemical_formula_repair": False,
                       "case_folding": False, "same_abbreviation_cross_document_identity": False,
                       "unknown_specification_equals_known": False, "automatic_human_approval": False}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    current = load(ROOT / "CURRENT.json")
    graph = args.graph or ROOT / current["graph"]
    g = load(graph)
    result = build(g)
    mids = {m["id"] for m in g["mentions"]}
    mapped = [x["mention_id"] for x in result["mention_mapping"]]
    assert set(mapped) == mids and len(mapped) == len(mids)
    for a in result["author_alias_evidence"]:
        ev = a["evidence"]
        b = next(b for b in g["blocks"] if b["id"] == ev["block_id"])
        assert b["text"][ev["start"]:ev["end"]] == ev["quote"]
    manifest = {"graph": graph.resolve().as_posix(), "graph_sha256": hashlib.sha256(graph.read_bytes()).hexdigest(),
                "parent_current": current, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if (args.output / "input_manifest.json").exists() and load(args.output / "input_manifest.json") != manifest:
        raise ValueError("已有运行指纹不同，不覆盖")
    save(args.output / "input_manifest.json", manifest)
    save(args.output / "entity_catalogue.json", result)
    import csv
    with (args.output / "entity_catalogue.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["目录ID", "展示名称", "提及数", "文献数", "身份候选分组数", "状态"])
        for card in sorted(result["catalogue_cards"], key=lambda c: (-c["mention_count"], c["label"])):
            writer.writerow([card["id"], card["label"], card["mention_count"], len(card["document_ids"]), len(card["candidate_group_ids"]), "pending"])
    summary = {"input_mentions": len(mids), "input_identity_entries": len(g["identities"]),
               "identity_candidate_partitions": len(result["identity_candidates"]), "display_cards": len(result["catalogue_cards"]),
               "author_definition_evidence": len(result["author_alias_evidence"]),
               "old_alias_labels_without_direct_definition": len(result["unsupported_old_alias_labels"]),
               "ambiguous_abbreviations_not_merged": len(result["ambiguous_definitions"]),
               "all_mentions_mapped_once": True, "source_anchors_valid": True, "graph_modified": False,
               "llm_calls": 0, "tokens": 0, "human_review": "pending"}
    save(args.output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
