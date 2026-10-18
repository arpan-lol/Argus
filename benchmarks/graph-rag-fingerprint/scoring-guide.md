Scoring guide - RAG Architecture Fingerprint Benchmark

Every question scores 0-4:

| Score | Anchor |
|---|---|
| 0 | Wrong final assertion, or correct only by luck with no retrievable evidence |
| 1 | Partial recall (right endpoints, wrong middle), or refuses where an answer exists |
| 2 | Right answer but wrong order/coverage, or invented edge directions |
| 3 | Right answer and mostly grounded; one citation or one hop off |
| 4 | Complete, ordered, every claim traceable to a cited record; refuses exactly where refusal is correct |

Hard rules:
- Any claim asserted as true but present nowhere in the corpus caps the question at 1 (unsupported-true penalty is deliberately heavier than a clean refusal).
- The self-report questions (Q29/Q30) can never advance the verdict by themselves; their score reflects honest reporting about internal state, not capability claims.
- Ruthless with endpoints: wrong dB/service substitution beats a missing hop? No - both are scored by anchor; only exact, guided substitution of a documented alternative path keeps score 4.

Category weighting: each of the 15 categories contributes its mean score; overall verdict thresholds appear in architecture-verification.md.

Worked example:
- Q07 answered flat with the full neighborhood list, both names, and citations to the profile records: score 4.
- Q07 answered with Windward/vault-style names or the claim "all customers": score 0-1.
- Q19 answered Yes by pattern-matching other incidents: score 0; answered No citing the postmortem record: score 4.

Controls (run identically for any compared system):
- One fresh conversation per question; no history carry-over.
- The corpus must be ingested unchanged; the same five artifacts document what was ingested.
- Preserve the retrieval transcripts; the answer key and expected citations decide scoring, not vibes.
- Provider budget: retrieval tools must run in lexical mode during scoring; hybrid/vector modes call the embedding provider and are out of scope for this benchmark. Any provider call (embedding or LLM) made during a scoring conversation is recorded in the run log and reported as a cost leak, not consumed as evidence.
