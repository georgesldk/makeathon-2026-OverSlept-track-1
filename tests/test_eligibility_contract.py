"""Black-box eligibility contract: only JSON files and the CLI are inspected."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


def known_defect(test):
    """Keep a requirement visible until fixed; strict mode makes it fail normally."""
    return test if (os.environ.get("ETHNOTRACE_STRICT") == "1" or os.environ.get("ETHNOTRACE_ELIGIBILITY_COMMAND")) else unittest.expectedFailure(test)


def evidence(family="gbif", grade="strong", candidate="Testus plantus", node=None, **kwargs):
    return {"herb": "example", "candidate": candidate, "node": node or candidate,
            "family": family, "source": family, "grade": grade,
            "culpeper_name": "Test herb", "layer": "headword", **kwargs}


def candidate(**changes):
    row = {"accepted_name": "Testus plantus L.", "accepted_name_without_authors": "Testus plantus",
           "rank": "species", "family": "Testaceae", "resolved": True, "decided_by": "WFO",
           "kingdom_flags": ["plant"], "agreements": {"agree": 1},
           "scientific_names": [{"name": "Testus plantus"}], "wcvp_opinions": ["Testus plantus L."]}
    row.update(changes)
    return row


def description(scores=None, congruence=3, wikipedia_only=False):
    details = {"d1": {"feature": "leaf", "quote": "leaf"},
               "d2": {"feature": "root", "quote": "root"},
               "d3": {"feature": "flower", "quote": "flower"}}
    if scores is None:
        scores = [{"id": key, "label": "good", "source": "bhl"} for key in details]
    return {"details": details, "candidates": [{"accepted_name": "Testus plantus L.",
             "congruence": congruence, "wikipedia_only": wikipedia_only, "scores": scores}]}


class EligibilityContract(unittest.TestCase):
    """Each run uses synthetic files in a fresh temporary root; no source output is touched."""

    def run_case(self, c=None, rows=None, geo="local (native in Britain/Ireland)", desc=None,
                 include_geo=True):
        with tempfile.TemporaryDirectory(prefix="ethnotrace-test-") as directory:
            root = Path(directory)
            matching = root / "matching" / "culpeper"
            matching.mkdir(parents=True)
            (root / "description_sources" / "check" / "culpeper").mkdir(parents=True)
            script = root / "matching" / "eligibility.py"
            shutil.copyfile(REPO / "matching" / "eligibility.py", script)
            chosen = c if c is not None else candidate()
            record = {"name": "Test herb", "label": None, "candidates": [chosen]}
            self.write(matching / "herb_candidates_resolved.json", {"herbs": {"example": record}})
            items = [{"accepted_name": chosen.get("accepted_name"), "geography": geo,
                      "native_regions": []}] if include_geo else []
            self.write(matching / "geography.json", {"herbs": {"example": {"candidates": items}}})
            rows = [evidence(), evidence("wikidata")] if rows is None else rows
            (matching / "evidence.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
            if desc is not None:
                self.write(root / "description_sources/check/culpeper/description_check.json", {"herbs": {"Test herb": desc}})
            # An alternative program may implement the same on-disk contract. The JSON
            # command array is executed without a shell; placeholders are substituted.
            configured = os.environ.get("ETHNOTRACE_ELIGIBILITY_COMMAND")
            command = json.loads(configured) if configured else [sys.executable, str(script), "--book", "culpeper"]
            command = [arg.replace("{root}", str(root)).replace("{book}", "culpeper") for arg in command]
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["ETHNOTRACE_ROOT"] = str(root)
            done = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 0, f"Command failed: {done.stderr}\n{done.stdout}")
            output = json.loads((matching / "eligibility.json").read_text(encoding="utf-8"))
            herb = output["herbs"]["example"]
            all_rows = [(section, row) for section in ("shown", "possible", "hidden") for row in herb[section]]
            self.assertEqual(len(all_rows), 1, "Each candidate must remain in the output exactly once")
            return all_rows[0]

    @staticmethod
    def write(path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_two_independent_strong_lineages_are_eligible_without_description(self):
        section, row = self.run_case()
        self.assertEqual((section, row["tier"]), ("shown", "A"))
        self.assertEqual(set(row["lineages_strong"]), {"GBIF + Catalogue of Life", "Wikidata"})

    def test_repeated_rows_from_one_lineage_are_not_independent(self):
        section, row = self.run_case(rows=[evidence(), evidence(), evidence("col")])
        self.assertEqual((section, row["tier"]), ("possible", "B"))
        self.assertIn("B1", row["rules"])

    def test_one_strong_source_is_possible(self):
        section, row = self.run_case(rows=[evidence()])
        self.assertEqual(section, "possible")
        self.assertIn("B1", row["rules"])

    def test_weak_evidence_only_is_hidden(self):
        section, row = self.run_case(rows=[evidence(grade="weak")])
        self.assertEqual(section, "hidden")
        self.assertIn("X1", row["rules"])

    def test_unresolved_candidate_is_retained_and_hidden(self):
        section, row = self.run_case(c=candidate(resolved=False, decided_by=None))
        self.assertEqual(section, "hidden")
        self.assertIn("X3", row["rules"])

    def test_known_higher_ranks_are_hidden(self):
        for rank in ("genus", "family", "order", "class", "phylum", "tribe"):
            with self.subTest(rank=rank):
                section, row = self.run_case(c=candidate(rank=rank))
                self.assertEqual(section, "hidden")
                self.assertIn("X6", row["rules"])

    def test_far_geography_is_hidden_under_current_rules(self):
        section, row = self.run_case(geo="far")
        self.assertEqual(section, "hidden")
        self.assertIn("X2", row["rules"])

    def test_missing_distribution_gets_caveat(self):
        section, row = self.run_case(geo="no distribution data")
        self.assertEqual(section, "possible")
        self.assertIn("B3", row["rules"])

    def test_introduced_without_date_gets_caveat(self):
        section, row = self.run_case(geo="local (introduced in Britain/Ireland)")
        self.assertEqual(section, "possible")
        self.assertIn("B3", row["rules"])

    def test_wfo_wcvp_disagreement_adds_caveat(self):
        section, row = self.run_case(c=candidate(agreements={"disagree": 1}))
        self.assertEqual(section, "possible")
        self.assertIn("B2", row["rules"])

    def test_global_names_only_is_not_promoted_to_a(self):
        section, row = self.run_case(c=candidate(decided_by="Global Names"))
        self.assertEqual(section, "possible")
        self.assertIn("B4", row["rules"])

    def test_comparison_with_explicit_mismatch_has_poor_fit_caveat(self):
        scores = [{"id": "d1", "label": "no", "source": "bhl"}]
        section, row = self.run_case(desc=description(scores, -1))
        self.assertEqual(section, "possible")
        self.assertIn("B6", row["rules"])

    def test_unchecked_candidate_with_described_entry_has_caveat(self):
        d = description()
        d["candidates"] = []
        section, row = self.run_case(desc=d)
        self.assertEqual(section, "possible")
        self.assertIn("B7", row["rules"])

    @known_defect
    def test_infraspecific_evidence_reaches_normalized_candidate(self):
        # Adapted from the real Horsetail record; the original name must survive.
        row = evidence(candidate="Testus plantus subsp. minor", node="Testus plantus")
        section, result = self.run_case(rows=[row])
        self.assertNotEqual(section, "hidden")
        self.assertNotIn("X1", result["rules"])

    @known_defect
    def test_unknown_kingdom_is_not_called_non_plant(self):
        _, row = self.run_case(c=candidate(kingdom_flags=["unknown"]))
        self.assertNotIn("X4", row["rules"])

    @known_defect
    def test_mixed_kingdom_is_not_called_non_plant(self):
        _, row = self.run_case(c=candidate(kingdom_flags=["mixed"]))
        self.assertNotIn("X4", row["rules"])

    @known_defect
    def test_unknown_rank_is_not_presented_as_species(self):
        section, row = self.run_case(c=candidate(rank=None))
        self.assertEqual(section, "hidden", "Unknown rank must not be presented as species-level identification")
        self.assertNotIn("A2", row["rules"])

    @known_defect
    def test_empty_comparison_is_not_poor_fit(self):
        _, row = self.run_case(desc=description(scores=[], congruence=0))
        self.assertNotIn("B6", row["rules"])
        self.assertNotEqual(row["description"], "weak")

    @known_defect
    def test_disagreement_preserves_both_backbone_names(self):
        alt = "Otherus plantus L."
        _, row = self.run_case(c=candidate(agreements={"disagree": 1}, wcvp_opinions=[alt]))
        self.assertIn(alt, json.dumps(row, ensure_ascii=False))

    @known_defect
    def test_absent_geography_is_not_silently_passed_as_a5(self):
        section, row = self.run_case(include_geo=False)
        self.assertNotEqual(section, "shown")
        self.assertNotIn("A5", row["rules"])


if __name__ == "__main__":
    unittest.main()
