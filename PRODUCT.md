# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Current stack: Next.js/React/TypeScript frontend, Python/FastAPI backend, LangGraph ingestion with Postgres checkpoints, Postgres with pg_search, and FalkorDB semantic graphs and vectors. A bounded Postgres queue processes uploaded and acquired files through shared stages. The earlier Express implementation and independent Python spike are inactive migration references.

## Users

The primary workspace serves a person reviewing sources, with central chat and the Source Explorer for graphs, files, chunks, and processing details. Proposed application users are engineers reviewing protocol implementations and materials researchers comparing published sources. The application personas are proposals, not interview-validated customers.

## Product Purpose

Build a generic engine in a strong direction that demonstrably removes source-review work. Produce inspectable, persistent source dossiers and review matrices that can support more than one domain through explicit adapters.

## Operating Context

FalkorDB hackathon, 15–18 October 2026. The user brings experience building retrieval engines and wants ingestion processing, DB inspection, scores, timing analytics and graph operations visible on the UI. The user has no chemistry/materials reviewer available during this event.

## Product Principles

- Lead with the source-review task and provide full technical inspection.
- Preserve exact source provenance, context, identity, versions and score meanings.
- Clearly separate implemented capabilities, observed results and planned features.
- Share engine contracts across domains while keeping domain normalization and applicability rules explicit.
- Demonstrate a useful work product and measure quality against a strong retrieval baseline.

## Proposals and Open Decisions

Use Case A: materials literature source review, beginning with adsorption/remediation source and a broader catalysis discovery collection. Use Case B: standards implementation review. These are two adapters for one engine, not fallback plans. Scientific interpretation remains unvalidated without a researcher reviewer.

Project name: Argus (two syllables), named for a character from Greek mythology. Preserve Argus's dashboard design language and controller/service/route organization. The requested entry page is a project grid, opening each project's dashboard with central chat, files above a graph, colored chunks, source navigation, and citation-linked neighborhoods. Authentication and long-term memory are explicitly deferred. Production deployment remains open. Future architectural decisions require asking Arpan.

## Source and Assets

`research/corpus-inventory.json` records the initial official discovery audit. Progress, goals, technical decisions, and historical planning live in ignored root `docs/`. Scientific acquisition artifacts live in ignored `data/`. `fixtures/demo.json` belongs to the earlier Python spike and is explicitly synthetic; it must not appear as real scientific data in the new dashboard. No customer testimonials, measured time savings, or corpus-scale performance have been established.
