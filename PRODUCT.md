# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Application stack authorized on 2026-10-16: Next.js/React/TypeScript frontend and Express/TypeScript backend extended from Cosmic Engine. FalkorDB stores graph structure; a local source catalog and event ledger preserve evidence and traces. A standalone ingestion worker acquires and parses scientific full text. The earlier Python engine remains a reference spike.

## Users

The user confirmed that the primary workspace should serve the person reviewing evidence, with a full technical inspector alongside it. Proposed application users are engineers reviewing protocol implementations and materials researchers comparing published evidence. The application personas are proposals, not interview-validated customers.

## Product Purpose

Build a generic engine in a strong direction that demonstrably removes evidence-review work. Produce inspectable, persistent evidence dossiers and review matrices that can support more than one domain through explicit adapters.

## Operating Context

FalkorDB hackathon, 15–18 October 2026. The user brings existing experience building Cosmic Engine and wants ingestion processing, DB inspection, scores, timing analytics and graph operations visible on the UI. The user has no chemistry/materials reviewer available during this event.

## Product Principles

- Lead with the evidence-review task and provide full technical inspection.
- Preserve exact source provenance, context, identity, versions and score meanings.
- Clearly separate implemented capabilities, observed results and planned features.
- Share engine contracts across domains while keeping domain normalization and applicability rules explicit.
- Demonstrate a useful work product and measure quality against a strong retrieval baseline.

## Proposals and Open Decisions

Use Case A: materials literature evidence review, beginning with adsorption/remediation evidence and a broader catalysis discovery collection. Use Case B: standards implementation review. These are two adapters for one engine, not fallback plans. Scientific interpretation remains unvalidated without a researcher reviewer.

Working name: Cosmic Evidence Workspace. Preserve Cosmic Engine's dashboard design language and controller/service/route organization. Open directly into a visual evidence-review dashboard with a full inspector, colored chunks, article section navigation, and citation-linked graph neighborhoods. Authentication and long-term memory are explicitly deferred. Production deployment remains open. Future architectural decisions require asking Arpan; the user granted creative freedom for this first implementation slice.

## Evidence and Assets

`research/corpus-inventory.json` records the initial official discovery audit. Progress, goals, technical decisions, and historical planning live in ignored root `docs/`. Scientific acquisition artifacts live in ignored `data/`. `fixtures/demo.json` belongs to the earlier Python spike and is explicitly synthetic; it must not appear as real scientific data in the new dashboard. No customer testimonials, measured time savings, or corpus-scale performance have been established.
