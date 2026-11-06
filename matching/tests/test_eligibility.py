"""Regression tests for matching/eligibility.py: Marselo's two Stage 2 audits (2026-11-06).
No network, no AI, no saved outputs: small hand-made candidates only.

Run:  python3 matching/tests/test_eligibility.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eligibility import judge, description, geography


def cand(name="Plantago major", rank="species", flags=("plant",), decided_by="WFO", **kw):
    return {"accepted_name": name + " L.", "accepted_name_without_authors": name, "rank": rank,
            "kingdom_flags": list(flags), "decided_by": decided_by, "resolved": True, **kw}


EV = [{"lineage": "WFO", "grade": "strong", "passage": False, "layer": "name"},
      {"lineage": "Wikidata", "grade": "strong", "passage": False, "layer": "name"}]   # A4a: 2 lineages
NONE = ("no description record", None)
FITS = ("fits", 4)


def entry(n_features=4, scores=(), congruence=0):
    details = {f"d{i}": {"feature": f"f{i}", "quote": "x"} for i in range(n_features)}
    return {"details": details, "candidates": [{"accepted_name": "Plantago major L.", "congruence": congruence,
                                                "wikipedia_only": False, "scores": list(scores)}]}


class Rank(unittest.TestCase):
    def test_one_word_no_rank_is_genus(self):                    # audit 1, bug 5: Plantago
        self.assertIn("X6", judge("culpeper", cand("Plantago", rank=None), EV, "fits", NONE, False)["rules"])

    def test_two_words_no_rank_not_confirmed_species(self):      # audit 2, issue 5
        j = judge("culpeper", cand(rank=None), EV, "fits", NONE, False)
        self.assertEqual(j["tier"], "X")                          # hidden, as in Marselo's contract test
        self.assertIn("X8", j["rules"])

    def test_species_rank_passes(self):
        self.assertEqual(judge("culpeper", cand(), EV, "fits", NONE, False)["tier"], "A")


class Geography(unittest.TestCase):
    def test_missing_record_is_a_caveat_not_a_pass(self):        # audit 2, issue 6
        self.assertIsNone(geography("culpeper", None))
        j = judge("culpeper", cand(), EV, None, NONE, False)
        self.assertEqual(j["tier"], "B")
        self.assertIn("B9", j["rules"])

    def test_not_checked_record(self):
        self.assertIsNone(geography("culpeper", {"geography": "not checked (no accepted name)"}))

    def test_no_distribution_is_b3_not_b9(self):
        self.assertEqual(geography("culpeper", {"geography": "no distribution data"}), "unknown")
        self.assertIn("B3", judge("culpeper", cand(), EV, "unknown", NONE, False)["rules"])

    def test_missing_data_never_hides(self):
        self.assertNotEqual(judge("culpeper", cand(), EV, None, NONE, False)["tier"], "X")


class Kingdom(unittest.TestCase):
    def test_explicit_non_plant_is_x4(self):
        self.assertIn("X4", judge("culpeper", cand(flags=("non-plant",)), EV, "fits", NONE, False)["rules"])

    def test_unknown_kingdom_global_names_only_is_x7(self):      # audit 2, issue 7: the shrew
        j = judge("dioscorides", cand("Sorex araneus", flags=("unknown",), decided_by="Global Names"),
                  EV, "fits", NONE, False)
        self.assertIn("X7", j["rules"])
        self.assertNotIn("X4", j["rules"])

    def test_unknown_kingdom_known_to_wfo_is_not_hidden(self):   # audit 1, bug 4: Berberis x ottawensis
        j = judge("culpeper", cand(flags=("unknown",)), EV, "fits", NONE, False)
        self.assertNotIn("X4", j["rules"])
        self.assertNotIn("X7", j["rules"])


class Description(unittest.TestCase):
    def test_all_absent_scores_are_no_comparison(self):          # audit 2, issue 3: Asparagus aphyllus
        e = entry(scores=[{"id": f"d{i}", "label": "absent", "source": "none"} for i in range(3)])
        self.assertEqual(description(e, "Plantago major L.")[0], "no comparable data")
        j = judge("culpeper", cand(), EV, "fits", description(e, "Plantago major L."), True)
        self.assertIn("B7", j["rules"])
        self.assertNotIn("B6", j["rules"])

    def test_no_scores_is_no_comparison(self):                   # audit 1, bug 6: Typha domingensis
        self.assertEqual(description(entry(), "Plantago major L.")[0], "no comparable data")

    def test_explicit_mismatch_is_b6(self):
        e = entry(scores=[{"id": "d0", "label": "no"}, {"id": "d1", "label": "good"}], congruence=0)
        self.assertEqual(description(e, "Plantago major L.")[0], "poor")
        self.assertIn("B6", judge("culpeper", cand(), EV, "fits", description(e, "Plantago major L."), True)["rules"])

    def test_too_few_details_is_not_held_against(self):          # audit 2, issue 4: Vicia faba 2.105
        e = entry(n_features=0)
        self.assertEqual(description(e, "Plantago major L.")[0], "too few details")
        j = judge("dioscorides", cand(), EV, "fits", description(e, "Plantago major L."), False)
        self.assertEqual(j["tier"], "A")
        self.assertIn("A6 n/a", j["rules"])                     # not "A6": nothing was checked

    def test_no_record_shows_a6_na(self):
        self.assertIn("A6 n/a", judge("culpeper", cand(), EV, "fits", NONE, False)["rules"])

    def test_fit_shows_a6(self):
        self.assertIn("A6", judge("culpeper", cand(), EV, "fits", FITS, True)["rules"])

    def test_candidate_not_compared(self):
        self.assertEqual(description(entry(), "Other plant L.")[0], "not compared")


if __name__ == "__main__":
    unittest.main(verbosity=1)
