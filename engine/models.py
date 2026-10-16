from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    uri: str
    revision: str
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Evidence:
    id: str
    document_id: str
    start: int
    end: int
    quote: str


@dataclass(frozen=True)
class Claim:
    id: str
    subject: str
    predicate: str
    object: str
    evidence_ids: list[str]
    status: str = "unreviewed"
    qualifiers: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Candidate:
    evidence_id: str
    score: float | None
    score_kind: str
    rank: int
    path: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Decision:
    id: str
    question: str
    claim_ids: list[str]
    evidence_ids: list[str]
    status: str
    reviewer: str | None = None
    rationale: str | None = None


class Ingestor(Protocol):
    def load(self, path: str) -> dict: ...


class Retriever(Protocol):
    def search(self, query: str, limit: int) -> list[Candidate]: ...


class GraphProvider(Protocol):
    def ingest(self, documents: list[Document], evidence: list[Evidence], claims: list[Claim]) -> None: ...
    def expand(self, evidence_ids: list[str], limit: int) -> dict: ...
