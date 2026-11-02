"""What a candidate claim looks like.

Everything the LLM returns is a *candidate*. Nothing here is decided: the plant
name and the condition stay exactly as the text wrote them, and identification
happens later, with Jev, against a candidate list. Normalising at extraction
time would destroy the evidence we need to check the identification against.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CandidateClaim(BaseModel):
    """One therapeutic claim a passage might be making."""

    plant_name_verbatim: str = Field(
        description="The plant as the passage names it, copied exactly. Never a Latin binomial unless the text gives one."
    )
    plant_part: str | None = Field(
        default=None,
        description="Part used: leaves, root, seed, flowers, juice, whole herb. Null if the passage does not say.",
    )
    preparation: str | None = Field(
        default=None,
        description="How it is made: decoction, distilled water, ointment, conserve, boiled in wine. Null if unstated.",
    )
    route: str | None = Field(
        default=None,
        description="How it is used: drunk, applied outwardly, chewed, bathed, snuffed. Null if unstated.",
    )
    condition_verbatim: str = Field(
        description="The complaint as the passage names it, copied exactly. Keep historical wording such as 'bloody flux' or 'the stone'."
    )
    quote: str = Field(
        description="The span of the passage that supports this claim, copied word for word."
    )


class ExtractionResult(BaseModel):
    """Everything one passage yielded."""

    claims: list[CandidateClaim] = Field(default_factory=list)


class StoredExtraction(BaseModel):
    """An extraction plus the provenance we have to keep."""

    passage_id: str
    corpus_id: str
    heading: str
    model: str
    extracted_at: str
    claims: list[CandidateClaim]
