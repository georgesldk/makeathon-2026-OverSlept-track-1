"""Where each Stage 3 run lives. A "set" is a list of units plus every output made from it.

  pilot   the 44 pilot units, first retrieval (PubMed only). Frozen: the reviewed results.
  pilot2  the same 44 units, retrieval v2 (all sources), to compare with pilot.
  shared  the groups Culpeper and Dioscorides share (same plant + MeSH term): one claim per book per group.
  shennong  the Shennong Bencao Jing's claims about its A plants, and its claims in groups it shares with
          Culpeper or Dioscorides (claims with a MeSH concept only).
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETS = ("pilot", "pilot2", "shared", "shennong")


def paths(name: str) -> dict:
    if name not in SETS:
        raise SystemExit(f"Unknown set {name!r}; choose from {', '.join(SETS)}")
    units = HERE / "units" / {"shared": "shared.jsonl", "shennong": "shennong_set.jsonl"}.get(name, "pilot.jsonl")
    if name == "pilot":                     # the original layout, kept so the reviewed pilot stays as it was
        return {"units": units, "studies": HERE / "studies", "web": HERE / "web",
                "assessments": HERE / "assessments" / "v1", "graph": HERE / "graph"}
    return {"units": units, "studies": HERE / "studies" / name, "web": HERE / "web" / name,
            "assessments": HERE / "assessments" / name, "graph": HERE / "graph" / name}
