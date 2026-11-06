"""Offline black-box tests for citation handling in the lexicon output."""
import gzip
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
    return test if (os.environ.get("ETHNOTRACE_STRICT") == "1" or os.environ.get("ETHNOTRACE_LEXICON_COMMAND")) else unittest.expectedFailure(test)


class LexiconContract(unittest.TestCase):
    def run_lexicon(self, text, labels=("1.1",), word="βρύον"):
        with tempfile.TemporaryDirectory(prefix="ethnotrace-lsj-") as tmp:
            root = Path(tmp)
            historical = root / "historical_texts/dioscorides"
            historical.mkdir(parents=True)
            index = root / "reference_sources/lsj"
            index.mkdir(parents=True)
            script = historical / "lexicon_lsj.py"
            shutil.copyfile(REPO / "historical_texts/dioscorides/lexicon_lsj.py", script)
            chapters = [{"chapter": label.split(".")[1], "book": int(label.split(".")[0]),
                         "label": label, "headword": word, "text_names": [], "rv_names": []}
                        for label in labels]
            (historical / "chapters.json").write_text(json.dumps({"chapters": chapters}), encoding="utf-8")
            # The index lemma is the normalized Greek spelling of βρύον.
            with gzip.open(index / "lsj_index.json.gz", "wt", encoding="utf-8") as stream:
                json.dump({"entries": [{"lemma": "βρυον", "key": "fixture", "text": text}]}, stream)
            configured = os.environ.get("ETHNOTRACE_LEXICON_COMMAND")
            command = json.loads(configured) if configured else [sys.executable, str(script)]
            command = [arg.replace("{root}", str(root)) for arg in command]
            env = os.environ.copy()
            env.update(PYTHONDONTWRITEBYTECODE="1", ETHNOTRACE_ROOT=str(root))
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return json.loads((historical / "lexicon_lsj.json").read_text(encoding="utf-8"))["chapters"]

    def identification(self, chapter, name):
        return next(x for n in chapter["names"] for e in n["entries"]
                    for x in e["identifications"] if x["binomial"] == name)

    def test_explicit_dioscorides_citation_is_recorded(self):
        chapters = self.run_lexicon("Ulva lactuca , Dsc. 1.1 .")
        match = self.identification(chapters[0], "Ulva lactuca")
        self.assertIn("1.1", match["dsc"])
        self.assertTrue(match["cites_this_chapter"])

    def test_another_chapter_is_not_passage_specific(self):
        chapters = self.run_lexicon("Ulva lactuca , Dsc. 1.2 .")
        match = self.identification(chapters[0], "Ulva lactuca")
        self.assertFalse(match["cites_this_chapter"])

    def test_unreferenced_identification_has_no_passage_claim(self):
        chapters = self.run_lexicon("Ulva lactuca .")
        match = self.identification(chapters[0], "Ulva lactuca")
        self.assertEqual(match["dsc"], [])
        self.assertFalse(match["cites_this_chapter"])

    def test_chapter_specific_flags_do_not_leak_between_chapters(self):
        chapters = self.run_lexicon("Ulva lactuca , Dsc. 1.1 .", labels=("1.1", "1.2"))
        first = self.identification(chapters[0], "Ulva lactuca")
        second = self.identification(chapters[1], "Ulva lactuca")
        self.assertTrue(first["cites_this_chapter"])
        self.assertFalse(second["cites_this_chapter"])

    def test_ib_referring_to_another_author_is_not_dioscorides(self):
        # Fixture mirrors the audited LSJ bru/on entry: ib. follows Nicander.
        text = "Ulva lactuca , Dsc. 4.98 : Nic. Th. 792 ; also a marsh-plant , ib. 415 ."
        chapters = self.run_lexicon(text, labels=("4.98",))
        match = self.identification(chapters[0], "Ulva lactuca")
        self.assertIn("4.98", match["dsc"])
        self.assertNotIn("4.415", match["dsc"])


if __name__ == "__main__":
    unittest.main()
