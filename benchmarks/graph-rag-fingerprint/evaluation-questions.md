# Evaluation questions

Ask each question in a fresh conversation against the ingested corpus. Category order below matches the answer key.

## 1. Provenance and single-hop baseline (PROV)
- **Q01**: Which team owns Fleet Dispatch, and what does that team's page say it operates?
- **Q02**: Which vendor supplies the Payments Gateway API, and which service hosts that API?

## 2. Multi-hop chain tracing (CHAIN)
- **Q03**: Trace how one confirmed checkout session's charge becomes visible on Partner Portal dashboards. Name every system in order and the edge type between them.
- **Q04**: How does Windward Grocers' van telemetry reach the Partner Portal dashboards? List the systems in order.

## 3. Reverse traversal (REVERSE)
- **Q05**: A paging rule hits Orders Primary, Ledger Primary and Ledger Mirror in one night. Which people are on call for each of them?
- **Q06**: Which customers require the Ledger Immutability Control?

## 4. Blast radius (BLAST)
- **Q07**: From Checkout Storefront, list its immediate graph neighborhood (one hop in either direction) and name the customers that directly consume it.
- **Q08**: If Swarm API goes down, which services degrade? Expect exactly three.

## 5. Multi-constraint lookup (CONSTRAINT)
- **Q09**: Which customers require the Ledger Immutability Control and also hold Payout Service settlement?
- **Q10**: Which customer requires Restore Drill Control and also runs van telemetry through Fleet Dispatch?

## 6. Shared-neighbor bridge (BRIDGE)
- **Q11**: Which single shared dependency do Payments Service and Nimbus Routing converge on, and which third service also connects to it?
- **Q12**: Which single API carries Analytics ETL output to the Partner Portal, and which team runs the producer side?

## 7. Shortest path (SHORTPATH)
- **Q13**: Find the shortest documented route of hops that connects on-call engineer Taro Kurosawa to on-call engineer Celia Hague. List every edge.
- **Q14**: Give the shortest supported route from Vaulttree Estate to Ledger Primary.

## 8. Global synthesis (SYNTH)
- **Q15**: Which team domains does the Analytics Lake span, and is the Order Intake cluster inside its nightly span?
- **Q16**: Which releases shipped into Orders Intake, and who approved each of them?

## 9. Temporal reasoning and supersession (TEMPORAL)
- **Q17**: What did the finance knowledge base say on April 18 about Ledger Mirror sourcing, what correction replaced it, and on what date?
- **Q18**: As of now, is 'Orders Primary replicates to Ledger Mirror' an active fact?

## 10. Negative evidence and false premises (NEGATIVE)
- **Q19**: Did Payout Release v2 cause Payout Delay Thursday? Give the record that proves your stance.
- **Q20**: Does the Analytics Lake carry Orders Primary data?

## 11. Provenance citation (SRC)
- **Q21**: Which record documents the external audit finding on Ledger Primary, on what date, and by which auditor?
- **Q22**: Who is the auditor of record for Orders Primary's storage audit?

## 12. Explicit vs inferred (EXPLICIT)
- **Q23**: Is there an explicit causal edge from Legacy Order Feeder to any incident?
- **Q24**: Does any record state that Pinefork Supply supplied checkout hardware?

## 13. Missing-link refusal (REFUSAL)
- **Q25**: Does Solvex Gateway supply the Route ETL Store? If not, name its actual data sources.
- **Q26**: Do partner-facing notifications feed the Route ETL Store's optimizer inputs?

## 14. Entity-resolution traps (TRAP)
- **Q27**: The order feeder that still writes hourly in the intake cluster: name it, its owning team, and the one API it still shares.
- **Q28**: Which store ingests nightly from ledger-side mirrors, and which cluster runs it?

## 15. Architecture self-report (SELFCHECK)
- **Q29**: When you plan a multi-hop answer, describe what you can actually observe about your own retrieval: do you know whether an explicit graph exists, or are you inferring from retrieved prose?
- **Q30**: If your answer to the Ledger Mirror rumour question cites a superseding record, state that record's ID and date; if you cannot, say you cannot.

