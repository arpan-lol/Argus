# Answer key (computed from the model; never ingested)

## 1. Provenance and single-hop baseline
### Q01 (Provenance and single-hop baseline)
Q: Which team owns Fleet Dispatch, and what does that team's page say it operates?
Hops: 1
- Dispatch Team -[OWNS]-> Fleet Dispatch
Must cite: svc-008
Tempting-wrong: Care Platform Team (runs portals, not fleet); Dispatch API is a surface, not the owner.
Hint: The answer is one OWNS edge.

### Q02 (Provenance and single-hop baseline)
Q: Which vendor supplies the Payments Gateway API, and which service hosts that API?
Hops: 2
- Solvex Gateway -[SUPPLIES]-> Payments Gateway API
- Payments Service -[EXPOSES]-> Payments Gateway API
Must cite: vend-002, api-004, svc-005
Tempting-wrong: DeltaWave (supplies the Notification Queue, nothing else); Pinefork (sortation cameras).

## 2. Multi-hop chain tracing
### Q03 (Multi-hop chain tracing)
Q: Trace how one confirmed checkout session's charge becomes visible on Partner Portal dashboards. Name every system in order and the edge type between them.
Hops: 6
- Orders Intake -[EXPOSES]-> Checkout API
- (reverse) Payments Service -[CALLS]-> Checkout API
- Payments Service -[WRITES_TO]-> Ledger Primary
- (reverse) Analytics ETL -[READS_FROM]-> Ledger Primary
- Analytics ETL -[EXPOSES]-> Reporting API
- (reverse) Partner Portal -[CALLS]-> Reporting API
Must cite: api-001, api-010, svc-002, svc-005, svc-012, svc-013
- acceptable alternative: the telemetry route via Fleet Dispatch is also written down, but it is not the charge path
Tempting-wrong: Jumping from Ledger Primary straight to Partner Portal, or claiming Mirror feeds the portal (finance dashboards read the Mirror, not the portal).
Hint: 6 hops
Hint: expect the exact order Orders Intake, Checkout API, Payments, Ledger Primary, Analytics ETL, Reporting API, Partner Portal

### Q04 (Multi-hop chain tracing)
Q: How does Windward Grocers' van telemetry reach the Partner Portal dashboards? List the systems in order.
Hops: 5
- Windward Grocers -[USES]-> Fleet Dispatch
- Fleet Dispatch -[WRITES_TO]-> Fleet Telemetry Store
- (reverse) Analytics ETL -[READS_FROM]-> Fleet Telemetry Store
- Analytics ETL -[EXPOSES]-> Reporting API
- (reverse) Partner Portal -[CALLS]-> Reporting API
Must cite: api-010, cust-002, svc-008, svc-012, svc-013
Tempting-wrong: Routing tree via Nimbus (routing has no telemetry edges).

## 3. Reverse traversal
### Q05 (Reverse traversal)
Q: A paging rule hits Orders Primary, Ledger Primary and Ledger Mirror in one night. Which people are on call for each of them?
Hops: 2
- Celia Hague is on call for Ledger Primary and Orders Primary
- Taro Kurosawa is on call for Ledger Mirror
Must cite: rota-001, rota-003, rota-011
Tempting-wrong: Jesse Moon (payments) or claiming the commander pages himself; Lin Mei sits inside intake rota only.
Hint: Reverse-lookup on ONCALL_FOR.
Hint: Ledger Mirror's named on call is Taro Kurosawa; Orders Primary and Ledger Primary are Celia Hague.

### Q06 (Reverse traversal)
Q: Which customers require the Ledger Immutability Control?
Hops: 1
- Tramline Couriers requires the Ledger Immutability Control
- Vaulttree Estate requires the Ledger Immutability Control
Must cite: cust-005, cust-009
Tempting-wrong: Greenfield Grocers (requires Isolation Control, not Immutability).

## 4. Blast radius
### Q07 (Blast radius)
Q: From Checkout Storefront, list its immediate graph neighborhood (one hop in either direction) and name the customers that directly consume it.
Hops: 1
- Neighborhood (one hop): Acme Retail; August Gateway 403 Surge; Checkout API; Checkout Release v2; Checkout Release v3; Granite Peaks Consulting; Launch Flag Gate; Lin Mei; Order Intake Team; Orders Primary; Solstice Media; Vendor Vulnerability Scan.
- Direct consumers: Acme Retail, Solstice Media (each one record: a customer Uses the storefront).
Must cite: svc-001, cust-001, cust-004
Tempting-wrong: Naming Windward (uses Fleet Dispatch, not checkout) or Vaulttree (ledger controls).
Hint: 12 neighbors
Hint: the two Uses customers are Solstice Media and Acme Retail

### Q08 (Blast radius)
Q: If Swarm API goes down, which services degrade? Expect exactly three.
Hops: 1
- Affected services: Fleet Dispatch, Nimbus Routing, Payments Service.
Must cite: svc-005
Tempting-wrong: Warehouse Management (uses Warehouse API, harmless to Swarm); the Payment Gateway API exposes blame onto Solvex, not the fallout list.

## 5. Multi-constraint lookup
### Q09 (Multi-constraint lookup)
Q: Which customers require the Ledger Immutability Control and also hold Payout Service settlement?
Hops: 2
- Tramline Couriers (requires Immutability; holds Payout Service)
- Vaulttree Estate (requires Immutability; holds Payout Service)
Must cite: cust-005
Tempting-wrong: Lakeside Pharmacy (holds Payout Service but requires nothing of that control family).

### Q10 (Multi-constraint lookup)
Q: Which customer requires Restore Drill Control and also runs van telemetry through Fleet Dispatch?
Hops: 2
- Windward Grocers: requires Restore Drill Control; uses Fleet Dispatch; its van telemetry reaches the lake.
Must cite: cust-002
Tempting-wrong: Tramline Couriers (uses Fleet Dispatch but requires Immutability, not the drill).

## 6. Shared-neighbor bridge
### Q11 (Shared-neighbor bridge)
Q: Which single shared dependency do Payments Service and Nimbus Routing converge on, and which third service also connects to it?
Hops: 2
- Shared dependency: Swarm API.
- Third connector: Fleet Dispatch (it exposes Swarm API).
Must cite: svc-005
Tempting-wrong: Report API/ledger bridges; Orchard Routes is a vendor feed for the map routing path, not the shared dependency.

### Q12 (Shared-neighbor bridge)
Q: Which single API carries Analytics ETL output to the Partner Portal, and which team runs the producer side?
Hops: 2
- Bridge API: Reporting API.
- Producer owner: Data Platform Team.
Must cite: api-010, svc-012, svc-013
Tempting-wrong: Checkout API (wrong cluster); Payout Queue.

## 7. Shortest path
### Q13 (Shortest path)
Q: Find the shortest documented route of hops that connects on-call engineer Taro Kurosawa to on-call engineer Celia Hague. List every edge.
Hops: 3
- Taro Kurosawa -[ONCALL_FOR]-> Ledger Mirror
- (reverse) Ledger Primary -[REPLICATES_TO]-> Ledger Mirror
- (reverse) Celia Hague -[ONCALL_FOR]-> Ledger Primary
Must cite: db-004, person-006, rota-001, rota-011
Tempting-wrong: Hoping through Team ownership or MEMBER_OF chains (long, true but not shortest): Taro -> payments rota -> checkout …; the right shape is Store rota hops through the two ledger stores.
Hint: 3 hops
Hint: Ledger Mirror copies from Ledger Primary, and each store's named on-call is respectively Taro and Celia.

### Q14 (Shortest path)
Q: Give the shortest supported route from Vaulttree Estate to Ledger Primary.
Hops: 2
- Vaulttree Estate -[REQUIRES]-> Ledger Immutability Control
- Ledger Immutability Control -[PROTECTS]-> Ledger Primary
Must cite: ctl-001, cust-005
Tempting-wrong: Via Payments usage (customers never USE the ledger directly; only the control chain is a two-hop route).

## 8. Global synthesis
### Q15 (Global synthesis)
Q: Which team domains does the Analytics Lake span, and is the Order Intake cluster inside its nightly span?
Hops: 3
- Sections span Care Platform Team, Dispatch Team, Payments Team.
- Intake is NOT included: Analytics ETL never reads Orders Primary; intake history remains in intake storage.
Must cite: summary-memo-sept, svc-012, svc-005, svc-007, svc-008, svc-010
Tempting-wrong: Claiming intake is in the lake (the feeder job's legacy purge is not lake ingestion).
Hint: payments/warehouse/support

### Q16 (Global synthesis)
Q: Which releases shipped into Orders Intake, and who approved each of them?
Hops: 2
- Orders Release v10 approved by Lin Mei
- Orders Release v9 approved by Lin Mei
Must cite: rel-003, rel-004
Tempting-wrong: Checkout Releases v2/v3 (ship into Checkout Storefront, a different target).

## 9. Temporal reasoning and supersession
### Q17 (Temporal reasoning and supersession)
Q: What did the finance knowledge base say on April 18 about Ledger Mirror sourcing, what correction replaced it, and on what date?
Hops: 2
- On 2026-04-18 the KB note 'Finance KB: draft copy about the ledger replica' claimed Ledger Mirror reads Orders Primary as a secondary source.
- That claim was superseded on 2026-04-20 (record corr-002): Orders Primary does not replicate into Ledger Mirror; the mirror receives Ledger Primary only.
Must cite: kb-mirror-rumor, corr-002
Tempting-wrong: Reporting the April claim as current truth.
Hint: superseded April 20

### Q18 (Temporal reasoning and supersession)
Q: As of now, is 'Orders Primary replicates to Ledger Mirror' an active fact?
Hops: 1
- No. It is explicitly negated by corr-002 (2026-04-20).
Must cite: corr-002
Tempting-wrong: The old KB wording still contains the sentence; staleness matters.

## 10. Negative evidence and false premises
### Q19 (Negative evidence and false premises)
Q: Did Payout Release v2 cause Payout Delay Thursday? Give the record that proves your stance.
Hops: 1
- No. Both the postmortem and the corr-004 notice explicitly negate it; the delay was queue suction, not the charge-side split.
Must cite: postmortem-002, corr-004
Tempting-wrong: Affirming release-causation pattern generalization (several incidents in the corpus DO have affirmed release causes).

### Q20 (Negative evidence and false premises)
Q: Does the Analytics Lake carry Orders Primary data?
Hops: 2
- No. Analytics ETL reads Ledger Primary, Warehouse DB, Fleet Telemetry Store and Notification Queue only; Orders Primary is absent from its read list.
Must cite: summary-memo-sept, svc-012
Tempting-wrong: Assuming the lake spans everything with 'orders' in the name.

## 11. Provenance citation
### Q21 (Provenance citation)
Q: Which record documents the external audit finding on Ledger Primary, on what date, and by which auditor?
Hops: 1
- Record audit-001 (2026-08-22): Annual retention finding: Ledger Primary archive policy fulfils the Harbour Audit retention scope; the Launch Flag Gate recorded as in place. Auditor: Harbour Audit.
Must cite: audit-001
Tempting-wrong: Harbor Audit lives in two notes; cite the one whose subject is Ledger Primary, not the payments vendor scan.

### Q22 (Provenance citation)
Q: Who is the auditor of record for Orders Primary's storage audit?
Hops: 1
- Harbour Audit (record audit-004).
Must cite: audit-004

## 12. Explicit vs inferred
### Q23 (Explicit vs inferred)
Q: Is there an explicit causal edge from Legacy Order Feeder to any incident?
Hops: 1
- No. Not one CAUSED_BY/AFFECTED edge leaves the feeder. It shares one historical API with intake, and downstream connectivity across that surface reaches payments, but connectivity is not causation.
Must cite: summary-memo-negatives
Tempting-wrong: Tracing feeder -> Checkout API -> Payments -> Blue Monday and calling that a causal chain; the memo explicitly forbids reading it that way.

### Q24 (Explicit vs inferred)
Q: Does any record state that Pinefork Supply supplied checkout hardware?
Hops: 1
- No. Pinefork's only supply record is Warehouse Management. No hardware claims touch checkout.
Must cite: vend-006
Tempting-wrong: Vision Events Store surge wording written near checkout.

## 13. Missing-link refusal
### Q25 (Missing-link refusal)
Q: Does Solvex Gateway supply the Route ETL Store? If not, name its actual data sources.
Hops: 2
- No. Solvex Gateway's only supply record is the Payments Gateway API.
- The Route ETL Store's real sources: Nimbus Maps (primary feed) and Orchard Routes (fallback feed); Nimbus Routing and Fleet Dispatch read from it.
Must cite: vend-002, vend-008, vend-003
Tempting-wrong: Vendor-washing: both are vendors, so assuming Solvex touches routing data.

### Q26 (Missing-link refusal)
Q: Do partner-facing notifications feed the Route ETL Store's optimizer inputs?
Hops: 1
- Refuse to claim a feed. No supply or data-flow edge connects Notification Service or its queue to Route ETL Store; the only cross-cluster links are customer usage chains, which are not feeds.
Must cite: svc-010, svc-009
Tempting-wrong: Walking the 5-hop usage chain (queue -> notification -> customer -> orders/fleet) and presenting it as a data feed.

## 14. Entity-resolution traps
### Q27 (Entity-resolution traps)
Q: The order feeder that still writes hourly in the intake cluster: name it, its owning team, and the one API it still shares.
Hops: 2
- Legacy Order Feeder; owned by Order Intake Team; shares Checkout API (still exposed by both.).
Must cite: svc-004
Tempting-wrong: Confusing it with Orders Intake itself, or with Analytics ETL.

### Q28 (Entity-resolution traps)
Q: Which store ingests nightly from ledger-side mirrors, and which cluster runs it?
Hops: 1
- Fraud Store runs in the payments cluster; Ledger Mirror itself is the read replica for finance dashboards, the fraud store is the nightly feature ingest.
Must cite: audit-009
Tempting-wrong: Answering Ledger Mirror; the trap query names a sink that eats from it.

## 15. Architecture self-report
### Q29 (Architecture self-report)
Q: When you plan a multi-hop answer, describe what you can actually observe about your own retrieval: do you know whether an explicit graph exists, or are you inferring from retrieved prose?
- Expected behavior: the system either reports concrete internal state (tool/tool-trace type names such as a typed-edge lookup it actually issued) or says 'cannot verify from the chat alone'. Uncorroborated self-descriptions must not be treated as measurement.
Hint: This question can never earn verdict-level proof by itself.

### Q30 (Architecture self-report)
Q: If your answer to the Ledger Mirror rumour question cites a superseding record, state that record's ID and date; if you cannot, say you cannot.
- Correct behavior: reproduce the citation only if it is grounded in retrieved material; a bare 'I checked my graph' claim with no record ID/date is not a citation.

