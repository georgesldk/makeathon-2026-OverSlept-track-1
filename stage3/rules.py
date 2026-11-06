"""Stage 3 interpretation rules, in code (OverSlept_Stage3_Plan_FINAL.md §3.5, STAGE3_DATA_CONTRACT.md §4.2).

The model only extracts fields (relevance, evidence type, compatibility, outcome, excerpts).
These functions turn checked fields into the interpretation. They never look at the text,
never call a model, and never produce a single "supports" verdict:

  assess(fields, tier)      -> applicability, finding, rules_applied, modifiers, mismatches, unknowns, badge
  summarise(assessments)    -> claim-level lanes (regulatory / human / preclinical / traditional), kept apart
  ema_applicability(match)  -> whether an EMA monograph applies to the historical remedy

Decisions taken here (to confirm in EVIDENCE_RULES.md):
  - species "different" = another genus  -> not relevant (S3-0)
    species "related"   = same genus, other species -> indirect at most (S3-3)
  - condition "different" with action not "same"/"related" -> not relevant (S3-0)
  - a partial match because the condition is only related says so: "Partial (related condition)"
  - rules are checked in order S3-0 .. S3-8; every rule that fires is recorded
  - an in vitro study has no route of administration (the extract is put on cells or tissue), so
    its route is always "different" from the historical remedy: in vitro is never more than
    indirect, whatever the model wrote. Animal studies keep the route the model reports
    (an animal can be fed by mouth), but are always labelled preclinical.
"""

MATERIAL = ("plant_part", "preparation", "route")
CORE = ("species", "condition", "therapeutic_action")
PRECLINICAL = {"animal": "preclinical_animal", "in_vitro": "in_vitro"}
LABEL = {"systematic_review": "Systematic review", "human_rct": "Human RCT", "human_other": "Human study",
         "animal": "Animal", "in_vitro": "In vitro", "traditional_use_document": "Traditional-use document",
         "registered_trial": "Registered trial", "regulatory_monograph": "EMA monograph",
         "other": "Other", "unknown": "Unknown type"}
EMA_USE = {"traditional_use": "traditional use, not proof of efficacy",
           "well_established_use": "well-established use", "use_type_unstated": "use type not stated"}
ORDER = ["direct", "partial", "indirect"]


def _val(fields: dict, name: str) -> str:
    """A compatibility value, "unknown" when missing or voided by the excerpt check."""
    voided = set((fields.get("validation") or {}).get("fields_voided", []))
    if name in voided:
        return "unknown"
    v = (fields.get("compatibility") or {}).get(name) or {}
    return v.get("value", "unknown") if isinstance(v, dict) else (v or "unknown")


def _worst(a: str, b: str) -> str:
    return a if ORDER.index(a) >= ORDER.index(b) else b


def assess(fields: dict, tier: str = "A") -> dict:
    voided = set((fields.get("validation") or {}).get("fields_voided", []))
    relevance = "unclear" if "relevance" in voided else fields.get("relevance", "unclear")
    etype = "unknown" if "evidence_type" in voided else fields.get("evidence_type", "unknown")
    outcome = (fields.get("outcome") or {}).get("value", "unclear")
    if "outcome" in voided:
        outcome = "unclear"
    comp = {k: _val(fields, k) for k in CORE + MATERIAL}
    if etype == "in_vitro":                                # no route in a dish
        comp["route"] = "different"
    rules, mods = [], []
    out = {"applicability": None, "finding": None, "rules_applied": rules, "modifiers": mods,
           "mismatches": [k for k, v in comp.items() if v == "different"],
           "unknowns": [k for k, v in comp.items() if v == "unknown"]}

    # S3-0 not relevant: another question, not the plant, another genus, or another condition
    if (relevance in ("different_question", "not_about_the_plant") or comp["species"] == "different"
            or (comp["condition"] == "different" and comp["therapeutic_action"] not in ("same", "related"))):
        rules.append("S3-0")
        out.update(applicability="not_relevant", finding=None)
        return _finish(out, etype, tier, fields.get("ema_use"))

    # S3-1 unassessable: relevance not established, or the species cannot be told
    if relevance in ("unclear", "unknown") or comp["species"] == "unknown":
        rules.append("S3-1")
        out.update(applicability="unassessable", finding=None)
        return _finish(out, etype, tier, fields.get("ema_use"))

    # applicability, from the most to the least comparable
    app = "direct"
    if relevance == "related":
        app = _worst(app, "partial")
    if comp["species"] == "related" or any(comp[k] == "different" for k in MATERIAL):
        rules.append("S3-3")                               # mismatch: at most indirect
        app = _worst(app, "indirect")
    if any(comp[k] == "related" for k in ("condition", "therapeutic_action")):
        if "S3-3" not in rules:
            rules.append("S3-3")
        app = _worst(app, "partial")
    if any(comp[k] == "related" for k in MATERIAL):
        rules.append("S3-3") if "S3-3" not in rules else None
        app = _worst(app, "partial")                       # a related part, preparation or route is not a match
    if any(comp[k] == "unknown" for k in MATERIAL + ("condition", "therapeutic_action")):
        rules.append("S3-4")                               # missing detail is never a match
        app = _worst(app, "partial")
    if app == "direct":
        rules.append("S3-5")                               # every element explicitly the same
    out["applicability"] = app
    if app == "partial" and comp["condition"] == "related":
        mods.append("related_condition")                   # said in the badge: not the claim's own condition
    for k in MATERIAL:
        if comp[k] == "different":
            mods.append(f"different_{k}")

    # S3-2 / S3-6 finding, independent of applicability
    if outcome == "not_reported":
        rules.append("S3-2")
    else:
        rules.append("S3-6")
    out["finding"] = outcome
    return _finish(out, etype, tier, fields.get("ema_use"))


def _finish(out: dict, etype: str, tier: str, ema_use: str = None) -> dict:
    if etype in PRECLINICAL:                               # S3-7 never clinical efficacy
        out["rules_applied"].append("S3-7")
        out["modifiers"].append(PRECLINICAL[etype])
    if tier != "A":                                        # S3-8 identification uncertainty travels
        out["rules_applied"].append("S3-8")
        out["modifiers"].append("possible_historical_identification")
    if etype == "regulatory_monograph":                    # an indication granted, not a study result
        out["modifiers"].append(f"ema_{ema_use or 'use_type_unstated'}")
    app = out["applicability"].replace("_", " ").capitalize()
    if "related_condition" in out["modifiers"]:
        app += " (related condition)"
    fin = (out["finding"] or "").replace("_", " ").capitalize()
    if etype == "regulatory_monograph" and out["finding"] == "positive":
        fin = f"Indication listed ({EMA_USE[ema_use or 'use_type_unstated']})"
    out["badge"] = " · ".join(x for x in (LABEL.get(etype, etype), app, fin) if x)
    out["evidence_type"] = etype
    return out


def lane(etype: str) -> str:
    if etype in ("systematic_review", "human_rct", "human_other", "registered_trial"):
        return "human"
    if etype == "regulatory_monograph":
        return "regulatory"
    if etype in PRECLINICAL:
        return "preclinical"
    if etype == "traditional_use_document":
        return "traditional"
    return "other"


LEVELS = (("direct", "direct"), ("partial", "partial match only"), ("indirect", "indirect only"))


def _summary(results: list, regulatory: bool = False) -> str:
    found = {r["finding"] for r in results if r["finding"] in ("positive", "negative", "mixed")}
    if regulatory:
        return "indication listed" if "positive" in found else "no matching indication"
    if len(found) > 1 or "mixed" in found:
        return "mixed/conflicting"
    return found.pop() if found else "no outcome evidence"


def summarise(assessments: list) -> dict:
    """S3-9: claim level. Every result kept; lanes never merged; conflicts stay visible.
    Each lane is summarised from its best-fitting studies only (direct, else partial, else indirect),
    and the summary says which: "positive (indirect only)" can never read as "positive"."""
    lanes = {}
    for a in assessments:
        if a["applicability"] in ("not_relevant", "unassessable"):
            continue
        l = lanes.setdefault(lane(a["evidence_type"]), {"results": [], "summary": None})
        l["results"].append({"badge": a["badge"], "applicability": a["applicability"], "finding": a["finding"]})
    for name, l in lanes.items():
        reg = name == "regulatory"
        for level, label in LEVELS:
            best = [r for r in l["results"] if r["applicability"] == level]
            if best:
                break
        if level == "partial" and all("related condition" in r["badge"] for r in best):
            label += ", related condition"
        summary = f"{_summary(best, reg)} ({label})"
        if reg and any("traditional use" in r["badge"] for r in best):
            summary += " · traditional use only, not proof of efficacy" if all("traditional use" in r["badge"] for r in best) else ""
        rest = [r for r in l["results"] if r["applicability"] != level]
        if rest and _summary(rest, reg) != _summary(best, reg) and _summary(rest, reg) not in ("no outcome evidence", "no matching indication"):
            summary += " · less direct studies differ"
        l["summary"], l["based_on"] = summary, level
    if not lanes:
        return {"lanes": {}, "search": "nothing assessable found (not the same as not studied)"}
    return {"lanes": lanes}


def ema_applicability(matches: dict) -> dict:
    """An EMA monograph applies only when preparation, route and indication all match or are related."""
    bad = [k for k in ("preparation", "route", "indication") if matches.get(k) not in ("same", "related")]
    return {"applicable": not bad, "mismatches": bad}
