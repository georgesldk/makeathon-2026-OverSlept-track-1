# Textual matching rules

How a historical herb name becomes a list of scientific-name
candidates. Text only: no meaning, no AI, no ranking.
Code: the source scripts (searching) and matching/*/aggregate.py
(grading and grouping).


## 1. What gets searched

Every name the book gives a herb: the heading plus every other
name ("Amara Dulcis", "Bitter-sweet", "Woody Night-shade").

Each name is sent in these spellings (`spellings()` in
common_name_sources/gbif/culpeper/source_gbif.py, shared by every source):
- as written
- hyphens as spaces ("Woody Night shade")
- hyphens removed ("Woody Nightshade")
- last word made singular ("Mallows" -> "Mallow")
- "Tree" / "Bush" at the end removed ("Chesnut Tree" -> "Chesnut")

TaxTree also gets each spelling in lower case and in Latin form
(first word capitalised only).


## 2. When two names count as the same

Two names are equal when they are equal after `key()`:
lower case, and spaces, hyphens, apostrophes and full stops removed.
"Lady's Mantle" = "ladys mantle" = "Ladys-Mantle".
Nothing else is ignored: "Ladies" is not "Lady's".


## 3. Strong and weak evidence

Strong:
- exact      the source's name equals our spelling (rule 2)
- exact part one part of a listed name equals it; parts are split
             at , / ; and " or " ("Bittersweet, Felonwort")
- Wikidata: exact label, alias or taxon common name (P1843), on an
  item that is a taxon
- iNaturalist: exact name in any language/locale

Weak (kept, never counted in summaries):
- contains   our spelling only appears inside a longer name
             (Dr. Duke's, ChecklistBank)
- similar    a TaxTree similar-name (fuzzy) hit

Not kept as evidence: plain search results that are neither
(GBIF/Wikidata/iNaturalist look-alikes). They stay in the source
files.


## 4. Scientific names

Each candidate keeps its full name as the source wrote it.
For grouping it is normalised (`canonical()`):
- author dropped ("Solanum dulcamara L." -> "Solanum dulcamara")
- hybrid sign kept, written "×" ("Mentha x piperita" ->
  "Mentha × piperita")
- varieties and subspecies folded into the species, kept as a note
- "Abies sp." / "spp." / "cf." / "aff." -> genus level
- one word ending in -aceae -> family, other one word -> genus

Identical normalised names form one group. A group is a name, not
a plant: synonyms are NOT merged here. That is the job of the
scientific phase (WFO + WCVP).


## 5. Kingdom

Each row carries the kingdom its source gives (its own
classification). Spellings are unified: Viridiplantae -> Plantae,
Metazoa -> Animalia, Bacillati etc. -> Bacteria, any ...virae ->
Viruses. Anything else (e.g. "Regnum") counts as no answer.
A group is plant, non-plant, mixed (sources disagree, often a
genus name used for both a plant and an animal) or unknown.
Non-plant groups are kept, only flagged.


## 6. Independence

Copies are not independent evidence. Rows are grouped into source
families: GBIF, Wikidata, iNaturalist, Dr. Duke's, NCBI, Catalogue
of Life (all releases = one), each other ChecklistBank checklist
project (all releases = one); ChecklistBank's copies of GBIF,
iNaturalist and Wikidata count as those sources.
A Wikidata item that lists another source's ID (GBIF P846,
iNaturalist P3151, NCBI P685) under a different name is recorded
as a cross-reference, not merged.


## 7. Never

- no ranking or picking a winner at this stage
- no merging of synonyms or collapsing via WCVP
- no AI decision; AI may only propose a spelling or a split,
  which must then match a source by these same rules
- no rules tied to one region or one source (e.g. the old
  "found in Great Britain" tie-break is gone)


## 8. Proposed additions (not in the code yet)

From the 47 herbs with no plant species candidate:

a. Inverted headings: "Campion, Wild" -> also "Wild Campion".
b. Leading qualifiers: also search without "Garden", "Common",
   "Ordinary", "English", "Wild" ("Garden Bazil" -> "Bazil").
c. Two plants in one heading: "Mallows and Marshmallows" ->
   also "Mallows", "Marshmallows"; "French and Dog Mercury" ->
   "French Mercury", "Dog Mercury". Recorded as a split, so each
   part keeps its link to the herb.
d. Old spellings (Arrach -> Orache, Bazil -> Basil, Garlick ->
   Garlic, Misselto -> Mistletoe, Ladies' -> Lady's): an AI or
   a word list proposes the modern spelling; it only counts if
   a source then matches it exactly (rule 2). Recorded as
   "modern spelling of".

a-c are plain text rules. d needs the proposal step.
