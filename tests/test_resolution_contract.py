"""Offline tests of taxonomic resolution through file and process boundaries."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


def wfo_record(role="accepted", identifier="wfo-1", accepted_id=None, spelling="same"):
    return {"role": role, "wfo_id": identifier, "full_name": "Testus plantus L.",
            "name_without_authors": "Testus plantus", "accepted_wfo_id": accepted_id,
            "accepted_name": "Testus acceptedus L.", "accepted_name_without_authors": "Testus acceptedus",
            "placement": "Plantae/Testaceae", "rank": "species", "authors": "L.", "spelling": spelling}


def wcvp_record(status="Accepted", identifier="p1", accepted_id="p1"):
    return {"taxon_status": status, "plant_name_id": identifier, "accepted_plant_name_id": accepted_id,
            "taxon_name": "Testus plantus", "taxon_authors": "L.", "family": "Testaceae", "taxon_rank": "species"}


class ResolutionContract(unittest.TestCase):
    def resolve(self, wfo_value, wcvp_value, accepted=None):
        with tempfile.TemporaryDirectory(prefix="ethnotrace-resolution-") as tmp:
            root = Path(tmp)
            match = root / "matching/culpeper"
            match.mkdir(parents=True)
            script = root / "matching/resolve_scientific.py"
            shutil.copyfile(REPO / "matching/resolve_scientific.py", script)
            for source in ("wfo", "wcvp"):
                (root / "scientific_name_sources" / source / "culpeper").mkdir(parents=True)
            candidate = {"scientific_name": "Testus plantus", "level": "species", "culpeper_names": ["Test herb"],
                         "sources": ["source"], "families": ["source"], "strong_rows": 1,
                         "weak_rows": 0, "kingdom_flag": "plant"}
            (match / "candidates.json").write_text(json.dumps({"test": {"name": "Test herb", "candidates": [candidate]}}))
            def write(path, value):
                path.write_text(json.dumps(value), encoding="utf-8")
            write(root / "scientific_name_sources/wfo/culpeper/wfo.json", {"names": {"Testus plantus": wfo_value}})
            write(root / "scientific_name_sources/wcvp/culpeper/wcvp.json", {"names": {"Testus plantus": wcvp_value},
                  "accepted": accepted or {}})
            configured = os.environ.get("ETHNOTRACE_RESOLUTION_COMMAND")
            command = json.loads(configured) if configured else [sys.executable, str(script)]
            command = [arg.replace("{root}", str(root)).replace("{book}", "culpeper") for arg in command]
            env = os.environ.copy()
            env.update(PYTHONDONTWRITEBYTECODE="1", ETHNOTRACE_ROOT=str(root))
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            resolved = json.loads((match / "scientific_names_resolved.json").read_text())
            groups = json.loads((match / "herb_candidates_resolved.json").read_text())
            return resolved["names"]["Testus plantus"], groups["herbs"]["test"]["candidates"]

    def test_accepted_backbones_agree(self):
        w = {"match": wfo_record(), "candidates": [], "level": "species", "original_forms": []}
        v = {"records": [wcvp_record()], "original_forms": []}
        result, groups = self.resolve(w, v, {"p1": wcvp_record()})
        self.assertEqual(result["agreement"], "agree")
        self.assertEqual(result["wfo"]["accepted_id"], "wfo-1")
        self.assertEqual(result["wcvp"]["accepted_id"], "p1")
        self.assertEqual(groups[0]["scientific_names"][0]["name"], "Testus plantus")

    def test_wfo_synonym_preserves_target_and_original(self):
        w = {"match": wfo_record("synonym", "syn-1", "accepted-1"), "candidates": [],
             "level": "species", "original_forms": []}
        result, groups = self.resolve(w, {"records": [], "original_forms": []})
        self.assertEqual(result["wfo"]["accepted_id"], "accepted-1")
        self.assertEqual(result["wfo"]["via"]["id"], "syn-1")
        self.assertEqual(result["agreement"], "only WFO")
        self.assertEqual(groups[0]["scientific_names"][0]["name"], "Testus plantus")

    def test_different_synonym_targets_remain_unresolved(self):
        w = {"match": None, "candidates": [wfo_record("synonym", "syn-1", "a"),
               wfo_record("synonym", "syn-2", "b")], "level": "species", "original_forms": []}
        result, _ = self.resolve(w, {"records": [], "original_forms": []})
        self.assertIsNone(result["wfo"]["accepted_id"])
        self.assertIn("different names", result["wfo"]["reason"])
        self.assertEqual(result["agreement"], "neither")

    def test_wcvp_synonym_resolves_to_accepted_record(self):
        syn = wcvp_record("Synonym", "old", "new")
        accepted = {**wcvp_record(identifier="new", accepted_id="new"), "taxon_name": "Testus acceptedus"}
        w = {"match": None, "candidates": [], "level": "species", "original_forms": []}
        result, _ = self.resolve(w, {"records": [syn], "original_forms": []}, {"new": accepted})
        self.assertEqual(result["wcvp"]["accepted_id"], "new")
        self.assertEqual(result["wcvp"]["via"]["id"], "old")
        self.assertEqual(result["agreement"], "only WCVP")

    def test_misapplied_wcvp_record_is_not_accepted_synonym(self):
        w = {"match": None, "candidates": [], "level": "species", "original_forms": []}
        result, _ = self.resolve(w, {"records": [wcvp_record("Misapplied", "old", "new")], "original_forms": []})
        self.assertIsNone(result["wcvp"]["accepted_id"])
        self.assertEqual(result["agreement"], "neither")

    def test_wfo_wcvp_different_accepted_names_are_disagreement(self):
        w = {"match": wfo_record(), "candidates": [], "level": "species", "original_forms": []}
        other = {**wcvp_record(), "taxon_name": "Testus otherus"}
        result, _ = self.resolve(w, {"records": [other], "original_forms": []}, {"p1": other})
        self.assertEqual(result["agreement"], "disagree")
        self.assertNotEqual(result["wfo"]["accepted_name"], result["wcvp"]["accepted_name"])


if __name__ == "__main__":
    unittest.main()
