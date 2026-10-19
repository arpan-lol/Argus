from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


Identifier = Annotated[str, StringConstraints(min_length=1, max_length=256)]
Predicate = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchSources(Arguments):
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["lexical", "vector", "hybrid"] = "hybrid"
    graph_hops: int = Field(default=5, ge=2, le=10)
    rrf_search: bool = True
    limit: int = Field(default=10, ge=3, le=10)
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


class ResolveEntities(Arguments):
    names: list[str] = Field(min_length=1, max_length=20)
    limit_per_name: int = Field(default=5, ge=1, le=20)

    @field_validator("names")
    @classmethod
    def valid_names(cls, values):
        if any(not name.strip() or len(name) > 300 for name in values):
            raise ValueError("Provide one to twenty nonempty graph names of at most 300 characters each")
        return list(dict.fromkeys(name.strip() for name in values))


class ReadChunks(Arguments):
    chunk_ids: list[Identifier] = Field(min_length=1, max_length=10, description="Opaque chunkId values returned by search_sources or other retrieval tools. Names and source record labels are not chunk IDs; discover the chunk IDs first.")


class InspectAssertions(Arguments):
    entity_id: str = Field(min_length=1, max_length=256)
    predicate: str | None = Field(default=None, max_length=200)
    polarity: Literal["affirmed", "negated", "uncertain", "unclassified"] | None = None
    limit: int = Field(default=20, ge=1, le=50)


class ExpandConnections(Arguments):
    entity_ids: list[Identifier] = Field(min_length=1, max_length=20)
    depth: int = Field(default=1, ge=1, le=10)
    direction: Literal["outgoing", "incoming", "both"] = "both"
    predicates: list[Predicate] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=40, ge=1, le=100)


class FindPaths(Arguments):
    source_entity_id: str = Field(min_length=1, max_length=256)
    target_entity_id: str = Field(min_length=1, max_length=256)
    max_depth: int = Field(default=5, ge=1, le=10)
    direction: Literal["outgoing", "incoming", "both"] = "both"
    predicates: list[Predicate] = Field(default_factory=list, max_length=10)
    exclude_assertion_ids: list[Identifier] = Field(default_factory=list, max_length=24, description="Previously inspected assertions to avoid when backtracking to another path.")
    limit: int = Field(default=3, ge=1, le=20)


class ReviewPath(Arguments):
    assertion_ids: list[Identifier] = Field(min_length=1, max_length=24, description="Assertion IDs returned by a graph traversal. Recheck source spans, publication status and review flags before relying on a path.")


class Invocation(Arguments):
    arguments: dict = Field(default_factory=dict)


TOOLS = {
    "search_sources": (SearchSources, "Find published source chunks with BM25, vectors or reciprocal-rank fusion. Scores measure relevance, never confidence."),
    "find_entities": (FindEntities, "Find published entities by literal canonical name or current source mention. Exact names with active assertion links rank first; links are not proof of identity. Return source-supported identities; do not silently choose between ambiguous matches."),
    "resolve_entities": (ResolveEntities, "Resolve named graph entities in one tool call. Choose the names needed for the question; return graph-checked identities grouped by requested name before traversing, never guessed opaque IDs."),
    "read_chunks": (ReadChunks, "Read retrieved chunkIds plus one following passage per seed, capped at 10 total chunks. Discover IDs with search_sources first; names/record labels are not chunk IDs. Adjacency and shared mentions are navigation, not scientific claims."),
    "inspect_assertions": (InspectAssertions, "Inspect source-grounded assertions involving an existing entity. Preserve polarity, conditions and source quotations."),
    "expand_connections": (ExpandConnections, "Follow bounded, directed semantic assertion hops from existing entity identities. Each hop retains its supporting source; composition is not a new scientific fact."),
    "find_paths": (FindPaths, "Find shortest discovered assertion paths between known entities within a bounded search. Leave predicates empty unless copied exactly from a graph result. An empty bounded search does not establish that no path exists."),
    "review_path": (ReviewPath, "Recheck each assertion in a discovered path against active published source text. Return source-backed hops and IDs that must be excluded when trying another route."),
}


def catalog():
    return [{"name": name, "description": description, "parameters": model.model_json_schema(), "agentAvailable": name in AGENT_TOOLS} for name, (model, description) in TOOLS.items()]


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
    "blast_radius": (ExpandConnections, "Article-style bounded graph reachability from known entity IDs. Return the recorded neighborhood as a traversal tree. This does not prove software impact or causal breakage."),
    "path_between": (FindPaths, "Find a source-backed path between graph identities. Use exclude_assertion_ids after review_path to backtrack and try a different route."),
    "load_bearing": (RankEntities, "Article-style PageRank on a bounded active assertion projection. Connectivity is not proof of architectural criticality or runtime use."),
    "recent_changes": (RecentSourceUpdates, "Article-style recency tool adapted to Argus: shows recent source indexing only, not Git commits or code changes."),
})


AGENT_TOOLS = tuple(name for name in TOOLS if name not in ("find_entities", "expand_connections", "find_paths", "rank_entities", "recent_source_updates"))


ARTICLE_TOOLS = [
    {"articleTool": "blast_radius", "tool": "blast_radius", "available": True, "meaning": "Follow recorded assertions with returned hops; no causal impact is inferred."},
    {"articleTool": "who_to_wake", "tool": None, "available": False, "reason": "The SDK source graph does not contain verified on-call ownership. Credited authors are not on-call contacts."},
    {"articleTool": "recent_changes", "tool": "recent_changes", "available": True, "meaning": "Recent indexing events, not Git commit history."},
    {"articleTool": "path_between", "tool": "path_between", "available": True, "meaning": "Bounded shortest discovered assertion paths with a citation for each hop."},
    {"articleTool": "load_bearing", "tool": "load_bearing", "available": True, "meaning": "Structural PageRank on a bounded, validated assertion projection."},
    {"articleTool": "recall", "tool": None, "available": False, "reason": "Long-term findings memory is disabled by user choice. Saved request checkpoints are not semantic memory."},
]
