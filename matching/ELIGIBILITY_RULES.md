# Eligibility rules: which candidates we show to the end user

One rule book for every old text (Culpeper, Dioscorides, and any book
added later). It decides which candidate plants are backed well enough
to be presented as the identification of a herb, before any medical
claim is attached. Each rule has an ID, so every decision can say which
rule placed a candidate where.

Tiers: A (shown as the identification), B (shown with a caveat),
X (never shown, kept in the data with the reason).

Status: in code, matching/eligibility.py (output matching/<book>/eligibility.json).

Basis: our own pipeline (name evidence, scientific names, geography),
extended     with the method of Lardos et al. (2024) [1], a Kew-led study
that scores how well a historical plant description fits each candidate
species, using Dioscorides (Wellmann's edition) as its reference text.
Its main warnings shape these rules:
- identifications taken from dictionaries and glossaries are often
  questionable and must not be adopted uncritically (A4, B5);
- the book's own description of the plant is the most objective
  evidence, because it is observable and stable over time (D);
- medicinal uses change over time and are supplementary only (M);
- one historical name can legitimately cover several related species
  (plant complexes, "ethnotaxa") (P).


## Words used here

- Entry: a herb (Culpeper) or a chapter (Dioscorides).
- Book name: a name the book itself gives the entry, with its quote.
- Candidate: an accepted plant name reached from a book name, after
  the scientific phase (WFO, WCVP, Global Names, IPNI).
- Lineage: a group of sources that copy each other. Agreement only
  counts between different lineages (see L1).
- Passage-specific identification: a scholarly work that names a plant
  for this very passage (LSJ citing "Dsc. 4.75" for chapter 4.75).
- Description check: how well the book's own description of the plant
  (leaves, flowers, root, habitat ...) fits a modern description of the
  candidate (D rules).


## L. Lineages: when sources count as independent

L1  Sources that copy each other count once:
      GBIF + Catalogue of Life (all releases) + ChecklistBank copies of either
      Wikidata (labels in any language) + ChecklistBank's copy of Wikidata
      iNaturalist + ChecklistBank's copy of iNaturalist
      NCBI (TaxTree)
      Dr. Duke's
      each other ChecklistBank project (a national checklist, ...)
      all private ChecklistBank checklists together, as one
      LSJ
      Lewis & Short
L2  The scientific databases (WFO, WCVP, Global Names, IPNI) check
    names; they are never counted as evidence that a name means a plant.


## E. Evidence grades (as in the aggregation)

E1  Strong: a book name equals a source's name for the plant (exact
    match), or a scholarly work identifies the plant for this very
    passage.
E2  Medium: a scholarly work identifies the plant for the book name in
    another passage; a Greek or Latin label in Wikidata.
E3  Weak: a loose match (the name inside a longer name, a fuzzy or
    similar-name hit), or the book name merely equals a genus name.
    Weak evidence never makes a candidate eligible on its own.


## A. Shown as the identification (all must hold)

A1  It is a plant: its accepted name is in WFO or WCVP. Fungi, animals
    and minerals are not plants (see X4).
A2  Species level or below (a genus or family alone is never shown, X6).
A3  Name settled: accepted in WFO or WCVP, and WFO and WCVP do not
    point to different accepted plants for it.
A4  Backed by enough independent evidence, one of:
      a) strong evidence from at least 2 different lineages (a single
         setting, MIN_LINEAGES = 2, easy to raise later), or
      b) a passage-specific identification (E1) confirmed by either a
         second lineage (strong or medium) or a description check of
         at least "moderate" (D3).
    A scholarly identification alone is not enough: dictionaries and
    glossaries are often wrong [1]; on its own it gives B5.
A5  It fits the author's world (G rules).
A6  Where the book describes the plant, the description check
    decides confidence, as in [1]: at least "moderate" (D3). Name
    evidence (A4) only proposes the candidate. Where the book gives no
    description (crops and well-known herbs often are not described,
    D6), A4 alone is enough; missing data never counts against a
    candidate (D2). In eligibility.json the rule is then listed as
    "A6 n/a" (no description to check), not "A6" (described, and the
    description fits). (Changed 2026-11-06, Marselo's second audit.)

    The description states, as stored in eligibility.json:
      no description record   the entry was not in the description check
      too few details         the book describes too little (fewer than
                              3 feature groups): nothing to check (D4)
      not compared            described, but this candidate was not
                              among those compared (B7)
      no comparable data      compared, but every score is "absent":
                              no feature could be matched (B7)
      fits / fits, Wikipedia only   at least moderate (D3)
      weak                    compared, below moderate, no group
                              negative (B6)
      poor                    an explicit mismatch: at least one feature
                              group scored negative (B6)
    Only weak and poor lower a candidate.

When an entry has more than one A candidate, all are shown; the one
with the most lineages, then the best description check, is listed
first ("most likely"), the others as "also possible". Several A
candidates are expected where the book means several plants (a heading
like "Mallows and Marshmallows") or a plant complex (P1).


## B. Shown as a possible identification, with a caveat

B1  A1, A2 and A5 hold, but the evidence is one lineage only (strong
    or medium). Caveat: "one source".
B2  A1, A2, A4 hold, but WFO and WCVP disagree on the accepted name.
    Both names are shown (other_accepted_names in eligibility.json,
    since 2026-11-06). Caveat: "botanists disagree on the name".
B3  A1, A2, A4 hold, but where it grows is unknown (no distribution
    data) or it is only introduced there with no date. Caveat: "may
    not have grown there in the author's time".
B4  Settled only by Global Names (not in WFO or WCVP), with A4.
    Caveat: "name not in the main plant lists".
B5  A1, A2, A5 hold, backed only by a scholarly identification (one
    lineage) without confirmation (A4b). Caveat: "identified by a
    dictionary only".
B6  A1-A5 hold, but the description check is "weak" (D3, D4).
    Caveat: "the book's description fits poorly". A candidate with no
    usable scores was not compared: B7, not B6. (Changed 2026-11-06,
    Marselo's audit: Typha domingensis in 3.118.) Scores that are all
    "absent" are no comparison either: B7 (round 2: Asparagus
    aphyllus, Prickly Asparagus; 29 candidates).
B7  A1-A5 hold and the book describes the plant, but this candidate
    was never compared with the description (no modern description
    found, or not among the candidates checked). Caveat: "not compared
    with the book's description". (Added 2026-11-05: without it, an
    unchecked candidate could pass A6 in an entry whose checked
    candidates all fit poorly.)

B9  Geography not checked: there is no geography record for the
    candidate, or it was not checked. Kept apart from B3 (checked, but
    no distribution data or introduced only). Missing data never hides
    a candidate (X2 needs a checked distribution far away). (Added
    2026-11-06, Marselo's second audit.)

B candidates are shown to the end user, marked with their caveat, in a
section of their own (separate from the A identifications).


## X. Never shown (kept in the data, with the reason)

X1  Weak evidence only (E3).
X2  It does not fit the author's world: native only far away (G2), or
    impossible for the period (G3).
X3  Not tied to an accepted name in any database.
X4  Not a plant (animal, fungus, mineral, virus). Kept apart for a
    later "other materia medica" list (beaver, murex, ...). In code: a
    source says "non-plant" and none says "plant". Until 2026-11-06
    (round 2) X4 also covered X7. (Changed 2026-11-06, Marselo's audit: "unknown"
    alone used to hide plants such as Berberis × ottawensis; Global
    Names alone also covers animals, such as the shrew Sorex araneus.)
X7  Plant status not established: the kingdom is unconfirmed
    ("unknown", "mixed") and no plant list (WFO, WCVP) knows the name.
    Hidden, because A1 needs WFO or WCVP, but not called "not a plant":
    mostly animals and seaweeds resolved only by Global Names (the
    shrew, Sorex araneus; Castor; Cyprinus). (Added 2026-11-06,
    Marselo's second audit.)
X8  Rank not established: the plant lists give no rank and the name
    has two or more words, so it may not be a species (A2 cannot be
    confirmed). Hidden, like X6, but kept with its evidence. (Added
    2026-11-06, Marselo's second audit and his contract test.)
X5  Reached only through a name the book does not use for this entry
    (for example a word from the description, not a name).
X6  Genus or family level only (Mosses -> Bryophyta, Chick-Pease ->
    Cicer): too vague to present as a plant, even with strong evidence.
    When the rank is missing, a one-word name counts as a genus (or a
    family if it ends in -aceae). (Added 2026-11-06, Marselo's audit:
    Plantago was shown for Buck's-Horn Plantain.)


## D. Description check (after Lardos et al. 2024 [1])

D1  Features compared, each from the book's description and a modern
    description of the candidate, grouped as in [1]: life form (1),
    habit (3), height (1), stem (4), leaf (7), flower (3), fruit (5),
    seed (3), root (4), properties such as smell or taste (2),
    habitat (1), distribution (1). Numbers are the details per group.
    These are 12 of the 13 groups in [1]; its 13th, ethnobotany (uses),
    belongs to M.
D2  Each detail is scored: good match +2, partial match +1, no match
    -2, no data on either side 0. Scores are averaged within each
    group, so richly described organs do not dominate. Missing data is
    never held against a candidate.
D3  Degree of fit = sum of positive groups - sum of negative groups:
      strong    5 or more
      moderate  3 to 4
      weak      2 or less
    Thresholds can be tuned as in [1]; the value used is recorded.
D4  "Weak with explicit mismatches" means at least one group scored
    negative; a weak score from missing data alone is "not assessable",
    not weak.
D5  Every comparison keeps the book's words, the modern description
    used and its source, so each score can be checked. AI may extract
    and compare features, but each step is recorded, never just a
    final verdict.
D6  Only part of a book can be checked: in [1] only 24% of Dioscorides'
    plants had rich descriptions; crops and well-known herbs are often
    not described at all. D therefore raises or lowers confidence; it
    is required only where A4b relies on it.
D7  Sources of modern descriptions, by preference (from the hackathon
    dataset list):
      WCVP: not used here. It has no description text, only a short
        life form; a keyword test of that against the author's text
        (2026-11-04) was too fragile to keep. Its distribution is
        still used by the geography check (G rules)
      POWO (Kew; descriptions, distributions, images): web only; it
        blocks scripts and also refused the sponsor's Anakin service
        (tested 2026-11-04), so it is not used
      BHL (Biodiversity Heritage Library, API v3 with a free key):
        full text of historical floras, e.g. Boissier's Flora
        Orientalis (eastern Mediterranean) and British floras; OCR is
        noisy and descriptions are in Latin
      Wikipedia (CC BY-SA, official MediaWiki API, no key): plant pages often
        have a Description section; WEAK: an encyclopedia, not a flora,
        uneven in detail. A check that rests only on Wikipedia counts
        at most "weak" support: it can lower confidence (an explicit
        mismatch) but cannot by itself lift a candidate to A. In code:
        a Wikipedia-only fit satisfies A6 when the name evidence already
        holds (A4a), but never confirms a dictionary identification (A4b).
      Images (Wikimedia Commons, BHL Flickr, GBIF, iDigBio): left out
        for now


## P. Plant complexes (after [1])

P1  When several A candidates of one entry belong to the same genus,
    they are shown together as one group ("related plants used under
    this name"), not as competing answers. Example from [1]:
    Dioscorides' three kinds of chamaipitys (Ajuga species).


## M. Medicinal uses (later)

M1  Agreement between the book's uses and modern uses of a candidate is
    supplementary evidence only. It never decides an identity: uses
    change over time and modern data are patchy [1].


## G. Geography: the author's world (one setting per book)

G1  Fits: native or introduced in the book's home area, or native in
    its wider world.
      Culpeper (England, 1650s): home Britain and Ireland; wider:
        Europe (garden plants and imported drugs)
      Dioscorides (eastern Mediterranean, 1st century): home the
        Mediterranean and Near East; wider: his trade world (Arabia,
        NE Africa, India, Caucasus, Central Asia, China, SE Asia)
      Shennong Bencao Jing (Han China, 1st-2nd century): home China;
        wider: the lands the Han knew (Mongolia, Korea and Japan,
        Siberia and the Russian Far East, Central and Western Asia,
        Indo-China, India, Malesia). (Added 2026-11-06.)
G2  Far: native only outside home and wider world.
G3  Impossible for the period: for books before 1492, a plant native
    only to the Americas, Australasia or the Pacific.
G4  Distribution from WCVP (where plants grow today); it carries no
    dates, so "introduced" alone never proves the author knew it.
G5  Like [1], we assume the flora of a region has changed little in
    which species are present since the author's time; abundance may
    have changed, and humans have moved plants.


## The Shennong Bencao Jing (added 2026-11-06)

Its evidence (matching/shennong/aggregate.py) plays the same roles:
  strong (passage-specific, like LSJ): Bretschneider's own verdict on
    what the drug is (Botanicon Sinicum III, 1895), proposed by Claude
    and checked by a person (historical_texts/shennong/review/)
  medium: his reading of a Chinese illustration, the name's 19th-century
    usage in China, a drug sample he examined; an author he quotes
    (Loureiro, Tatarinov, Henry ...: each its own lineage); Wikidata
    crude drugs (P1582) and Chinese labels on the headword
  weak: Wikidata labels on other names (一名, Wu Pu, Famous Physicians);
    anything Bretschneider calls doubtful
  left out: Japanese usage and Japanese works he quotes (the same
    characters can name another plant in Japan)
There is no description check: the classic describes no plants, so A6
is "n/a". Animals and minerals (kind from the plain Wikisource version)
are not identified. B5 reads "identified by one scholar only
(Bretschneider)".


## Known limits

- Candidates come only from the sources' suggestions, not from the
  whole flora of the author's region; the right plant can be missing
  from the list. [1] names the same limit and recommends comparing
  against the complete regional flora where possible.
- Name evidence and dictionaries can share errors; lineages (L1) only
  remove copies we know about.


## Decisions taken

- A4a: 2 independent lineages (MIN_LINEAGES = 2), following [1]: name
  evidence only proposes candidates; confidence comes from the
  description check where the book has a description (A6). May be
  raised later by changing the one setting.
- B candidates are shown, marked, in their own section.
- Description sources (D7): BHL, and Wikipedia as weak evidence; WCVP's
  life form was tested and dropped;
  images are left out for now. POWO was tested through Anakin and
  refuses it (as it refuses scripts), so it is not used.


## Adding a new book

To use these rules, a new book needs:
1. its extraction: entries, book names, and a quote for every name;
2. a bridge from its names to scientific names, graded with E1-E3,
   with each source assigned to a lineage (L1);
3. its G1 setting (home area, wider world, and whether it predates
   1492);
4. where it has plant descriptions, the passages for the D check;
5. the shared steps: scientific phase, then these rules.


## References

[1] Lardos, A., Patmore, K., Allkin, R., Lazarou, R., Nesbitt, M.,
    Scott, A. C., Zipser, B. (2024). A systematic methodology to assess
    the identity of plants in historical texts: A case study based on
    the Byzantine pharmacy text John the Physician's Therapeutics.
    Journal of Ethnopharmacology 322, 117622.
    https://doi.org/10.1016/j.jep.2023.117622 (open access, CC BY 4.0)
