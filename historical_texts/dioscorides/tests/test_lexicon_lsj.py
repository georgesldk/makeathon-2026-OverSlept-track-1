"""Regression tests for historical_texts/dioscorides/lexicon_lsj.py (read_entry): Marselo's two Stage 2
audits (2026-11-06). The texts are the LSJ entries as they stand in the local LSJ index.

Run:  python3 historical_texts/dioscorides/tests/test_lexicon_lsj.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lexicon_lsj import read_entry

G = {"Plantago", "Nardostachys", "Valeriana", "Cymbopogon", "Pinus", "Narcissus", "Muscari", "Citrus", "Celtis", "Nymphaea", "Isatis", "Cyclamen", "Lonicera", "Artemisia", "Inula", "Calamintha", "Ulva", "Acorus", "Arundo", "Iris"}

KUKLAMINOS = ("kukla/mi_nos [ a^], h( , Theoc. 5.123 , Dsc. 2.164 ; also o( , Thphr. HP 7.9.4 , 9.9.3 ; "
              "kukla^mi/s , h( , Orph. A. 917 :— Cyclamen graecum , etc., Il.cc.; also k. e(te/ra honeysuckle, "
              "Lonicera Periclymenum , Dsc. 2.165 .")
ARTEMISIA = ("Artemisia arborescens, Dsc. 3.113 . A. campestris, Dsc. 3.113 . a). mono/klwnos, = A. scoparia, Ps.- Dsc. 3.113 . = a)mbrosi/a , ib. 114 .")
HELENION = ("e(le/nion , to/ , calamint, Calamintha incana , Chaerem. 14.12 , Thphr. HP 6.6.2 , Dsc. 1.29 . "
            "elecampane, Inula Helenium , ib. 28 . = su/mfuton , Ps.- Dsc. 4.9 .")
BRYON = "Ulva Lactuca , Dsc. 4.98 , Thphr. HP 4.6.2 , Nic. Th. 792 ; also, a marsh-plant, ib. 415 ."


def ids(text):
    return {i["binomial"]: i for i in read_entry(text, G)["identifications"]}


class SenseBoundaries(unittest.TestCase):                       # audit 2, issue 1
    def test_locis_citatis_takes_the_earlier_passage(self):
        r = ids(KUKLAMINOS)
        self.assertEqual(r["Cyclamen graecum"]["dsc"], ["2.164"])
        self.assertEqual(r["Cyclamen graecum"]["via_locis_citatis"], ["2.164"])

    def test_also_starts_a_new_sense(self):
        r = ids(KUKLAMINOS)
        self.assertNotIn("2.165", r["Cyclamen graecum"]["dsc"])
        self.assertEqual(r["Lonicera periclymenum"]["dsc"], ["2.165"])

    def test_equals_after_citation_starts_a_new_sense(self):
        self.assertEqual(ids(HELENION)["Inula helenium"]["pseudo_dsc"], [])
        self.assertNotIn("3.114", ids(ARTEMISIA)["Artemisia scoparia"]["pseudo_dsc"])

    def test_author_ll_cc_is_not_dioscorides(self):
        r = ids("Hp. Ulc. 11 , Dsc. 2.1 :—a plant producing a dark blue dye, woad , Lat. Isatis tinctoria , "
                "Hp. ll.cc., Thphr. Sens. 77 , Dsc. 2.184 .")
        self.assertEqual(r["Isatis tinctoria"]["dsc"], ["2.184"])         # "Hp. ll.cc." is Hippocrates


class Ibidem(unittest.TestCase):                                # audit 1 bug 2, audit 2 issue 2
    def test_ib_keeps_ps_dsc(self):
        r = ids("Artemisia campestris . = A. scoparia, Ps.- Dsc. 3.113 , ib. 114 .")
        self.assertEqual(r["Artemisia scoparia"]["pseudo_dsc"], ["3.113", "3.114"])
        self.assertEqual(r["Artemisia scoparia"]["dsc"], [])

    def test_ib_keeps_dsc(self):
        self.assertEqual(ids(HELENION)["Inula helenium"]["dsc"], ["1.28"])

    def test_ib_after_other_author_is_not_dioscorides(self):
        self.assertEqual(ids(BRYON)["Ulva lactuca"]["dsc"], ["4.98"])

    def test_ib_with_book_number(self):
        r = ids("Iris florentina , Ps.- Dsc. 4.13 ; ib. 4.109 .")
        self.assertEqual(r["Iris florentina"]["pseudo_dsc"], ["4.13", "4.109"])

    def test_ib_after_unrecognised_citation_is_for_review(self):
        r = ids("Acorus calamus , Dsc. 1.2 , IG 2.61 , ib. 5 .")
        self.assertEqual(r["Acorus calamus"]["dsc"], ["1.2"])
        self.assertEqual([u["ref"] for u in r["Acorus calamus"]["uncertain_ib"]], ["1.5"])

NARD = ("spikenard, Nardostachys Jatamansi , Thphr. HP 9.7.2 , Ev.Marc. 14.3 ; n. *)indikh/ Dsc. 1.7 , etc.; "
        "mountain nard, Valeriana Dioscoridis , Dsc. 1.9 (cf. Thphr. HP 9.7.4 ). n. *suriakh/ Syrian nard, "
        "Cymbopogon Iwarancusa , Dsc. 1.7 , cf. Plin. HN 12.45 .")
PINE = ("pine , esp. Pinus Laricio, Corsican pine , Il. 13.390 ; also, Aleppo pine, P. halepensis , Thphr. HP 3.9.5 , "
        "Gp. 2.8.2 (called p. a)gri/a Thphr. HP 1.9.3 ); stone pine, P. pinea , Theoc. 5.49 , Dsc. 1.69 , 72 .")
BULB = ("b. e)metiko/s , = Narcissus Tazetta , Dsc. 4.156 ; b. a)/grios, = kolxiko/n , ib. 4.83 ; b., = na/rkissos , "
        "Ps.- Dsc. 4.158 .")
APPLE = ("citron, Citrus Medica , Thphr. HP 1.11.4 ; also called h( *mhdikh\\ m. Thphr. CP 1.18.5 ; m. *kudwni/a quince, "
         "malus Punica , Dsc. 1.115 .")
LOTUS = ("Nile water-lily, Nymphaea Lotus , Dsc. 4.113 ; also, Nymphaea Nelumbo , Ath. 3.73a . of trees found in Libya, "
         "nettle-tree, Celtis australis , Thphr. HP 1.5.3 , Dsc. 1.117 , etc.")


class MoreSenseBoundaries(unittest.TestCase):                   # round 2, found while checking the rerun
    def test_circumflex_is_not_an_equals_sign(self):
        r = ids("plantain, Plantago major, Thphr. HP 7.8.3 , Luc. Trag. 150 ; a). to\\ mei=zon Dsc. 2.126 . "
                "haresfoot plantain, P.Lagopus, a). to\\ mikro/n ibid.")
        self.assertEqual(r["Plantago major"]["dsc"], ["2.126"])

    def test_variety_without_gloss_keeps_the_plant(self):
        self.assertEqual(ids(NARD)["Nardostachys jatamansi"]["dsc"], ["1.7"])

    def test_bracket_full_stop_ends_a_sense(self):
        self.assertEqual(ids(NARD)["Valeriana dioscoridis"]["dsc"], ["1.9"])

    def test_semicolon_new_binomial(self):
        r = ids(PINE)
        self.assertEqual(r["Pinus halepensis"]["dsc"], [])
        self.assertEqual(r["Pinus pinea"]["dsc"], ["1.69"])   # known limit: the bare ", 72" (= 1.72) is not read

    def test_ib_with_book_in_another_sub_sense(self):
        self.assertEqual(ids(BULB)["Narcissus tazetta"]["dsc"], ["4.156"])

    def test_sub_sense_with_own_gloss(self):
        self.assertEqual(ids(APPLE)["Citrus medica"]["dsc"], [])

    def test_citation_closed_by_full_stop(self):
        r = ids(LOTUS)
        self.assertEqual(r["Nymphaea nelumbo"]["dsc"], [])
        self.assertEqual(r["Celtis australis"]["dsc"], ["1.117"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
