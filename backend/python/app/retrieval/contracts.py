from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


Identifier = Annotated[str, StringConstraints(min_length=1, max_length=256)]
Predicate = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchSources(Arguments):
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["lexical", "vector", "hybrid"] = "hybrid"
    limit: int = Field(default=10, ge=1, le=30)
    document_id: str | None = Field(default=None, max_length=256)

    @field_validator("query")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("A nonempty query is required")
        return value.strip()


class FindEntities(Arguments):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=10, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("A nonempty query is required")
        return value.strip()


class ReadChunks(Arguments):
    chunk_ids: list[Identifier] = Field(min_length=1, max_length=10)


class InspectAssertions(Arguments):
    entity_id: str = Field(min_length=1, max_length=256)
    predicate: str | None = Field(default=None, max_length=200)
    polarity: Literal["affirmed", "negated", "uncertain"] | None = None
    limit: int = Field(default=20, ge=1, le=50)


class ExpandConnections(Arguments):
    entity_ids: list[Identifier] = Field(min_length=1, max_length=5)
    depth: int = Field(default=1, ge=1, le=3)
    direction: Literal["outgoing", "incoming", "both"] = "both"
    predicates: list[Predicate] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=40, ge=1, le=100)


class FindPaths(Arguments):
    source_entity_id: str = Field(min_length=1, max_length=256)
    target_entity_id: str = Field(min_length=1, max_length=256)
    max_depth: int = Field(default=3, ge=1, le=3)
    direction: Literal["outgoing", "incoming", "both"] = "both"
    predicates: list[Predicate] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=3, ge=1, le=5)


class Invocation(Arguments):
    arguments: dict = Field(default_factory=dict)


TOOLS = {
    "search_sources": (SearchSources, "Find published source chunks with BM25, vectors or reciprocal-rank fusion. Scores measure relevance, never confidence."),
    "find_entities": (FindEntities, "Find published entities by literal canonical name or current source mention. Return source-supported identities; do not silently choose between ambiguous matches."),
    "read_chunks": (ReadChunks, "Read published chunks with exact source offsets and connected entity identities. Shared mentions are navigation, not scientific claims."),
    "inspect_assertions": (InspectAssertions, "Inspect source-grounded assertions involving an existing entity. Preserve polarity, conditions and source quotations."),
    "expand_connections": (ExpandConnections, "Follow bounded, directed semantic assertion hops from existing entity identities. Each hop retains its supporting source; composition is not a new scientific fact."),
    "find_paths": (FindPaths, "Find shortest discovered assertion paths between known entities within a bounded search. An empty bounded search does not establish that no path exists."),
}


def catalog():
    return [{"name": name, "description": description, "parameters": model.model_json_schema()} for name, (model, description) in TOOLS.items()]
