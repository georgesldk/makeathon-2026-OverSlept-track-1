"""Regression tests for stage3/rules.py: the 14 cases of OverSlept_Stage3_Plan_FINAL.md §3.6 D,
plus boundary cases found while writing the rules. No AI, no network, no real abstracts.

Run:  python3 stage3/tests/test_rules.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rules import assess, summarise, ema_applicability


def F(relevance="direct", etype="human_rct", outcome="positive", voided=(), **comp):
    """Fields as the model would return them; compatibility defaults to "same"."""
    c = {k: {"value": comp.get(k, "same")} for k in
         ("species", "condition", "therapeutic_action", "plant_part", "preparation", "route")}
    return {"relevance": relevance, "evidence_type": etype, "compatibility": c,
            "outcome": {"value": outcome}, "validation": {"fields_voided": list(voided)}}


class PlanCases(unittest.TestCase):
    def test_01_same_plant_and_term_other_question(self):
        r = assess(F(relevance="different_question"))
        self.assertEqual(r["applicability"], "not_relevant")
        self.assertIsNone(r["finding"])

    def test_02_direct_rct_no_effect(self):
        r = assess(F(outcome="negative"))
        self.assertEqual((r["applicability"], r["finding"]), ("direct", "negative"))
        self.assertEqual(r["badge"], "Human RCT · Direct · Negative")

    def test_03_same_plant_unrelated_condition(self):
        r = assess(F(condition="different", therapeutic_action="different"))
        self.assertEqual(r["applicability"], "not_relevant")

    def test_04_positive_in_vitro_never_clinical(self):
        r = assess(F(etype="in_vitro", route="unknown"))
        self.assertIn("in_vitro", r["modifiers"])
        self.assertIn("S3-7", r["rules_applied"])
        self.assertTrue(r["badge"].startswith("In vitro"))
        self.assertNotEqual(r["applicability"], "direct")

    def test_05_essential_oil_vs_root_decoction(self):
        r = assess(F(plant_part="different", preparation="different"))
        self.assertEqual((r["applicability"], r["finding"]), ("indirect", "positive"))
        self.assertIn("different_preparation", r["modifiers"])

    def test_06_abstract_omits_part_preparation_route(self):
        r = assess(F(plant_part="unknown", preparation="unknown", route="unknown"))
        self.assertEqual(r["applicability"], "partial")
        self.assertEqual(set(r["unknowns"]), {"plant_part", "preparation", "route"})
        self.assertIn("S3-4", r["rules_applied"])

    def test_07_protocol_without_results(self):
        r = assess(F(outcome="not_reported"))
        self.assertEqual(r["finding"], "not_reported")
        self.assertIn("S3-2", r["rules_applied"])

    def test_08_other_species_same_genus(self):
        r = assess(F(species="related"))
        self.assertEqual(r["applicability"], "indirect")

    def test_09_mixed_endpoints(self):
        self.assertEqual(assess(F(outcome="mixed"))["finding"], "mixed")

    def test_10_invented_quote_voids_relevance(self):
        r = assess(F(voided=["relevance"]))
        self.assertEqual(r["applicability"], "unassessable")
        self.assertIn("S3-1", r["rules_applied"])

    def test_11_tier_b_keeps_uncertainty(self):
        r = assess(F(), tier="B")
        self.assertIn("possible_historical_identification", r["modifiers"])
        self.assertIn("S3-8", r["rules_applied"])

    def test_12_negative_direct_with_positive_indirect(self):
        a = assess(F(outcome="negative"))
        b = assess(F(preparation="different", outcome="positive"))
        s = summarise([a, b])
        self.assertEqual(s["lanes"]["human"]["summary"], "negative (direct) · less direct studies differ")
        self.assertEqual(len(s["lanes"]["human"]["results"]), 2)

    def test_13_inconclusive_review(self):
        r = assess(F(etype="systematic_review", outcome="inconclusive"))
        self.assertEqual(r["finding"], "inconclusive")
        s = summarise([r])
        self.assertEqual(s["lanes"]["human"]["summary"], "no outcome evidence (direct)")

    def test_14_ema_traditional_use_other_preparation(self):
        e = ema_applicability({"preparation": "different", "route": "same", "indication": "same"})
        self.assertFalse(e["applicable"])
        self.assertEqual(e["mismatches"], ["preparation"])


class Boundaries(unittest.TestCase):
    def test_other_genus_is_not_relevant(self):
        self.assertEqual(assess(F(species="different"))["applicability"], "not_relevant")

    def test_unknown_species_is_unassessable(self):
        self.assertEqual(assess(F(species="unknown"))["applicability"], "unassessable")

    def test_related_condition_is_partial_not_direct(self):
        self.assertEqual(assess(F(condition="related"))["applicability"], "partial")

    def test_direct_only_when_everything_same(self):
        r = assess(F())
        self.assertEqual(r["applicability"], "direct")
        self.assertIn("S3-5", r["rules_applied"])

    def test_voided_outcome_becomes_unclear(self):
        self.assertEqual(assess(F(voided=["outcome"]))["finding"], "unclear")

    def test_voided_compatibility_counts_as_unknown(self):
        r = assess(F(voided=["route"]))
        self.assertEqual(r["applicability"], "partial")
        self.assertIn("route", r["unknowns"])

    def test_animal_is_preclinical_lane(self):
        r = assess(F(etype="animal"))
        self.assertIn("preclinical_animal", r["modifiers"])
        self.assertIn("preclinical", summarise([r])["lanes"])

    def test_not_relevant_studies_never_reach_the_summary(self):
        s = summarise([assess(F(relevance="not_about_the_plant"))])
        self.assertEqual(s["lanes"], {})
        self.assertIn("not the same as not studied", s["search"])

    def test_lanes_are_kept_apart(self):
        s = summarise([assess(F(outcome="negative")), assess(F(etype="in_vitro", outcome="positive"))])
        self.assertEqual(s["lanes"]["human"]["summary"], "negative (direct)")
        self.assertEqual(s["lanes"]["preclinical"]["summary"], "positive (indirect only)")

    def test_indirect_only_evidence_is_labelled(self):
        s = summarise([assess(F(preparation="different", outcome="positive"))])   # e.g. a homeopathic dilution
        self.assertEqual(s["lanes"]["human"]["summary"], "positive (indirect only)")

    def test_partial_beats_indirect_in_the_summary(self):
        s = summarise([assess(F(condition="related", outcome="positive")),
                       assess(F(preparation="different", outcome="positive"))])
        self.assertEqual(s["lanes"]["human"]["summary"], "positive (partial match only, related condition)")

    def test_ema_traditional_use_is_labelled_and_kept_in_its_own_lane(self):
        r = assess(F(etype="regulatory_monograph", condition="related", outcome="positive") | {"ema_use": "traditional_use"})
        self.assertIn("ema_traditional_use", r["modifiers"])
        self.assertIn("not proof of efficacy", r["badge"])
        s = summarise([r])
        self.assertEqual(list(s["lanes"]), ["regulatory"])
        self.assertTrue(s["lanes"]["regulatory"]["summary"].startswith("indication listed (partial match only, related condition)"))
        self.assertIn("traditional use only", s["lanes"]["regulatory"]["summary"])

    def test_registered_trial_without_results_is_human_lane_no_outcome(self):
        r = assess(F(etype="registered_trial", outcome="not_reported"))
        s = summarise([r])
        self.assertEqual(s["lanes"]["human"]["summary"], "no outcome evidence (direct)")

    def test_related_condition_is_named_in_badge_and_summary(self):
        r = assess(F(condition="related"))                 # e.g. pressure ulcers for genital sores
        self.assertEqual(r["applicability"], "partial")
        self.assertIn("related_condition", r["modifiers"])
        self.assertEqual(r["badge"], "Human RCT · Partial (related condition) · Positive")
        self.assertEqual(summarise([r])["lanes"]["human"]["summary"], "positive (partial match only, related condition)")

    def test_partial_for_unknown_details_has_no_related_condition_label(self):
        r = assess(F(preparation="unknown"))
        self.assertEqual(r["badge"], "Human RCT · Partial · Positive")

    def test_related_part_preparation_or_route_is_never_direct(self):
        for k in ("plant_part", "preparation", "route"):
            r = assess(F(**{k: "related"}))               # e.g. leaf extract for the book's juice
            self.assertEqual(r["applicability"], "partial", k)

    def test_in_vitro_is_never_direct_even_if_model_says_same_route(self):
        r = assess(F(etype="in_vitro"))                    # every field "same", as a careless model might say
        self.assertEqual(r["applicability"], "indirect")
        self.assertIn("different_route", r["modifiers"])

    def test_animal_keeps_reported_route_but_is_preclinical(self):
        r = assess(F(etype="animal"))
        self.assertEqual(r["applicability"], "direct")     # comparable design...
        self.assertTrue(r["badge"].startswith("Animal"))  # ...but never a clinical claim
        self.assertIn("preclinical_animal", r["modifiers"])

    def test_no_percentages_anywhere(self):
        r = assess(F())
        self.assertFalse(any(isinstance(v, float) for v in r.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
