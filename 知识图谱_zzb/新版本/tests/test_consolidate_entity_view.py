import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from consolidate_entity_view import build, key


def bundle(rows):
    g = {"mentions": [], "blocks": [], "identities": [], "identity_links": []}
    for i, (doc, text, names) in enumerate(rows):
        bid = "b" + str(i)
        g["blocks"].append({"id": bid, "document_id": doc, "text": text})
        for j, name in enumerate(names):
            start = text.index(name)
            g["mentions"].append({"id": f"m{i}-{j}", "document_id": doc, "surface": name, "candidate_type_ids": [],
                "evidence": {"kind": "block", "block_id": bid, "start": start, "end": start+len(name), "quote": name}})
    return g


class CatalogueTests(unittest.TestCase):
    def test_same_name_across_documents_grouped(self):
        r = build(bundle([("a", "copper", ["copper"]), ("b", "copper", ["copper"])]))
        self.assertEqual(len(r["identity_candidates"]), 1)
        self.assertEqual(len(r["mention_mapping"]), 2)

    def test_ambiguous_acronyms_separate_identities_but_one_display(self):
        r = build(bundle([("a", "ABC", ["ABC"]), ("b", "ABC", ["ABC"])]))
        self.assertEqual(len(r["identity_candidates"]), 2)
        self.assertEqual(len(r["catalogue_cards"]), 1)

    def test_explicit_definition_groups_abbreviation(self):
        r = build(bundle([("a", "polyvinylpyrrolidone (PVP)", ["polyvinylpyrrolidone", "PVP"])]))
        self.assertEqual(len(r["identity_candidates"]), 1)
        self.assertEqual(len(r["author_alias_evidence"]), 1)

    def test_formula_charge_and_case_preserved(self):
        self.assertNotEqual(key("Co"), key("CO"))
        r = build(bundle([("a", "Co Co2+ CoSO4 CoSO4·7H2O", ["Co", "Co2+", "CoSO4", "CoSO4·7H2O"])]))
        self.assertEqual(len(r["identity_candidates"]), 4)

    def test_specs_group_for_navigation_only(self):
        r = build(bundle([("a", "PEG PEG-2000 PEG-4000", ["PEG", "PEG-2000", "PEG-4000"])]))
        self.assertEqual(len(r["identity_candidates"]), 3)
        self.assertEqual(len(r["catalogue_cards"]), 1)

    def test_deterministic_and_no_input_mutation(self):
        import copy
        g = bundle([("a", "cobalt (Co)", ["cobalt", "Co"])])
        before = copy.deepcopy(g)
        self.assertEqual(build(g), build(g))
        self.assertEqual(g, before)

    def test_shared_acronym_does_not_bridge_different_compounds(self):
        r = build(bundle([("a", "glutamic acid (DMG); dimethoxyoxime (DMG)", ["glutamic acid", "DMG", "dimethoxyoxime"])]))
        self.assertEqual(len(r["identity_candidates"]), 3)
        self.assertEqual(len(r["ambiguous_definitions"]), 1)


if __name__ == "__main__":
    unittest.main()
