"""LLM triage result model for hedge filler words."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class FillerTriageResult(BaseModel):
    """LLM verdict for one hedge filler."""

    filler_index: int = Field(ge=0)
    word: str
    category: str
    safe_to_remove: bool = False
    reason: str = ""
    llm_model: str = ""
    triaged_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
