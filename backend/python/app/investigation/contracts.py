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
    graph_expansion: bool = True

    @field_validator("query")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Enter a message")
        return value.strip()


class Paragraph(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=3000)
    citations: list[str] = Field(default_factory=list, max_length=10)


class ComparisonRow(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    subject: str = Field(min_length=1, max_length=200)
    finding: str = Field(min_length=1, max_length=1000)
    conditions: str = Field(max_length=1000)
    citations: list[str] = Field(min_length=1, max_length=10)


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    purpose: Literal["conversation", "source_answer", "insufficient_support"]
    paragraphs: list[Paragraph] = Field(min_length=1, max_length=10)
    comparison: list[ComparisonRow] = Field(default_factory=list, max_length=12)
    gaps: list[str] = Field(default_factory=list, max_length=8)


def report_references(report):
    return list(dict.fromkeys(reference for item in [*report.paragraphs, *report.comparison] for reference in item.citations))
