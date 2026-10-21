import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from precision_guard import flags

def row(subject="plating solution",relation="other",statement="observation",quote="The composition of the plating solution included 220 g/L salt.",**kw):
 return {"raw":{"subject":subject,"relation":relation,"statement":statement,"quote":quote,**kw}}

class PrecisionGuardTests(unittest.TestCase):
 def test_recipe_and_method_are_quarantined(self):
  self.assertIn("recipe_not_observed_result",flags(row()))
  self.assertIn("unresolved_calculation_setup_vs_result",flags(row(subject="BD",statement="calculation_result",quote="The solvent effect was included by IEFPCM.")))
 def test_actual_observation_and_calculated_adsorption_preserved(self):
  self.assertFalse(flags(row(subject="coating",quote="EDS mapping demonstrates uniform element distribution.")))
  self.assertFalse(flags(row(subject="MTT",relation="adsorption",statement="calculation_result",quote="Charge density maps of MTT adsorbed on copper.")))
 def test_comparison_not_affected_object(self):
  self.assertIn("comparison_target_may_not_be_affected_object",flags(row(subject="PDS",target="PD",relation="effect",statement="author_interpretation",quote="Potential increase caused by PDS is less pronounced compared to PD.")))
 def test_statistical_association_not_cause(self):
  self.assertIn("association_or_prediction_not_causal_effect",flags(row(subject="FractionCSP3",target="ΔE",relation="effect",outcomes=[{"value":"positive association"}])))
 def test_concentration_cannot_belong_to_test_method(self):
  self.assertIn("concentration_assigned_to_method",flags(row(subject="chronopotentiometry tests",statement="reported_claim",conditions=[{"parameter":"concentrations of PDS","about":"subject"}])))
 def test_ionic_coordination_and_unbound_regimes(self):
  self.assertIn("ionic_complexation_not_surface_adsorption",flags(row(subject="NBT",target="Cu ^ 2 +",relation="adsorption",statement="calculation_result",quote="The Cu–O distance in the complex is 2.177 A.")))
  self.assertIn("multiple_concentration_regimes_without_result_binding",flags(row(subject="MTT",target="Cu reduction",relation="effect",quote="Resistance rises from 24 to 181.",conditions=[{"parameter":"concentration","value":"0 mg/L"},{"parameter":"concentration","value":"60 mg/L"}],outcomes=[{"value":"24"},{"value":"181"}])))
 def test_affected_material_not_causal_agent(self):
  self.assertIn("affected_property_or_material_as_causal_subject",flags(row(subject="coating",relation="effect",quote="The coating was dispersed evenly.",outcomes=[{"indicator":"dispersion","value":"evenly"}])))
 def test_study_purpose_not_demonstrated_effect(self):
  self.assertIn("study_description_not_demonstrated_result",flags(row(subject="BD",target="coating",relation="effect",statement="reported_claim",quote="In this work the impact of BD on coating is characterized by SEM.")))
