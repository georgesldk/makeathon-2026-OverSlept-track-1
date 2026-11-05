# How we extract and check medicinal claims

This page explains where every claim comes from and how we checked it,
so anyone can trace a claim back to the old book and to an official
medical term.

> A claim is what an old book says a plant does.
> It is a historical statement, not proof that the plant works,
> and not medical advice.


## In short

1. We give the book's text to an AI model (Gemini 3.8 Flash).
2. It lists every claim, with the author's exact words.
3. It suggests an official medical term (MeSH) for each claim.
4. Our code checks all of it: the quotes, the terms, and the plants.
5. Claims about the same plant and the same medical term
   are linked across books.


## Where the claims come from

**Culpeper, The Complete Herbal (1653)**
- Text: the "Government and Virtues" section of each herb (312 herbs).
- Edition: Project Gutenberg #49513, public domain.

**Dioscorides, De materia medica (1st century)**
- Text: the whole Greek chapter (409 chapters).
- Only chapters where Stage 2 found a plant (shown or possible).
- Edition: Wellmann 1906-14, First1KGreek, CC BY-SA 4.0.


## What we store for each claim

Example (made up, to show the format):

    claim_id     culpeper:wormwood:c03
    quote        "it kills the worms in the belly"     (the author's words)
    part         leaves
    preparation  decoction
    route        internal
    claim        expels intestinal worms                (modern wording)
    relation     treats
    kind         medical
    mesh         D000871 Anthelmintics (exact match)

What the fields mean:
- **quote**: copied word for word from the book.
- **translation**: for Greek only. Made by the model,
  not taken from a published translation.
- **part, preparation, route**: only if the author says so.
- **relation**: treats, relieves, prevents, promotes, causes, other.
- **kind**: medical, humoral, astrological, magical, cosmetic,
  veterinary, household, other.
  Only medical claims get a medical term.
- **mesh**: up to 3 official medical terms (see below).
- **flags**: doubts found by our checks (see check 4).


## How the claims are extracted

- Model: Gemini 3.8 Flash, in the web chat, temperature 0.
  We chose it because it scored closest to experts in our test
  (description_sources/paper_test/RESULTS.md).
- 10 herbs per prompt.
- Every prompt and every reply is saved in claims/web/<book>/.
  So the results can be rebuilt at any time,
  without asking the model again.


## The shared medical terms: MeSH

MeSH (Medical Subject Headings) is the official list of medical terms
of the U.S. National Library of Medicine. PubMed uses it to index
every article.

Why MeSH:
- It has diseases and symptoms (Jaundice, Fever, Cough).
- It also has what a remedy does (Diuretics, Cathartics, Anthelmintics).
  Old herbals often describe claims this way.
- It knows many old words: dropsy is Edema,
  melancholia is Depressive Disorder.
- Stage 3 can search PubMed with the same terms.

How it links the books:
- Each claim gets its terms on its own.
- Two books are linked when they say the same thing
  (same term) about the same plant.
- A new book only adds its own claims. Nothing is redone.

Version: MeSH 2026 (31,110 terms, 245,494 names and synonyms),
from https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/

How sure the match is:
- **exact**: the same idea ("the jaundice" is Jaundice).
- **broad**: the MeSH term is wider ("pains in the joints" as Pain).
- **close**: similar, but not the same.


## Our checks

Code runs these on every import. Nothing depends on trusting the model.

1. **The quote is really in the book.**
   If not, the claim is deleted.
   Two quoting conventions are accepted: "..." for left-out words,
   and [square brackets] for a word the model added so a short
   fragment reads as a sentence (often a verb shared by several
   clauses in Dioscorides). Bracketed words are not checked;
   everything else must be in the text.
2. **Each claim is under the right herb.**
   Claims filed under another herb are reported.
3. **The MeSH term really exists.**
   The model only suggests a name. We look it up in the official
   MeSH file and take the ID from there. Invented terms are rejected.
   Rejected terms are often old medical words (strangury, induration).
   claims/map_historical_terms.py looks them up in two open sources
   from the hackathon's dataset list, Disease Ontology and Wikidata
   (exact name or alias, with a link to MeSH). Found mappings go to
   claims/historical_terms.csv, marked "close" and with their source,
   and a person can approve or reject each row (one was rejected:
   Wikidata's "abrasion" meant dental wear, the claim meant skin).
4. **The term makes sense for the claim.**
   For example, "treats" with a body part instead of a disease.
   Such claims are kept but flagged for a person to look at.
5. **A person checks a sample.**
   20 random claims per book are written to
   claims/<book>/review_sample.csv, to be marked right or wrong.
6. **PubMed gives a second opinion.**
   We send each claim's modern wording to PubMed, which picks its own
   MeSH terms. We report how often it agrees with the model.
   (claims/check_mesh_ncbi.py)


## Results

| | Culpeper | Dioscorides |
|---|---|---|
| Entries | 312 herbs | 409 chapters |
| Claims | 5,202 | 3,815 |
| With a MeSH term | 4,559 (88%) | 3,477 (91%) |
| Claims dropped (quote not in the book) | 5 | 18 |
| Claims under the wrong herb | 0 | 0 |
| MeSH terms rejected (not in MeSH) | 36 | 54 |
| Recovered through historical_terms.csv | 7 | 4 |
| Flagged by the category check | 79 | 63 |

**Human review** (check 5, 20 random claims per book,
claims/review_results.json):

| | Claim right | MeSH term right |
|---|---|---|
| Culpeper | 20 / 20 | 18 / 20 |
| Dioscorides | 16 / 20 | 19 / 20 |

The Dioscorides misses are mostly properties or comparisons counted as
claims ("the root is more astringent", "less nourishing than millet").
Three marks were changed from n to y after a second opinion; the
note column of each review file says which and why.

**PubMed's second opinion** (check 6, claims/<book>/mesh_crosscheck.json):

| | Agree | Agree or closely related | PubMed has no opinion |
|---|---|---|---|
| Culpeper | 3,066 / 4,413 (69%) | 84% | 146 |
| Dioscorides | 2,285 / 3,312 (69%) | 83% | 164 |

"Closely related" means both share a key word (Liver Diseases and
Liver). Exact agreement understates accuracy: PubMed's automatic
mapping tends to pick the body part ("clears obstructions of the
liver" → Liver), while the model picks the condition or the drug
action (→ Liver Diseases; "induces menstruation" →
Menstruation-Inducing Agents instead of Menstruation).

**Links between the books** (claims/links.json):
- Culpeper: 4,515 claims linked to a plant, 3,301 of them to an
  identification (tier A).
- Dioscorides: 3,815 linked, 754 to an identification.
- 670 shared claims (same plant, same MeSH term, both books),
  114 of them with tier A plants in both books.


## Linking claims to plants

A claim belongs to its herb. The herb's plants come from Stage 2
(matching/<book>/eligibility.json):
- **A** plants (the identification): linked.
- **B** plants (possible, with a caveat): linked, marked "possible".
- **X** plants (rejected): never linked.

If a herb covers several plants, each claim is linked to all of them,
because the book does not always say which kind it means.

Outputs:
- claims/links.json: claims shared by the books.
- claims/graph/nodes.csv and edges.csv: ready for a graph database.


## Limits

- Some old concepts have no MeSH term at all (strangury, tenesmus,
  lochia, induration). Disease Ontology found none of the 34 rejected
  terms and Wikidata 5 (4 kept). Looking the Greek words up in LSJ was
  also tried and dropped: LSJ gives the meaning, but MeSH still lacks
  the concept. These stay unmapped until a person maps them.

- The English translation of Greek quotes is the model's.
  Our code checks the Greek, not the English.
- Matching old ideas to modern medical terms is an interpretation.
  The match level and the review sample show how reliable it is.
- A claim about one kind of a plant is linked to every plant of the herb.


## Sources

- Culpeper, N. The Complete Herbal. Project Gutenberg #49513.
  https://www.gutenberg.org/ebooks/49513
- Dioscorides. De materia medica, ed. M. Wellmann, 1906-1914.
  First1KGreek TEI, urn:cts:greekLit:tlg0656.tlg001.1st1K-grc1
- U.S. National Library of Medicine. Medical Subject Headings (MeSH), 2026.
  https://www.nlm.nih.gov/mesh/ (courtesy of the U.S. National Library of Medicine)
- NCBI E-utilities and PubMed Automatic Term Mapping.
  https://www.ncbi.nlm.nih.gov/books/NBK25499/
- Lardos, A. et al. (2024). Journal of Ethnopharmacology 322, 117622.
  doi:10.1016/j.jep.2023.117622
