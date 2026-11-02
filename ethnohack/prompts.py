"""The extraction prompt. Keep all prompt text here so changes are reviewable.

Design note: this step is tuned for RECALL, not precision. A claim the model
misses is gone for good — nothing downstream can recover it. A claim it
over-generates gets caught by Jev's yes/no check and dropped with a recorded
probability. So borderline readings are wanted, and the model is told to say so
rather than to decide.
"""

from __future__ import annotations

import hashlib

EXTRACTION_SYSTEM = """\
You extract therapeutic claims from historical herbals for a research corpus.

Your job is to LIST what the passage might be claiming. You do not judge whether
a claim is true, plausible, or medically sensible, and you do not identify which
modern plant or disease is meant. A later step does that.

Rules:

1. One claim per plant-part-preparation-condition combination. If a sentence
   says a herb boiled in wine is drunk for one complaint and the same herb made
   into an ointment is applied for another, that is TWO claims, not one.
   If one preparation is said to help four complaints, that is FOUR claims.

2. Copy names exactly as the passage writes them. Do not modernise, translate,
   correct spelling, or supply a Latin binomial. "Bloody flux" stays "bloody
   flux". If the passage calls the plant "it", use the herb heading you were
   given.

3. Every claim carries a quote: the words from the passage that support it,
   copied verbatim. Do not paraphrase the quote.

4. THE QUOTE MUST STAND ALONE. It has to include the verb that attributes the
   claim, so a reader seeing only the quote can tell what is being asserted.
   When one sentence lists several complaints, quote the whole clause for each
   one rather than the bare complaint word.

     Passage: "It kills the worms, helps the gout, cramp, and convulsions"
     WRONG, three bare words: "cramp" / "convulsions" / "the gout"
     RIGHT, the governing verb kept each time:
       "It kills the worms, helps the gout, cramp, and convulsions"

   A quote of one or two words with no verb is always wrong.

5. THE CONDITION MUST BE A COMPLAINT, written as a noun phrase.

   - An ACTION is not a complaint. "provokes urine" is the remedy's action;
     if no complaint is named, there is no claim to extract.
   - An ORGAN is not a complaint. From "helps the yellow jaundice, spleen, and
     gravel in the kidneys", the second is "disorders of the spleen", not
     "spleen".
   - A FRAGMENT is not a complaint. From "strengthens the back, and eases the
     pains thereof", the complaint is "pains of the back", not "pains thereof".
     Resolve "thereof", "the same", "it" against the sentence.
   - A VAGUE CATCH-ALL is not a complaint. Skip "other distempers", "all sudden
     diseases whatsoever", "whatsoever griefs".

6. Prefer including a borderline claim to dropping it. If a sentence might be a
   therapeutic claim, extract it.

What is NOT a claim:

- Astrological or humoral statements on their own ("it is an herb of Mercury",
  "under the sign Cancer"). Skip these unless a complaint is named alongside.
- Where the plant grows, when it flowers, what it looks like.
- Commentary about other authors, prices, the writer's opinions of doctors.
- Preparation instructions with no complaint attached.

Return only the structured result.
"""

EXTRACTION_USER = """\
Herb heading: {heading}
Passage id: {passage_id}

Passage:
\"\"\"
{text}
\"\"\"
"""


def build_user_prompt(heading: str, passage_id: str, text: str) -> str:
    return EXTRACTION_USER.format(heading=heading, passage_id=passage_id, text=text)


def _fingerprint() -> str:
    """Eight hex characters derived from the prompt text above.

    This goes in the extraction cache key, and it replaces a hand-maintained
    version number. Nobody has to remember to bump anything: edit a single word
    of the prompt and the fingerprint changes, so results produced by the old
    wording stop being served from cache and stop being reviewed as if they were
    new. Reviewing one prompt's output while believing it came from another is
    the one mistake in this pipeline that silently corrupts the measurements.
    """
    material = (EXTRACTION_SYSTEM + EXTRACTION_USER).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:8]


PROMPT_FINGERPRINT = _fingerprint()
