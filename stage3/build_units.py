"""Stage 3, step 2: build the claim × plant units (STAGE3_DATA_CONTRACT.md §2) and the
MeSH -> medicinal use group map (Lardos et al. 2024, 21 groups). Code only: no model, no network.

Usage:  python3 stage3/build_units.py

Reads (read-only):  claims/<book>/claims.json, claims/links.json, matching/<book>/eligibility.json,
                    matching/<book>/herb_candidates_resolved.json, reference_sources/mesh/mesh_index.json.gz
Writes:  stage3/mesh_use_groups.csv     every MeSH term used by a claim -> use group(s), with the rule
         stage3/units/<book>.jsonl      every claim × A/B plant
         stage3/units/pilot.jsonl       the pilot: for each PILOT plant, its 3 largest shared groups
                                        (same plant + MeSH term in both books, tier A in both), one
                                        claim per book from each, so both books and many concepts appear
         stage3/units/shared.jsonl      every shared group (670): one claim per book (its first tier-A
                                        claim, else its first claim) for the group's plant, with the
                                        group's details for ordering (A in both books first, then size)
"""
import csv
import gzip
import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BOOKS = ("culpeper", "dioscorides")
SCHEMA = "0.1"
EDITIONS = {"culpeper": "Project Gutenberg #49513", "dioscorides": "Wellmann 1906-14, First1KGreek TEI"}
PILOT_GROUPS_PER_PLANT = 3                       # shared plant + MeSH groups per pilot plant
PILOT = ["Ruta graveolens L.", "Plantago major L.", "Marrubium vulgare L.", "Inula helenium L.",
         "Daucus carota L.", "Glycyrrhiza glabra L.", "Tanacetum parthenium (L.) Sch.Bip.",
         "Achillea millefolium L."]

# The 21 groups of Lardos et al. 2024 (data file 10, sheet "Med use groups")
GROUPS = {"AN": "Andrology", "BS": "Blood, spleen", "CV": "Cardiovascular disorders", "DE": "Dermatology",
          "FV": "Fever", "GI": "Gastrointestinal tract", "GY": "Gynaecology", "ID": "Infectious diseases",
          "LG": "Liver and gall bladder", "MA": "Maternity", "MC": "Mental conditions",
          "MN": "Metabolic & nutritional disorders", "MS": "Musculoskeletal", "NC": "Neurological conditions",
          "OP": "Ophthalmology", "OC": "Oral cavity", "OT": "Otology", "RE": "Respiratory tract",
          "RL": "Rhino-Laryngology", "UR": "Urology", "XY": "Residual category"}

# 1. A MeSH term or one of its ancestors with exactly this name -> group (checked first, most specific wins)
BY_NAME = {
    # signs and symptoms placed as in the paper's examples
    "Fever": "FV", "Malaria": "FV", "Edema": "CV", "Headache": "NC", "Abdominal Pain": "GI", "Arthralgia": "MS",
    "Signs and Symptoms, Digestive": "GI", "Signs and Symptoms, Respiratory": "RE", "Cough": "RE",
    "Hemorrhoids": "CV", "Bites and Stings": "DE", "Fractures, Bone": "MS", "Sprains and Strains": "MS",
    "Dislocations": "MS", "Gout": "MS", "Sciatica": "MS", "Spasm": "MS", "Paralysis": "MS",
    "Liver Diseases": "LG", "Biliary Tract Diseases": "LG", "Jaundice": "LG",
    "Mouth Diseases": "OC", "Tooth Diseases": "OC", "Toothache": "OC", "Pharyngeal Diseases": "RL",
    "Nose Diseases": "RL", "Laryngeal Diseases": "RL", "Ear Diseases": "OT", "Eye Diseases": "OP",
    "Genital Diseases, Male": "AN", "Genital Diseases, Female": "GY", "Pregnancy Complications": "MA",
    "Puerperal Disorders": "MA", "Urologic Diseases": "UR", "Urinary Calculi": "UR",
    "Splenic Diseases": "BS", "Tuberculosis": "ID",
    "Ulcer": "DE",            # old herbals' "ulcers" are mostly sores on the skin (the paper puts skin disorders in DE)
    # drug actions (MeSH D27)
    "Diuretics": "UR", "Menstruation-Inducing Agents": "GY", "Cathartics": "GI", "Laxatives": "GI",
    "Emetics": "GI", "Antiemetics": "GI", "Antidiarrheals": "GI", "Anthelmintics": "GI",
    "Abortifacient Agents": "MA", "Oxytocics": "MA", "Galactogogues": "MA", "Contraceptive Agents": "GY",
    "Expectorants": "RE", "Antitussive Agents": "RE", "Antipyretics": "FV", "Hypnotics and Sedatives": "MC",
    "Antidepressive Agents": "MC", "Anticonvulsants": "NC", "Aphrodisiacs": "AN", "Cardiotonic Agents": "CV",
    "Hemostatics": "BS", "Dentifrices": "OC", "Mouthwashes": "OC", "Emollients": "DE", "Hair Dyes": "DE",
    "Cosmetics": "DE", "Caustics": "DE", "Anti-Infective Agents": "ID", "Appetite Stimulants": "MN",
    "Anti-Obesity Agents": "MN",
    # body processes and parts (MeSH G, A)
    "Menstruation": "GY", "Lactation": "MA", "Diuresis": "UR", "Urination": "UR", "Digestion": "GI",
    "Defecation": "GI", "Mucus": "RE", "Labor, Obstetric": "MA", "Postpartum Period": "MA", "Placenta": "MA",
    "Pregnancy": "MA", "Spermatogenesis": "AN", "Semen": "AN", "Ejaculation": "AN", "Wound Healing": "DE",
    "Granulation Tissue": "DE", "Hair": "DE", "Tears": "OP", "Salivation": "OC", "Sleep": "MC",
    "Shivering": "FV", "Uvula": "RL", "Liver": "LG", "Kidney": "UR", "Heart": "CV", "Uterus": "GY",
    "Cervix Uteri": "GY", "Breast": "MA", "Eyelashes": "OP", "Brain": "NC", "Urinary Bladder": "UR",
    "Urinary Tract": "UR", "Ascaris": "GI",
}
# 2. Otherwise by MeSH tree branch
BY_TREE = [("C01", "ID"), ("C05", "MS"), ("C06", "GI"), ("C07", "OC"), ("C08", "RE"), ("C09", "RL"),
           ("C10", "NC"), ("C11", "OP"), ("C12", "UR"), ("C13", "GY"), ("C14", "CV"), ("C15", "BS"),
           ("C17", "DE"), ("C18", "MN"), ("C19", "MN"), ("C26", "DE"), ("F01", "MC"), ("F02", "MC"),
           ("F03", "MC")]
# 3. Everything else -> XY (residual), recorded as such


def git_head() -> str:
    try:
        return subprocess.run(["git", "--no-optional-locks", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return "unknown"


def use_groups(ui: str, D: dict, tree_name: dict) -> tuple:
    """(groups, rule): every tree of the term is mapped; the residual XY is dropped if a specific group exists."""
    groups, rules = [], []
    for t in D[ui]["trees"] or [""]:
        chain = [t[:i] for i in range(len(t), 0, -1) if i == len(t) or t[i] == "."]
        hit = next(((tree_name.get(p), BY_NAME[tree_name.get(p)]) for p in chain if tree_name.get(p) in BY_NAME), None)
        if not hit and D[ui]["name"] in BY_NAME:
            hit = (D[ui]["name"], BY_NAME[D[ui]["name"]])
        if hit:
            g, rule = hit[1], f"name: {hit[0]}"
        else:
            g = next((grp for pre, grp in BY_TREE if t.startswith(pre)), "XY")
            rule = f"tree: {t[:3]}" if g != "XY" else "residual"
        if g not in groups:
            groups.append(g)
            rules.append(rule)
    if len(groups) > 1 and "XY" in groups:
        i = groups.index("XY")
        groups.pop(i)
        rules.pop(i)
    return groups, rules


def split_list(text: str) -> list:
    """'drink or pessary' -> ['drink', 'pessary']; only clear alternatives are split."""
    if not text:
        return ["unknown"]
    parts = [p.strip() for p in text.replace(";", " or ").split(" or ") if p.strip()]
    return parts or ["unknown"]


def main() -> None:
    mesh = json.load(gzip.open(ROOT / "reference_sources/mesh/mesh_index.json.gz", "rt", encoding="utf-8"))
    D = mesh["descriptors"]
    tree_name = {t: d["name"] for d in D.values() for t in d["trees"]}
    links = json.load(open(ROOT / "claims/links.json", encoding="utf-8"))["shared_claims"]
    shared = defaultdict(set)                       # claim_id -> the other books' claim_ids (same plant + term)
    pilot_claims, per_plant = set(), defaultdict(int)
    shared_pick = {}                                # (claim_id, species) -> the group, for shared.jsonl
    for gi, s in enumerate(sorted(links, key=lambda s: (not s["both_A"], -len(s["claims"]), s["species"], s["mesh"]))):
        for book in s["books"]:
            cs = [c for c in s["claims"] if c["book"] == book]
            first = next((c for c in cs if c["tier"] == "A"), cs[0] if cs else None)
            if first:
                shared_pick.setdefault((first["claim_id"], s["species"]), {
                    "order": gi, "species": s["species"], "mesh": s["mesh"], "mesh_ui": s["mesh_ui"],
                    "both_A": s["both_A"], "claims_in_group": len(s["claims"])})
    for s in links:
        ids = [c["claim_id"] for c in s["claims"]]
        for i in ids:
            shared[i] |= {x for x in ids if x.split(":")[0] != i.split(":")[0]}
    # pilot: per plant, its largest shared groups (tier A in both books), one claim per book from each
    for s in sorted(links, key=lambda s: (-len(s["claims"]), s["mesh"])):
        if s["both_A"] and s["species"] in PILOT and per_plant[s["species"]] < PILOT_GROUPS_PER_PLANT:
            per_plant[s["species"]] += 1
            for book in BOOKS:
                first = next((c["claim_id"] for c in s["claims"] if c["book"] == book and c["tier"] == "A"), None)
                if first:
                    pilot_claims.add(first)
    head, now = git_head(), datetime.now(timezone.utc).isoformat(timespec="seconds")
    used, out_dir = {}, HERE / "units"
    out_dir.mkdir(exist_ok=True)
    pilot, shared_units = [], []
    for book in BOOKS:
        claims = json.load(open(ROOT / "claims" / book / "claims.json", encoding="utf-8"))["entries"]
        elig = json.load(open(ROOT / "matching" / book / "eligibility.json", encoding="utf-8"))["herbs"]
        res = json.load(open(ROOT / "matching" / book / "herb_candidates_resolved.json", encoding="utf-8"))["herbs"]
        plants = {}                                  # claims' entry key -> [(row, taxon)]
        for key, h in elig.items():
            k = h["label"] if book == "dioscorides" else key
            taxa = {c.get("accepted_name"): c for c in res[key]["candidates"]}
            plants[k] = [(r, taxa.get(r["accepted_name"], {})) for r in h["shown"] + h["possible"]]
        n = 0
        with open(out_dir / f"{book}.jsonl", "w", encoding="utf-8") as f:
            for entry, e in claims.items():
                for c in e["claims"]:
                    cond, act, other = [], [], []
                    for m in c["mesh"]:
                        g, r = use_groups(m["ui"], D, tree_name)
                        used[m["ui"]] = (g, r)
                        item = {"ui": m["ui"], "name": m["name"], "match": m["match"]}
                        branches = {t[:3] if t.startswith("D27") else t[:1] for t in D[m["ui"]]["trees"]}
                        (cond if branches & {"C", "F"} else act if branches & {"D27", "G"} else other).append(item)
                    groups = sorted({g for m in c["mesh"] for g in used[m["ui"]][0]})
                    for row, taxon in plants.get(entry, []):
                        wfo = taxon.get("wfo_id") or "no-wfo-id"
                        unit = {
                            "schema_version": SCHEMA,
                            "unit_id": f"{c['claim_id']}|{wfo}", "claim_id": c["claim_id"],
                            "identification_id": f"{book}:{entry}:{wfo}",
                            "book": book, "edition": EDITIONS[book], "entry": entry, "entry_label": e["name"],
                            "quote": c["quote"], "quote_language": "grc" if book == "dioscorides" else "en",
                            "translation": c.get("translation"), "claim_text": c["claim"],
                            "relation": c["relation"], "kind": c["kind"],
                            "condition_concepts": cond, "action_concepts": act, "other_concepts": other,
                            "use_groups": groups,
                            "plant_part": c.get("part") or "unknown",
                            "preparation": split_list(c.get("preparation")),
                            "route": [c.get("route") or "unknown"],
                            "taxon": {"accepted_name": row["accepted_name"], "wfo_id": taxon.get("wfo_id"),
                                      "wcvp_id": taxon.get("wcvp_id"), "family": taxon.get("family")},
                            "identification": {"tier": row["tier"], "rules": row["rules"], "caveats": row["caveats"],
                                               "description_check": row.get("description")},
                            "shared_with": sorted(shared.get(c["claim_id"], ())),
                            "inputs": {"stage1_commit": head, "stage2_commit": head, "built_at": now}}
                        f.write(json.dumps(unit, ensure_ascii=False) + "\n")
                        n += 1
                        if c["claim_id"] in pilot_claims and row["accepted_name"] in PILOT:
                            pilot.append(unit)
                        g = shared_pick.get((c["claim_id"], row["accepted_name"]))
                        if g:
                            shared_units.append({**unit, "shared_group": g})
        print(f"{book}: {n:,} units")
    with open(out_dir / "pilot.jsonl", "w", encoding="utf-8") as f:
        for u in pilot:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    shared_units.sort(key=lambda u: (u["shared_group"]["order"], u["book"]))
    with open(out_dir / "shared.jsonl", "w", encoding="utf-8") as f:
        for u in shared_units:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    print(f"Shared: {len(shared_units)} units from {len({u['shared_group']['order'] for u in shared_units})} groups, "
          f"{sum(u['shared_group']['both_A'] for u in shared_units)} in groups with an A plant in both books")
    with open(HERE / "mesh_use_groups.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mesh_ui", "mesh_name", "groups", "group_names", "rule", "trees"])
        for ui, (g, r) in sorted(used.items(), key=lambda x: D[x[0]]["name"]):
            w.writerow([ui, D[ui]["name"], " ".join(g), "; ".join(GROUPS[x] for x in g), " | ".join(r),
                        " ".join(D[ui]["trees"])])
    resid = sum(1 for g, _ in used.values() if g == ["XY"])
    multi = sum(1 for g, _ in used.values() if len(g) > 1)
    print(f"MeSH -> use groups: {len(used)} terms · {resid} residual (XY) only · {multi} in more than one group "
          f"→ stage3/mesh_use_groups.csv")
    sp = defaultdict(int)
    for u in pilot:
        sp[u["taxon"]["accepted_name"]] += 1
    print(f"Pilot: {len(pilot)} units, {len({u['claim_id'] for u in pilot})} claims, {len(sp)} plants: "
          + ", ".join(f"{k} {v}" for k, v in sorted(sp.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
