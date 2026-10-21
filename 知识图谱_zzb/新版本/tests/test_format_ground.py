import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from format_ground import locate,repair,GroundError

class FormatGroundTests(unittest.TestCase):
    def test_only_whitespace_and_glyphs_are_restored_to_source(self):
        self.assertEqual(locate("ADO suppresses Co− deposition.","ADO  suppresses Co− deposition."),"ADO  suppresses Co− deposition.")
        self.assertEqual(locate("DCQA-C_8-QIL","DCQA -C_8 -QI L"),"DCQA -C_8 -QI L")

    def test_chemical_case_or_digits_cannot_be_changed(self):
        with self.assertRaises(GroundError):locate("CoCl2","COCl2")
        with self.assertRaises(GroundError):locate("14.4","10.7")

    def test_ambiguous_normalization_is_rejected(self):
        with self.assertRaises(GroundError):locate("ADO-Co","ADO - Co and ADO- Co")

    def test_ellipsis_is_not_silently_filled(self):
        with self.assertRaises(GroundError):locate("change ... texture","change the surface texture")

if __name__=="__main__":unittest.main()
