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
    chunk_ids: list[Identifier] = Field(min_length=1, max_length=10, description="Opaque chunkId values returned by search_sources or other retrieval tools. Names and source record labels are not chunk IDs; discover the chunk IDs first.")


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
    "read_chunks": (ReadChunks, "Read retrieved chunkIds plus one following passage per seed, capped at 10 total chunks. Discover IDs with search_sources first; names/record labels are not chunk IDs. Adjacency and shared mentions are navigation, not scientific claims."),
    "inspect_assertions": (InspectAssertions, "Inspect source-grounded assertions involving an existing entity. Preserve polarity, conditions and source quotations."),
    "expand_connections": (ExpandConnections, "Follow bounded, directed semantic assertion hops from existing entity identities. Each hop retains its supporting source; composition is not a new scientific fact."),
    "find_paths": (FindPaths, "Find shortest discovered assertion paths between known entities within a bounded search. An empty bounded search does not establish that no path exists."),
}


def catalog():
    return [{"name": name, "description": description, "parameters": model.model_json_schema()} for name, (model, description) in TOOLS.items()]


class SourceAuthors(Arguments):
    document_id: Identifier
    limit: int = Field(default=10, ge=1, le=20)


class RecentSourceUpdates(Arguments):
    hours: int = Field(default=24, ge=1, le=168)
    document_id: Identifier | None = None
    limit: int = Field(default=10, ge=1, le=20)


class RankEntities(Arguments):
    entity_id: Identifier | None = None
    depth: int = Field(default=2, ge=1, le=3)
    limit: int = Field(default=10, ge=1, le=20)


TOOLS.update({
    "source_authors": (SourceAuthors, "Read authors recorded in the parsed metadata of one published source. These are credited authors, not on-call staff, contact details or expert recommendations. Cite returned metadata references."),
    "recent_source_updates": (RecentSourceUpdates, "List active source publications indexed within the last 1–168 hours. indexedAt is an Argus indexing timestamp, never the research paper's publication date or proof of a new scientific result."),
    "rank_entities": (RankEntities, "Compute PageRank over a bounded sample of current, affirmed source assertions, optionally around an existing entity. Structural connectivity is not scientific importance, truth, confidence or causality. Results retain source support and sampling limits."),
})


ARTICLE_TOOLS = [
    {"articleTool": "blast_radius", "tool": "expand_connections", "available": True, "meaning": "Follow recorded research assertions with returned hops; no causal impact is inferred."},
    {"articleTool": "who_to_wake", "tool": "source_authors", "available": True, "meaning": "Credited source authors only; no on-call or contact information is inferred."},
    {"articleTool": "recent_changes", "tool": "recent_source_updates", "available": True, "meaning": "Recent indexing events, separately labeled from article publication dates."},
    {"articleTool": "path_between", "tool": "find_paths", "available": True, "meaning": "Bounded shortest discovered assertion paths with a citation for each hop."},
    {"articleTool": "load_bearing", "tool": "rank_entities", "available": True, "meaning": "Structural PageRank on a bounded, validated assertion projection."},
    {"articleTool": "recall", "tool": None, "available": False, "reason": "Long-term findings memory is disabled by user choice. Saved request checkpoints are not semantic memory."},
]
