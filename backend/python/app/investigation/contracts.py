from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=8)
    graph_expansion: bool = Field(default=True, description="Legacy request field retained for compatibility; graph traversal is always enabled for source questions.")
    graph_hops: int = Field(default=5, ge=2, le=10)
    hybrid_search: bool = True
    rrf_search: bool = True
    conversation_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

    @field_validator("query")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Enter a message")
        return value.strip()


class Paragraph(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=3000)
    citations: list[str] = Field(default_factory=list, max_length=10, description="Application-assigned S references only; never native record labels. Empty for conversation.")


class ComparisonRow(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    subject: str = Field(min_length=1, max_length=200)
    finding: str = Field(min_length=1, max_length=1000, description="Every requested attribute; say not documented when absent. An outcome or preventive control is a mitigation only if the source explicitly describes corrective action.")
    conditions: str = Field(max_length=1000, description="Requested grouping/category and explicit qualifiers; analytical grouping must be labeled")
    citations: list[str] = Field(min_length=1, max_length=10, description="Application-assigned S references only; never native record labels")


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    purpose: Literal["conversation", "source_answer", "insufficient_support"]
    paragraphs: list[Paragraph] = Field(min_length=1, max_length=10)
    comparison: list[ComparisonRow] = Field(default_factory=list, max_length=12, description="One cited row per requested subject for comparisons/groupings, covering the requested attributes; empty for ordinary conversation and tool lists")
    gaps: list[str] = Field(default_factory=list, max_length=8, description="Missing requested facts or actual retrieval limits only; [] when covered. No hypothetical follow-up questions.")


def report_references(report):
    return list(dict.fromkeys(reference for item in [*report.paragraphs, *report.comparison] for reference in item.citations))
