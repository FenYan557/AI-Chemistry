"""回归：图注数值不漏计、重复数值不折叠、符号与科学计数法不丢。"""
import unittest
from collections import Counter
from release_check import numeric_tokens, after_text, before_text


class NumericDiagnosticTests(unittest.TestCase):
    def test_caption_values_are_kept(self):
        text = "Fig. 2. I−: 4.452 μmol/L; diameter: 85 and 105 μm."
        source = {"type": "chart", "chart_caption": [text]}
        output = {"type": "chart", "caption": text, "caption_extra": ""}
        self.assertEqual(numeric_tokens(before_text(source)), numeric_tokens(after_text(output)))

    def test_repeated_values_are_not_collapsed(self):
        self.assertEqual(numeric_tokens("10 10 10")["1E+1"], 3)
        self.assertEqual(sum((numeric_tokens("10 10 10") - numeric_tokens("10")).values()), 2)

    def test_sign_exponent_thousands_and_underscore(self):
        self.assertEqual(numeric_tokens("−1e−3 -0.001"), Counter({"-0.001": 2}))
        self.assertEqual(numeric_tokens("1,234.5"), numeric_tokens("1234.5"))
        self.assertEqual(numeric_tokens("_0.7"), numeric_tokens("_ 0.7"))
        self.assertNotEqual(numeric_tokens("-1"), numeric_tokens("1"))


if __name__ == "__main__":
    unittest.main()
