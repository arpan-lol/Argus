# Flow-derived codebase ingestion

This component is licensed under AGPL-3.0-only. The full license is in
`backend/python/licenses/flow-AGPL-3.0.txt`.

The typed software graph ontology in `contracts.py` is adapted from
`flow/graph-gateway/src/schema.ts` in samyakkkk/flow, revision
`5d7e942fe32438c09ac3dd137961f4b122e7115f`:
https://github.com/samyakkkk/flow

The repository-reading graph-builder approach, find-before-create writes,
source provenance and revision-based incremental ingestion follow Flow's design.
Argus implements a separate Python/LangGraph runner, Azure LLM2 provider,
Postgres token ledger/checkpoints, typed staging tools and integration with its
existing source publication lifecycle. It does not run Flow's OpenCode service.

Flow's root workspace shell is MIT licensed, but the original `flow/` subtree
used here is AGPL-3.0-only, as its NOTICE.md and subtree LICENSE specify. The root
MIT license does not relicense the graph builder or ontology.

Corresponding source for this adaptation is provided in the Argus repository:
https://github.com/arpan-lol/falkor/tree/ingestion-main/backend/python
