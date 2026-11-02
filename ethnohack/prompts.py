"""The extraction prompt. Keep all prompt text here so changes are reviewable.

Design note: this step is tuned for RECALL, not precision. A claim the model
misses is gone for good — nothing downstream can recover it. A claim it
over-generates gets caught by Jev's yes/no check and dropped with a recorded
probability. So borderline readings are wanted, and the model is told to say so
rather than to decide.
"""

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

4. Prefer including a borderline claim to dropping it. If a sentence might be a
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
