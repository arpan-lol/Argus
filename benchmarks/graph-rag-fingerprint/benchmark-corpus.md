# Benchmark corpus: Nimbusfield Logistics (fictional enterprise)

This document is the complete ingestible corpus for the RAG Architecture Fingerprint Benchmark.
Every fact below is stated exactly once as a literal arrow line; prose adds human context only.

Every fact line appears as `SUBJECT -> PREDICATE -> OBJECT`. All edges are directed exactly as written.
Negation convention: a predicate prefixed with `!` states that the positive edge does **not** hold, dated and explained in the correction record that owns the line.

## team-001 - profile - 2026-01-14
Team page: Order Intake Team

Team page for Order Intake Team (team:intake).
Members: Lin Mei, Nila Venkat.
Charter note: owns the order-acceptance path only; does not own charges.
`Lin Mei -> MEMBER_OF -> Order Intake Team`
`Nila Venkat -> MEMBER_OF -> Order Intake Team`

## team-002 - profile - 2026-01-14
Team page: Payments Team

Team page for Payments Team (team:payments).
Members: Mara Okafor, Taro Kurosawa, Samir Hadzhi.
Charter note: owns charging, ledger and payouts; does not own intake sessions.
`Mara Okafor -> MEMBER_OF -> Payments Team`
`Taro Kurosawa -> MEMBER_OF -> Payments Team`
`Samir Hadzhi -> MEMBER_OF -> Payments Team`

## team-003 - profile - 2026-01-14
Team page: Dispatch Team

Team page for Dispatch Team (team:dispatch).
Members: Ravi Mohan, Jesse Moon.
Charter note: hub and van routing; does not own customer messages.
`Ravi Mohan -> MEMBER_OF -> Dispatch Team`
`Jesse Moon -> MEMBER_OF -> Dispatch Team`

## team-004 - profile - 2026-01-14
Team page: Care Platform Team

Team page for Care Platform Team (team:care).
Members: Sofia Beltan, Omar Diaz.
Charter note: notification and helpdesk; no order-state ownership.
`Sofia Beltan -> MEMBER_OF -> Care Platform Team`
`Omar Diaz -> MEMBER_OF -> Care Platform Team`

## team-005 - profile - 2026-01-14
Team page: Data Platform Team

Team page for Data Platform Team (team:data).
Members: Bogdan Traistman, Yuki Tanabe.
Charter note: nightly lake copies and the fan-out reporting surface.
`Bogdan Traistman -> MEMBER_OF -> Data Platform Team`
`Yuki Tanabe -> MEMBER_OF -> Data Platform Team`

## team-006 - profile - 2026-01-14
Team page: Core Storage Team

Team page for Core Storage Team (team:coredb).
Members: Celia Hague.
Charter note: database primaries and replicas only.
`Celia Hague -> MEMBER_OF -> Core Storage Team`

## person-001 - profile - 2026-01-13
Person card: Mara Okafor

Directory card for Mara Okafor (person:mara-okafor).
Member of Payments Team.
Standing on-call rota: Payments Service.
Standing note: personal sign-off is the approval gate for ledger schema changes.
`Mara Okafor -> MEMBER_OF -> Payments Team`
`Mara Okafor -> ONCALL_FOR -> Payments Service`

## person-002 - profile - 2026-01-13
Person card: Ravi Mohan

Directory card for Ravi Mohan (person:ravi-mohan).
Member of Dispatch Team.
Standing on-call rota: Warehouse Management, Fleet Dispatch.
Standing note: leads hub incident command; pages the warehouse rota.
`Ravi Mohan -> MEMBER_OF -> Dispatch Team`
`Ravi Mohan -> ONCALL_FOR -> Warehouse Management`
`Ravi Mohan -> ONCALL_FOR -> Fleet Dispatch`

## person-003 - profile - 2026-01-13
Person card: Sofia Beltan

Directory card for Sofia Beltan (person:sofia-beltan).
Member of Care Platform Team.
Standing note: templates customer comms; requests block write access to customer PII.
`Sofia Beltan -> MEMBER_OF -> Care Platform Team`

## person-004 - profile - 2026-01-13
Person card: Bogdan Traistman

Directory card for Bogdan Traistman (person:bogdan-traistman).
Member of Data Platform Team.
Standing on-call rota: Analytics ETL.
Standing note: owns the partner data contract; must clear partner filters with Yuki.
`Bogdan Traistman -> MEMBER_OF -> Data Platform Team`
`Bogdan Traistman -> ONCALL_FOR -> Analytics ETL`

## person-005 - profile - 2026-01-13
Person card: Lin Mei

Directory card for Lin Mei (person:lin-mei).
Member of Order Intake Team.
Standing on-call rota: Orders Intake, Checkout Storefront.
Standing note: approvals for checkout releases only after flag-gate evidence.
`Lin Mei -> MEMBER_OF -> Order Intake Team`
`Lin Mei -> ONCALL_FOR -> Orders Intake`
`Lin Mei -> ONCALL_FOR -> Checkout Storefront`

## person-006 - profile - 2026-01-13
Person card: Taro Kurosawa

Directory card for Taro Kurosawa (person:taro-kurosawa).
Member of Payments Team.
Standing on-call rota: Ledger Mirror, Payout Service.
Standing note: primary pager for ledger mirror and payouts.
`Taro Kurosawa -> MEMBER_OF -> Payments Team`
`Taro Kurosawa -> ONCALL_FOR -> Ledger Mirror`
`Taro Kurosawa -> ONCALL_FOR -> Payout Service`

## person-007 - profile - 2026-01-13
Person card: Celia Hague

Directory card for Celia Hague (person:celia-hague).
Member of Core Storage Team.
Standing on-call rota: Orders Primary.
Standing note: runs restore drills on every transactional store.
`Celia Hague -> MEMBER_OF -> Core Storage Team`
`Celia Hague -> ONCALL_FOR -> Orders Primary`

## person-008 - profile - 2026-01-13
Person card: Jesse Moon

Directory card for Jesse Moon (person:jesse-moon).
Member of Dispatch Team.
Standing note: integrates vendor traffic feeds; owns the fallback provider switch.
`Jesse Moon -> MEMBER_OF -> Dispatch Team`

## person-009 - profile - 2026-01-13
Person card: Nila Venkat

Directory card for Nila Venkat (person:nila-venkat).
Member of Order Intake Team.
Standing on-call rota: Pricing Engine.
Standing note: builds idempotency keys for intake.
`Nila Venkat -> MEMBER_OF -> Order Intake Team`
`Nila Venkat -> ONCALL_FOR -> Pricing Engine`

## person-010 - profile - 2026-01-13
Person card: Omar Diaz

Directory card for Omar Diaz (person:omar-diaz).
Member of Care Platform Team.
Standing on-call rota: Notification Service.
Standing note: owns retry caps and dedupe keys on notifications.
`Omar Diaz -> MEMBER_OF -> Care Platform Team`
`Omar Diaz -> ONCALL_FOR -> Notification Service`

## person-011 - profile - 2026-01-13
Person card: Yuki Tanabe

Directory card for Yuki Tanabe (person:yuki-tanabe).
Member of Data Platform Team.
Standing note: quality of lake snapshots; partner filter co-owner.
`Yuki Tanabe -> MEMBER_OF -> Data Platform Team`

## person-012 - profile - 2026-01-13
Person card: Samir Hadzhi

Directory card for Samir Hadzhi (person:samir-hadzhi).
Member of Payments Team.
Standing note: gateway vendor checks and fraud thresholds.
`Samir Hadzhi -> MEMBER_OF -> Payments Team`

## svc-001 - profile - 2026-01-15
Service profile: Checkout Storefront

Profile record for Checkout Storefront (service:checkout-storefront).
It calls Checkout API.
It reads Orders Primary.
Web portal only; never writes on its own.
`Order Intake Team -> OWNS -> Checkout Storefront`
`Checkout Storefront -> CALLS -> Checkout API`
`Checkout Storefront -> READS_FROM -> Orders Primary`

## svc-002 - profile - 2026-01-15
Service profile: Orders Intake

Profile record for Orders Intake (service:orders-intake).
It publicly exposes Checkout API, Promotions API.
It owns writes to Orders Primary.
It runs its legacy purge routine on Orders Archive.
Care note: Do not confuse with the Legacy Order Feeder, which duplicated intake writes and was retired.
Durable order state machine; idempotency keys keep retries safe.
`Order Intake Team -> OWNS -> Orders Intake`
`Orders Intake -> EXPOSES -> Checkout API`
`Orders Intake -> EXPOSES -> Promotions API`
`Orders Intake -> WRITES_TO -> Orders Primary`
`Orders Intake -> DELETES -> Orders Archive`

## svc-003 - profile - 2026-01-15
Service profile: Pricing Engine

Profile record for Pricing Engine (service:pricing-engine).
It publicly exposes Pricing API.
It reads Orders Archive.
Quote bands with fail-open behavior; also reads the archive for promo history.
`Order Intake Team -> OWNS -> Pricing Engine`
`Pricing Engine -> EXPOSES -> Pricing API`
`Pricing Engine -> READS_FROM -> Orders Archive`

## svc-004 - profile - 2026-01-15
Service profile: Legacy Order Feeder

Profile record for Legacy Order Feeder (service:orders-legacy-etl).
It publicly exposes Checkout API.
It reads Orders Archive.
Retired history-aware feeder; reads only, writes nothing new. It once shared the Checkout API with Orders Intake.
`Order Intake Team -> OWNS -> Legacy Order Feeder`
`Legacy Order Feeder -> EXPOSES -> Checkout API`
`Legacy Order Feeder -> READS_FROM -> Orders Archive`

## api-001 - profile - 2026-01-16
API spec: Checkout API

Spec record for Checkout API (api:checkout-api).
Hosted by Orders Intake.
Reads Orders Primary.
`Orders Intake -> EXPOSES -> Checkout API`
`Checkout API -> READS_FROM -> Orders Primary`

## api-002 - profile - 2026-01-16
API spec: Promotions API

Spec record for Promotions API (api:promo-api).
Hosted by Orders Intake.
Reads Orders Primary.
`Orders Intake -> EXPOSES -> Promotions API`
`Promotions API -> READS_FROM -> Orders Primary`

## api-003 - profile - 2026-01-16
API spec: Pricing API

Spec record for Pricing API (api:pricing-api).
Hosted by Pricing Engine.
Reads Orders Primary.
`Pricing Engine -> EXPOSES -> Pricing API`
`Pricing API -> READS_FROM -> Orders Primary`

## db-001 - profile - 2026-01-17
Database registry: Orders Primary

Registry record for Orders Primary (db:orders-primary).
Replicates forward into: Orders Archive.
Store of record; immutable primary for orders.
`Orders Primary -> REPLICATES_TO -> Orders Archive`

## db-002 - profile - 2026-01-17
Database registry: Orders Archive

Registry record for Orders Archive (db:orders-archive).
Offline retention only; never queried in live order paths.
Disambiguation note: Name overlap trick: the Vision Events Store also gets called an archive in marketing decks; only Orders Archive copies orders.

## db-003 - profile - 2026-01-17
Database registry: Ledger Mirror

Registry record for Ledger Mirror (db:ledger-mirror).
Read replica for finance dashboards; not written by charge paths.

## svc-005 - profile - 2026-01-15
Service profile: Payments Service

Profile record for Payments Service (service:payments).
It calls Checkout API, Warehouse API, Swarm API.
It publicly exposes Payments Gateway API.
It owns writes to Ledger Primary.
Care note: Never writes Orders Primary; ledger persistence only.
Confirms intake through the checkout surface, then charges once.
`Payments Team -> OWNS -> Payments Service`
`Payments Service -> CALLS -> Checkout API`
`Payments Service -> CALLS -> Warehouse API`
`Payments Service -> CALLS -> Swarm API`
`Payments Service -> EXPOSES -> Payments Gateway API`
`Payments Service -> WRITES_TO -> Ledger Primary`

## svc-006 - profile - 2026-01-15
Service profile: Payout Service

Profile record for Payout Service (service:payouts).
It reads Payout Queue.
It owns writes to Payout Queue.
Settles courier days with batch retry rules.
`Payments Team -> OWNS -> Payout Service`
`Payout Service -> READS_FROM -> Payout Queue`
`Payout Service -> WRITES_TO -> Payout Queue`

## api-004 - profile - 2026-01-16
API spec: Payments Gateway API

Spec record for Payments Gateway API (api:payments-gateway-api).
Hosted by Payments Service.
Writes Ledger Primary under transaction scope.
`Payments Service -> EXPOSES -> Payments Gateway API`
`Payments Gateway API -> WRITES_TO -> Ledger Primary`

## db-004 - profile - 2026-01-17
Database registry: Ledger Primary

Registry record for Ledger Primary (db:ledger-primary).
Replicates forward into: Ledger Mirror.
Append-only ledger; the Ledger Immutability Control forbids in-place updates.
`Ledger Primary -> REPLICATES_TO -> Ledger Mirror`

## db-005 - profile - 2026-01-17
Database registry: Fraud Store

Registry record for Fraud Store (db:fraud-store).
Feature store built from ledger mirrors by nightly jobs.
Disambiguation note: Name pairing caution: Fraud Store is not a mirror of Orders Primary.

## db-006 - profile - 2026-01-17
Database registry: Payout Queue

Registry record for Payout Queue (db:payout-queue).
Settlement queue; head-of-line blocking caused an incident here.
Disambiguation note: Do not confuse with Ledger Mirror; the payout queue is write input, the ledger mirror is read output.

## svc-007 - profile - 2026-01-15
Service profile: Warehouse Management

Profile record for Warehouse Management (service:warehouse-mgmt).
It publicly exposes Warehouse API.
It owns writes to Warehouse DB.
Tracks parcel totes inside hubs.
`Dispatch Team -> OWNS -> Warehouse Management`
`Warehouse Management -> EXPOSES -> Warehouse API`
`Warehouse Management -> WRITES_TO -> Warehouse DB`

## svc-008 - profile - 2026-01-15
Service profile: Fleet Dispatch

Profile record for Fleet Dispatch (service:fleet-dispatch).
It calls Warehouse API.
It publicly exposes Swarm API.
It reads Route ETL Store.
It owns writes to Fleet Telemetry Store.
Care note: Never queries Orders Primary; only uses warehouse scan events and vendor routes.
Route assignment with vendor traffic feeds.
`Dispatch Team -> OWNS -> Fleet Dispatch`
`Fleet Dispatch -> CALLS -> Warehouse API`
`Fleet Dispatch -> EXPOSES -> Swarm API`
`Fleet Dispatch -> READS_FROM -> Route ETL Store`
`Fleet Dispatch -> WRITES_TO -> Fleet Telemetry Store`

## svc-009 - profile - 2026-01-15
Service profile: Nimbus Routing

Profile record for Nimbus Routing (service:nimbus-routing).
It calls Swarm API.
It reads Route ETL Store.
Turn-by-turn engine composed from vendors and internal traffic math.
`Dispatch Team -> OWNS -> Nimbus Routing`
`Nimbus Routing -> CALLS -> Swarm API`
`Nimbus Routing -> READS_FROM -> Route ETL Store`

## api-005 - profile - 2026-01-16
API spec: Warehouse API

Spec record for Warehouse API (api:warehouse-api).
Hosted by Warehouse Management.
Writes Vision Events Store under transaction scope.
`Warehouse Management -> EXPOSES -> Warehouse API`
`Warehouse API -> WRITES_TO -> Vision Events Store`

## api-006 - profile - 2026-01-16
API spec: Dispatch API

Spec record for Dispatch API (api:dispatch-api).
Hosted by Fleet Dispatch.
Reads Route ETL Store.
`Fleet Dispatch -> EXPOSES -> Dispatch API`
`Dispatch API -> READS_FROM -> Route ETL Store`

## api-007 - profile - 2026-01-16
API spec: Swarm API

Spec record for Swarm API (api:swarm-api).
Hosted by Fleet Dispatch.
Purge responsibility against Fleet Telemetry Store runs through this endpoint only.
Care note: Fan-out adapter. Payments Service reuses it to reach vendor mapping services.
`Fleet Dispatch -> EXPOSES -> Swarm API`
`Swarm API -> PURGES -> Fleet Telemetry Store`

## db-007 - profile - 2026-01-17
Database registry: Vision Events Store

Registry record for Vision Events Store (db:vision-events).
Replicates forward into: Warehouse DB.
Raw scan events; feeds nightly tote reconciliation into the hub inventory store.
`Vision Events Store -> REPLICATES_TO -> Warehouse DB`

## db-008 - profile - 2026-01-17
Database registry: Fleet Telemetry Store

Registry record for Fleet Telemetry Store (db:telemetry).
Van samples; purged on 90-day windows by the Swarm API.
Disambiguation note: Never used as a ledger mirror; unrelated to charge paths.

## db-009 - profile - 2026-01-17
Database registry: Warehouse DB

Registry record for Warehouse DB (db:warehouse-db).
Hub inventory of totes and rack positions; fed by vision event ingest.

## svc-010 - profile - 2026-01-15
Service profile: Notification Service

Profile record for Notification Service (service:notify).
It publicly exposes Notification API.
It owns writes to Notification Queue.
Milestone texts and emails with strict dedupe keys.
`Care Platform Team -> OWNS -> Notification Service`
`Notification Service -> EXPOSES -> Notification API`
`Notification Service -> WRITES_TO -> Notification Queue`

## svc-011 - profile - 2026-01-15
Service profile: Helpdesk Service

Profile record for Helpdesk Service (service:helpdesk).
It calls Notification API.
It publicly exposes Helpdesk API.
It reads Orders Primary.
Agent console; links cases to parcels and orders.
`Care Platform Team -> OWNS -> Helpdesk Service`
`Helpdesk Service -> CALLS -> Notification API`
`Helpdesk Service -> EXPOSES -> Helpdesk API`
`Helpdesk Service -> READS_FROM -> Orders Primary`

## api-008 - profile - 2026-01-16
API spec: Notification API

Spec record for Notification API (api:notify-api).
Hosted by Notification Service.
Writes Notification Queue under transaction scope.
`Notification Service -> EXPOSES -> Notification API`
`Notification API -> WRITES_TO -> Notification Queue`

## api-009 - profile - 2026-01-16
API spec: Helpdesk API

Spec record for Helpdesk API (api:helpdesk-api).
Hosted by Helpdesk Service.
Reads Orders Primary.
`Helpdesk Service -> EXPOSES -> Helpdesk API`
`Helpdesk API -> READS_FROM -> Orders Primary`

## db-010 - profile - 2026-01-17
Database registry: Notification Queue

Registry record for Notification Queue (db:notify-queue).
Outbound queue; scoped keys keep milestone repeats unique.

## svc-012 - profile - 2026-01-15
Service profile: Analytics ETL

Profile record for Analytics ETL (service:analytics-etl).
It publicly exposes Reporting API.
It reads Ledger Primary, Warehouse DB, Fleet Telemetry Store, Notification Queue.
It owns writes to Analytics Lake.
Nightly extraction into the lake; the bridge across intake, payments, warehouse and support clusters. Note: the lake never ingests Orders Primary; intake history stays in intake storage only.
`Data Platform Team -> OWNS -> Analytics ETL`
`Analytics ETL -> EXPOSES -> Reporting API`
`Analytics ETL -> READS_FROM -> Ledger Primary`
`Analytics ETL -> READS_FROM -> Warehouse DB`
`Analytics ETL -> READS_FROM -> Fleet Telemetry Store`
`Analytics ETL -> READS_FROM -> Notification Queue`
`Analytics ETL -> WRITES_TO -> Analytics Lake`

## svc-013 - profile - 2026-01-15
Service profile: Partner Portal

Profile record for Partner Portal (service:partner-portal).
It calls Reporting API.
Enterprise dashboards.
`Data Platform Team -> OWNS -> Partner Portal`
`Partner Portal -> CALLS -> Reporting API`

## api-010 - profile - 2026-01-16
API spec: Reporting API

Spec record for Reporting API (api:reporting-api).
Hosted by Analytics ETL.
Reads Analytics Lake.
`Analytics ETL -> EXPOSES -> Reporting API`
`Reporting API -> READS_FROM -> Analytics Lake`

## db-011 - profile - 2026-01-17
Database registry: Analytics Lake

Registry record for Analytics Lake (db:analytics-lake).
Columnar lake; carries shared snapshots across every cluster.

## db-012 - profile - 2026-01-17
Database registry: Route ETL Store

Registry record for Route ETL Store (db:route-etl).
Vendor-normalized traffic snapshots.
Disambiguation note: Do not confuse with Fleet Telemetry Store; Route ETL Store holds vendor math.

## ctl-001 - profile - 2026-01-20
Control record: Ledger Immutability Control

Control record for Ledger Immutability Control (control:ledger-immutability).
Protects: Ledger Primary, Ledger Mirror.
Governed by Core Storage Team.
Append-only enforcement; violations page Core Storage immediately.
`Ledger Immutability Control -> PROTECTS -> Ledger Primary`
`Ledger Immutability Control -> PROTECTS -> Ledger Mirror`
`Ledger Immutability Control -> GOVERNED_BY -> Core Storage Team`

## ctl-002 - profile - 2026-01-20
Control record: Launch Flag Gate

Control record for Launch Flag Gate (control:launch-flag-gate).
Protects: Checkout Storefront, Orders Intake.
Governed by Order Intake Team.
Higher-traffic order paths must ramp behind feature flags.
`Launch Flag Gate -> PROTECTS -> Checkout Storefront`
`Launch Flag Gate -> PROTECTS -> Orders Intake`
`Launch Flag Gate -> GOVERNED_BY -> Order Intake Team`

## ctl-003 - profile - 2026-01-20
Control record: Isolation Control

Control record for Isolation Control (control:customer-isolation).
Protects: Orders Primary, Warehouse DB.
Governed by Core Storage Team.
Row scoping enforced on shared stores; a hard requirement for regulated customers.
`Isolation Control -> PROTECTS -> Orders Primary`
`Isolation Control -> PROTECTS -> Warehouse DB`
`Isolation Control -> GOVERNED_BY -> Core Storage Team`

## ctl-004 - profile - 2026-01-20
Control record: Fraud Threshold Review

Control record for Fraud Threshold Review (control:fraud-threshold-review).
Protects: Fraud Store, Ledger Primary.
Governed by Payments Team.
Cutoff review before every promotion run.
`Fraud Threshold Review -> PROTECTS -> Fraud Store`
`Fraud Threshold Review -> PROTECTS -> Ledger Primary`
`Fraud Threshold Review -> GOVERNED_BY -> Payments Team`

## ctl-005 - profile - 2026-01-20
Control record: Vendor Vulnerability Scan

Control record for Vendor Vulnerability Scan (control:vendor-vuln-scan).
Protects: Fleet Dispatch, Checkout Storefront.
Governed by Order Intake Team.
Vendor dependencies pass the scan gate monthly.
`Vendor Vulnerability Scan -> PROTECTS -> Fleet Dispatch`
`Vendor Vulnerability Scan -> PROTECTS -> Checkout Storefront`
`Vendor Vulnerability Scan -> GOVERNED_BY -> Order Intake Team`

## ctl-006 - profile - 2026-01-20
Control record: Restore Drill Control

Control record for Restore Drill Control (control:backup-restore-drill).
Protects: Orders Primary, Ledger Primary, Warehouse DB.
Governed by Core Storage Team.
Quarterly restore proof for every transactional store; Aurora Compute keeps the restore points.
`Restore Drill Control -> PROTECTS -> Orders Primary`
`Restore Drill Control -> PROTECTS -> Ledger Primary`
`Restore Drill Control -> PROTECTS -> Warehouse DB`
`Restore Drill Control -> GOVERNED_BY -> Core Storage Team`

## ctl-007 - profile - 2026-01-20
Control record: On-call Escalation Control

Control record for On-call Escalation Control (control:oncall-escalation).
Protects: Orders Primary.
Governed by Core Storage Team.
Pages a named responder within five minutes of dispatch.
`On-call Escalation Control -> PROTECTS -> Orders Primary`
`On-call Escalation Control -> GOVERNED_BY -> Core Storage Team`

## ctl-008 - profile - 2026-01-20
Control record: Annual Penetration Test

Control record for Annual Penetration Test (control:pen-test-cycle).
Governed by Payments Team.
Annual external test of customer surfaces such as checkout and partner portals.
`Annual Penetration Test -> GOVERNED_BY -> Payments Team`

## vend-001 - profile - 2026-01-22
Vendor record: Aurora Compute

Vendor record for Aurora Compute (vendor:aurora-compute).
Supplies: Orders Primary, Ledger Primary.
Managed hosting of the two stores of record; provides backup restore points.
`Aurora Compute -> SUPPLIES -> Orders Primary`
`Aurora Compute -> SUPPLIES -> Ledger Primary`

## vend-002 - profile - 2026-01-22
Vendor record: Solvex Gateway

Vendor record for Solvex Gateway (vendor:solvex-gateway).
Supplies: Payments Gateway API.
Acquiring gateway behind Payments Service; the only vendor authorized to clear charge requests.
`Solvex Gateway -> SUPPLIES -> Payments Gateway API`

## vend-003 - profile - 2026-01-22
Vendor record: Orchard Routes

Vendor record for Orchard Routes (vendor:orchard-routes).
Supplies: Route ETL Store.
Fallback geodata vendor; used after the primary mapping feed degraded. Route math only; never payment data.
`Orchard Routes -> SUPPLIES -> Route ETL Store`

## vend-004 - profile - 2026-01-22
Vendor record: DeltaWave Communications

Vendor record for DeltaWave Communications (vendor:deltawave-comms).
Supplies: Notification Queue.
Transport vendor; holds the retry throttle for customer texts.
`DeltaWave Communications -> SUPPLIES -> Notification Queue`

## vend-005 - profile - 2026-01-22
Vendor record: Harbour Audit

Vendor record for Harbour Audit (vendor:harbour-audit).
Independent ledger archive auditor; issues the annual retention finding.

## vend-006 - profile - 2026-01-22
Vendor record: Pinefork Hardware

Vendor record for Pinefork Hardware (vendor:pinefork-hardware).
Supplies: Warehouse Management.
Hardware cameras on sortation lines.
`Pinefork Hardware -> SUPPLIES -> Warehouse Management`

## vend-007 - profile - 2026-01-22
Vendor record: Granite Peaks Consulting

Vendor record for Granite Peaks Consulting (vendor:granite-peaks).
External pen-test vendor; scope is checkout and partner surfaces.

## vend-008 - profile - 2026-01-22
Vendor record: Nimbus Maps

Vendor record for Nimbus Maps (vendor:nimbus-maps).
Supplies: Route ETL Store.
Primary geodata and traffic vendor for Fleet Dispatch.
`Nimbus Maps -> SUPPLIES -> Route ETL Store`

## cust-001 - profile - 2026-01-25
Customer record: Acme Retail

Customer entitlement record for Acme Retail (customer:acme-retail).
Uses: Orders Intake, Checkout Storefront.
Requires controls: Isolation Control.
Latency SLA posture; escalation path is Lin Mei or on-call intake.
`Acme Retail -> USES -> Orders Intake`
`Acme Retail -> USES -> Checkout Storefront`
`Acme Retail -> REQUIRES -> Isolation Control`

## cust-002 - profile - 2026-01-25
Customer record: Windward Grocers

Customer entitlement record for Windward Grocers (customer:windward-grocers).
Uses: Orders Intake, Fleet Dispatch.
Requires controls: Isolation Control, Restore Drill Control.
Perishables; telemetry freshness is contractual.
`Windward Grocers -> USES -> Orders Intake`
`Windward Grocers -> USES -> Fleet Dispatch`
`Windward Grocers -> REQUIRES -> Isolation Control`
`Windward Grocers -> REQUIRES -> Restore Drill Control`

## cust-003 - profile - 2026-01-25
Customer record: Lakeside Pharmacy

Customer entitlement record for Lakeside Pharmacy (customer:lakeside-pharmacy).
Uses: Orders Intake, Warehouse Management.
Requires controls: Isolation Control, Annual Penetration Test.
Regulated deliveries with pharmacy notifications.
`Lakeside Pharmacy -> USES -> Orders Intake`
`Lakeside Pharmacy -> USES -> Warehouse Management`
`Lakeside Pharmacy -> REQUIRES -> Isolation Control`
`Lakeside Pharmacy -> REQUIRES -> Annual Penetration Test`

## cust-004 - profile - 2026-01-25
Customer record: Solstice Media

Customer entitlement record for Solstice Media (customer:solstice-media).
Uses: Checkout Storefront, Orders Intake.
Requires controls: Fraud Threshold Review.
Runs the August promo stacking pilot alongside Solstice Media benchmark tests.
`Solstice Media -> USES -> Checkout Storefront`
`Solstice Media -> USES -> Orders Intake`
`Solstice Media -> REQUIRES -> Fraud Threshold Review`

## cust-005 - profile - 2026-01-25
Customer record: Vaulttree Estate

Customer entitlement record for Vaulttree Estate (customer:vaulttree-estate).
Uses: Orders Intake, Payout Service.
Requires controls: Ledger Immutability Control.
Held under high-priority thresholds with: Payout Service.
High-value shipments demand payout ledger history.
`Vaulttree Estate -> USES -> Orders Intake`
`Vaulttree Estate -> USES -> Payout Service`
`Vaulttree Estate -> REQUIRES -> Ledger Immutability Control`
`Vaulttree Estate -> HELD_BY -> Payout Service`

## cust-006 - profile - 2026-01-25
Customer record: Nordhollow Books

Customer entitlement record for Nordhollow Books (customer:nordhollow-books).
Uses: Orders Intake.
Requires controls: Isolation Control.
Shield tier across the north region.
`Nordhollow Books -> USES -> Orders Intake`
`Nordhollow Books -> REQUIRES -> Isolation Control`

## cust-007 - profile - 2026-01-25
Customer record: Cindergate Supply

Customer entitlement record for Cindergate Supply (customer:cindergate-supply).
Uses: Warehouse Management, Fleet Dispatch.
Requires controls: Isolation Control.
Scan-heavy industrial account.
`Cindergate Supply -> USES -> Warehouse Management`
`Cindergate Supply -> USES -> Fleet Dispatch`
`Cindergate Supply -> REQUIRES -> Isolation Control`

## cust-008 - profile - 2026-01-25
Customer record: Orchid Lake Boutique

Customer entitlement record for Orchid Lake Boutique (customer:orchid-lake-boutique).
Uses: Notification Service, Orders Intake.
Requires controls: On-call Escalation Control.
June seasonal drops drive customer text volume.
`Orchid Lake Boutique -> USES -> Notification Service`
`Orchid Lake Boutique -> USES -> Orders Intake`
`Orchid Lake Boutique -> REQUIRES -> On-call Escalation Control`

## cust-009 - profile - 2026-01-25
Customer record: Tramline Couriers

Customer entitlement record for Tramline Couriers (customer:tramline-couriers).
Uses: Payout Service, Orders Intake.
Requires controls: Ledger Immutability Control.
Held under high-priority thresholds with: Payout Service.
Courier settlement aggregator.
`Tramline Couriers -> USES -> Payout Service`
`Tramline Couriers -> USES -> Orders Intake`
`Tramline Couriers -> REQUIRES -> Ledger Immutability Control`
`Tramline Couriers -> HELD_BY -> Payout Service`

## cust-010 - profile - 2026-01-25
Customer record: Greenfield Care

Customer entitlement record for Greenfield Care (customer:greenfield-care).
Uses: Notification Service.
Requires controls: On-call Escalation Control.
Notified templates for pharmacy reminders.
`Greenfield Care -> USES -> Notification Service`
`Greenfield Care -> REQUIRES -> On-call Escalation Control`

## rel-001 - profile - 2026-01-18
Release note: Checkout Release v2

Release record for Checkout Release v2 (release:checkout-v2).
Shipped changes into: Checkout Storefront.
Approved by Lin Mei; available in the February window.
Shipping note: builds the promo stacking pilot.
`Checkout Release v2 -> SHIPS -> Checkout Storefront`
`Lin Mei -> APPROVED -> Checkout Release v2`

## rel-002 - profile - 2026-01-18
Release note: Checkout Release v3

Release record for Checkout Release v3 (release:checkout-v3).
Shipped changes into: Checkout Storefront.
Approved by Lin Mei; available in the August window.
Side fact: Checkout Release v3 introduced Promotions API.
Side fact: promo fail-open defaults shipped in this cut.
`Checkout Release v3 -> SHIPS -> Checkout Storefront`
`Lin Mei -> APPROVED -> Checkout Release v3`
`Checkout Release v3 -> INTRODUCED -> Promotions API`

## rel-003 - profile - 2026-01-18
Release note: Orders Release v9

Release record for Orders Release v9 (release:orders-v9).
Shipped changes into: Orders Intake.
Approved by Lin Mei; available in the May window.
Idempotency keys landed as the intake retry-safety change.
`Orders Release v9 -> SHIPS -> Orders Intake`
`Lin Mei -> APPROVED -> Orders Release v9`

## rel-004 - profile - 2026-01-18
Release note: Orders Release v10

Release record for Orders Release v10 (release:orders-v10).
Shipped changes into: Orders Intake.
Approved by Lin Mei; available in the September window.
Intake burst quota brought under the gateway cut.
`Orders Release v10 -> SHIPS -> Orders Intake`
`Lin Mei -> APPROVED -> Orders Release v10`

## rel-005 - profile - 2026-01-18
Release note: Payments Release v7

Release record for Payments Release v7 (release:payments-v7).
Shipped changes into: Payments Service.
Approved by Mara Okafor; available in the April window.
Side fact: Payments Release v7 introduced Ledger Primary.
Known consequence: contributed to the April overcharge run through refund dedupe gaps; the incident record carries the causal edge.
`Payments Release v7 -> SHIPS -> Payments Service`
`Mara Okafor -> APPROVED -> Payments Release v7`
`Payments Release v7 -> INTRODUCED -> Ledger Primary`

## rel-006 - profile - 2026-01-18
Release note: Payments Release v8

Release record for Payments Release v8 (release:payments-v8).
Shipped changes into: Payments Service, Payout Service.
Approved by Mara Okafor; available in the July window.
Held by Mara before clearing payout ownership.
`Payments Release v8 -> SHIPS -> Payments Service`
`Payments Release v8 -> SHIPS -> Payout Service`
`Mara Okafor -> APPROVED -> Payments Release v8`

## rel-007 - profile - 2026-01-18
Release note: Payments Release v9

Release record for Payments Release v9 (release:payments-v9).
Shipped changes into: Payments Service.
Approved by Mara Okafor; available in the December window.
Ledger mirror lag probe flows for dashboards.
`Payments Release v9 -> SHIPS -> Payments Service`
`Mara Okafor -> APPROVED -> Payments Release v9`

## rel-008 - profile - 2026-01-18
Release note: Warehouse Release v6

Release record for Warehouse Release v6 (release:warehouse-v6).
Shipped changes into: Warehouse Management.
Approved by Ravi Mohan; available in the August window.
Vision thresholds shipped after the July mismatch was reviewed.
`Warehouse Release v6 -> SHIPS -> Warehouse Management`
`Ravi Mohan -> APPROVED -> Warehouse Release v6`

## rel-009 - profile - 2026-01-18
Release note: Fleet Release v5

Release record for Fleet Release v5 (release:fleet-v5).
Shipped changes into: Fleet Dispatch.
Approved by Ravi Mohan; available in the October window.
Clock-skew guard landed straight into the release used after the dispatch glitch.
`Fleet Release v5 -> SHIPS -> Fleet Dispatch`
`Ravi Mohan -> APPROVED -> Fleet Release v5`

## rel-010 - profile - 2026-01-18
Release note: Notification Release v6

Release record for Notification Release v6 (release:notify-v6).
Shipped changes into: Notification Service.
Approved by Sofia Beltan; available in the July window.
Queue backpressure caps introduced before the June flood fix.
`Notification Release v6 -> SHIPS -> Notification Service`
`Sofia Beltan -> APPROVED -> Notification Release v6`

## rel-011 - profile - 2026-01-18
Release note: Notification Release v7

Release record for Notification Release v7 (release:notify-v7).
Shipped changes into: Notification Service.
Approved by Sofia Beltan; available in the September window.
Milestone template dedupe keys.
`Notification Release v7 -> SHIPS -> Notification Service`
`Sofia Beltan -> APPROVED -> Notification Release v7`

## rel-012 - profile - 2026-01-18
Release note: ETL Release v12

Release record for ETL Release v12 (release:etl-v12).
Shipped changes into: Analytics ETL.
Approved by Bogdan Traistman; available in the November window.
Lake compaction plus partner filter surfaces land together.
`ETL Release v12 -> SHIPS -> Analytics ETL`
`Bogdan Traistman -> APPROVED -> ETL Release v12`

## rel-013 - profile - 2026-01-18
Release note: Helpdesk Release v3

Release record for Helpdesk Release v3 (release:helpdesk-v3).
Shipped changes into: Helpdesk Service.
Approved by Sofia Beltan; available in the June window.
Cross-parcel case linking shipped.
`Helpdesk Release v3 -> SHIPS -> Helpdesk Service`
`Sofia Beltan -> APPROVED -> Helpdesk Release v3`

## rel-014 - profile - 2026-01-18
Release note: Payout Release v2

Release record for Payout Release v2 (release:payout-v2).
Shipped changes into: Payout Service.
Approved by Mara Okafor; available in the June window.
Settlement retry scheduling rules after the head-of-line finding.
`Payout Release v2 -> SHIPS -> Payout Service`
`Mara Okafor -> APPROVED -> Payout Release v2`

## inc-001 - profile - 2026-03-09
Incident record: Blue Monday Ledger Stall

Incident record Blue Monday Ledger Stall (incident:blue-monday); opened 2026-03-09.
Service impact: Payments Service.
Store impact: Ledger Primary.
Incident commander: Taro Kurosawa (the on-call escalation rule requires a named responder within five minutes).
Negative evidence: investigation cleared Payments Release v7; it did not cause this incident (charge batching is unrelated; batching landed later in April).
Customer-visible symptoms: Ledger writes stalled during morning peaks; payouts unaffected.
`Blue Monday Ledger Stall -> AFFECTED -> Payments Service`
`Blue Monday Ledger Stall -> AFFECTED_D -> Ledger Primary`
`Blue Monday Ledger Stall -> ALERTED -> Payments Service`
`Blue Monday Ledger Stall -> ALERTED -> Ledger Primary`
`Taro Kurosawa -> RCA_BY -> Blue Monday Ledger Stall`
`Blue Monday Ledger Stall -> !CAUSED_BY -> Payments Release v7` (charge batching is unrelated; batching landed later in April)

## inc-002 - profile - 2026-04-14
Incident record: April Overcharge Run

Incident record April Overcharge Run (incident:overcharge-run); opened 2026-04-14.
Service impact: Payments Service.
Incident commander: Mara Okafor (the on-call escalation rule requires a named responder within five minutes).
Preliminary attribution: Payments Release v7 — refund dedupe missed stale idempotency keys.
Customer-visible symptoms: Duplicate charge rows on promo tests; Windward Grocers and Solstice Media both issued refunds.
`April Overcharge Run -> AFFECTED -> Payments Service`
`April Overcharge Run -> ALERTED -> Payments Service`
`Mara Okafor -> RCA_BY -> April Overcharge Run`
`April Overcharge Run -> CAUSED_BY -> Payments Release v7` (refund dedupe missed stale idempotency keys)

## inc-003 - profile - 2026-05-14
Incident record: Payout Delay Thursday

Incident record Payout Delay Thursday (incident:payout-delay); opened 2026-05-14.
Service impact: Payout Service.
Store impact: Payout Queue.
Incident commander: Taro Kurosawa (the on-call escalation rule requires a named responder within five minutes).
Negative evidence: investigation cleared Payments Release v8; it did not cause this incident (charge-side split had no settlement residue).
Customer-visible symptoms: Courier batches delayed by head-of-line blocking in the Payout Queue.
`Payout Delay Thursday -> AFFECTED -> Payout Service`
`Payout Delay Thursday -> AFFECTED_D -> Payout Queue`
`Payout Delay Thursday -> ALERTED -> Payout Service`
`Payout Delay Thursday -> ALERTED -> Payout Queue`
`Taro Kurosawa -> RCA_BY -> Payout Delay Thursday`
`Payout Delay Thursday -> !CAUSED_BY -> Payments Release v8` (charge-side split had no settlement residue)

## inc-004 - profile - 2026-06-11
Incident record: June Lake Gaps

Incident record June Lake Gaps (incident:etl-gaps); opened 2026-06-11.
Service impact: Partner Portal, Analytics ETL.
Store impact: Analytics Lake.
Incident commander: Bogdan Traistman (the on-call escalation rule requires a named responder within five minutes).
Negative evidence: investigation cleared ETL Release v12; it did not cause this incident (compaction shipped in November; cannot explain the June gap).
Customer-visible symptoms: Partner dashboards showed June 4-7 ledger partitions missing.
`June Lake Gaps -> AFFECTED -> Partner Portal`
`June Lake Gaps -> AFFECTED -> Analytics ETL`
`June Lake Gaps -> AFFECTED_D -> Analytics Lake`
`June Lake Gaps -> ALERTED -> Partner Portal`
`June Lake Gaps -> ALERTED -> Analytics ETL`
`June Lake Gaps -> ALERTED -> Analytics Lake`
`Bogdan Traistman -> RCA_BY -> June Lake Gaps`
`June Lake Gaps -> !CAUSED_BY -> ETL Release v12` (compaction shipped in November; cannot explain the June gap)

## inc-005 - profile - 2026-06-30
Incident record: June Notification Flood

Incident record June Notification Flood (incident:notify-flood); opened 2026-06-30.
Service impact: Notification Service.
Store impact: Notification Queue.
Incident commander: Omar Diaz (the on-call escalation rule requires a named responder within five minutes).
Customer-visible symptoms: Retry storm produced duplicate customer texts for Windward Grocers.
`June Notification Flood -> AFFECTED -> Notification Service`
`June Notification Flood -> AFFECTED_D -> Notification Queue`
`June Notification Flood -> ALERTED -> Notification Service`
`June Notification Flood -> ALERTED -> Notification Queue`
`Omar Diaz -> RCA_BY -> June Notification Flood`

## inc-006 - profile - 2026-07-21
Incident record: July Duplicate Labels

Incident record July Duplicate Labels (incident:duplicate-labels); opened 2026-07-21.
Service impact: Warehouse Management.
Store impact: Vision Events Store, Warehouse DB.
Incident commander: Ravi Mohan (the on-call escalation rule requires a named responder within five minutes).
Negative evidence: investigation cleared Warehouse Release v6; it did not cause this incident (threshold rewrite shipped in August after this incident; timing excludes it).
Customer-visible symptoms: Two totes matched one carton on the Pinefork line.
`July Duplicate Labels -> AFFECTED -> Warehouse Management`
`July Duplicate Labels -> AFFECTED_D -> Vision Events Store`
`July Duplicate Labels -> AFFECTED_D -> Warehouse DB`
`July Duplicate Labels -> ALERTED -> Warehouse Management`
`July Duplicate Labels -> ALERTED -> Vision Events Store`
`July Duplicate Labels -> ALERTED -> Warehouse DB`
`Ravi Mohan -> RCA_BY -> July Duplicate Labels`
`July Duplicate Labels -> !CAUSED_BY -> Warehouse Release v6` (threshold rewrite shipped in August after this incident; timing excludes it)

## inc-007 - profile - 2026-08-05
Incident record: August Gateway 403 Surge

Incident record August Gateway 403 Surge (incident:gateway-403); opened 2026-08-05.
Service impact: Checkout Storefront, Orders Intake.
Incident commander: Jesse Moon (the on-call escalation rule requires a named responder within five minutes).
Customer-visible symptoms: Bursts of 403 through the public path during promo stacking.
`August Gateway 403 Surge -> AFFECTED -> Checkout Storefront`
`August Gateway 403 Surge -> AFFECTED -> Orders Intake`
`August Gateway 403 Surge -> ALERTED -> Checkout Storefront`
`August Gateway 403 Surge -> ALERTED -> Orders Intake`
`Jesse Moon -> RCA_BY -> August Gateway 403 Surge`

## inc-008 - profile - 2026-09-02
Incident record: September Ledger Stall

Incident record September Ledger Stall (incident:ledger-stall); opened 2026-09-02.
Service impact: Payments Service.
Store impact: Ledger Primary, Ledger Mirror.
Incident commander: Taro Kurosawa (the on-call escalation rule requires a named responder within five minutes).
Negative evidence: investigation cleared Payments Release v8; it did not cause this incident (the payout split did not touch failover logic).
Customer-visible symptoms: An append lost a replica mid-failover; mirror lag spiked.
`September Ledger Stall -> AFFECTED -> Payments Service`
`September Ledger Stall -> AFFECTED_D -> Ledger Primary`
`September Ledger Stall -> AFFECTED_D -> Ledger Mirror`
`September Ledger Stall -> ALERTED -> Payments Service`
`September Ledger Stall -> ALERTED -> Ledger Primary`
`September Ledger Stall -> ALERTED -> Ledger Mirror`
`Taro Kurosawa -> RCA_BY -> September Ledger Stall`
`September Ledger Stall -> !CAUSED_BY -> Payments Release v8` (the payout split did not touch failover logic)

## inc-009 - profile - 2026-10-06
Incident record: October Dispatch Clock Slip

Incident record October Dispatch Clock Slip (incident:dispatch-clock-slip); opened 2026-10-06.
Service impact: Fleet Dispatch.
Store impact: Fleet Telemetry Store.
Incident commander: Ravi Mohan (the on-call escalation rule requires a named responder within five minutes).
Negative evidence: investigation cleared Fleet Release v5; it did not cause this incident (skew guard shipped in the same month as the slip; not causal).
Customer-visible symptoms: Route assignments shifted 40 minutes during the vendor feed swap.
`October Dispatch Clock Slip -> AFFECTED -> Fleet Dispatch`
`October Dispatch Clock Slip -> AFFECTED_D -> Fleet Telemetry Store`
`October Dispatch Clock Slip -> ALERTED -> Fleet Dispatch`
`October Dispatch Clock Slip -> ALERTED -> Fleet Telemetry Store`
`Ravi Mohan -> RCA_BY -> October Dispatch Clock Slip`
`October Dispatch Clock Slip -> !CAUSED_BY -> Fleet Release v5` (skew guard shipped in the same month as the slip; not causal)

## inc-010 - profile - 2026-05-28
Incident record: May Archive Slowdown

Incident record May Archive Slowdown (incident:archive-slowdown); opened 2026-05-28.
Service impact: Orders Intake.
Store impact: Orders Archive, Orders Primary.
Incident commander: Celia Hague (the on-call escalation rule requires a named responder within five minutes).
Customer-visible symptoms: Retention scans slowed reads on the order path; the Orders Archive copy itself stayed healthy.
`May Archive Slowdown -> AFFECTED -> Orders Intake`
`May Archive Slowdown -> AFFECTED_D -> Orders Archive`
`May Archive Slowdown -> AFFECTED_D -> Orders Primary`
`May Archive Slowdown -> ALERTED -> Orders Intake`
`May Archive Slowdown -> ALERTED -> Orders Archive`
`May Archive Slowdown -> ALERTED -> Orders Primary`
`Celia Hague -> RCA_BY -> May Archive Slowdown`

## postmortem-001 - postmortem - 2026-09-09
Postmortem: September Ledger Stall

Postmortem for September Ledger Stall (incident:ledger-stall); finalized 2026-09-09; commander Taro Kurosawa.
Proven causal path: Payments Release v9 — ledger mirror lag probe read stale failover state and short-circuited an append.
Explicit negative evidence: Payments Release v8 was cleared by investigation; it did not cause this incident (the payout split did not touch failover logic).
Explicit negative evidence: Ledger Immutability Control was cleared by investigation; it did not cause this incident (the control executed correctly; the probe bypassed it).
Highlight: Cross-cluster probing between payments and dispatch was needed.
Highlight: Timeline pinned at 14:12 local through mirror audit.
Compliance: the Ledger Immutability Control held; the probe read-only path was the gap.
`Taro Kurosawa -> RCA_BY -> September Ledger Stall`
`September Ledger Stall -> CAUSED_BY -> Payments Release v9` (ledger mirror lag probe read stale failover state and short-circuited an append)
`September Ledger Stall -> !CAUSED_BY -> Payments Release v8` (the payout split did not touch failover logic)
`September Ledger Stall -> !CAUSED_BY -> Ledger Immutability Control` (the control executed correctly; the probe bypassed it)

## postmortem-002 - postmortem - 2026-05-20
Postmortem: Payout Delay Thursday

Postmortem for Payout Delay Thursday (incident:payout-delay); finalized 2026-05-20; commander Taro Kurosawa.
Explicit negative evidence: Payments Release v8 was cleared by investigation; it did not cause this incident (charge-side split had no settlement residue).
Explicit negative evidence: On-call Escalation Control was cleared by investigation; it did not cause this incident (paging escalated within the five-minute rule as required).
Highlight: Payout queue head-of-line shape documented.
Highlight: Fixes landed in Payout Release v2 in June.
The settlement queue now alerts on the first blocked batch.
`Taro Kurosawa -> RCA_BY -> Payout Delay Thursday`
`Payout Delay Thursday -> !CAUSED_BY -> Payments Release v8` (charge-side split had no settlement residue)
`Payout Delay Thursday -> !CAUSED_BY -> On-call Escalation Control` (paging escalated within the five-minute rule as required)

## postmortem-003 - postmortem - 2026-08-11
Postmortem: August Gateway 403 Surge

Postmortem for August Gateway 403 Surge (incident:gateway-403); finalized 2026-08-11; commander Jesse Moon.
Proven causal path: Checkout Release v3 — promo fail-open generated a request burst the gateway classifier treated as abuse.
Explicit negative evidence: Checkout Release v2 was cleared by investigation; it did not cause this incident (the v2 rollout predates the August surge).
Explicit negative evidence: Launch Flag Gate was cleared by investigation; it did not cause this incident (the flag gate executed cleanly; the burst was a response-class shape problem).
Highlight: Vendor Solvex saw the same shape and confirmed burst classification.
Promo burst caps shipped as a hotfix.
`Jesse Moon -> RCA_BY -> August Gateway 403 Surge`
`August Gateway 403 Surge -> CAUSED_BY -> Checkout Release v3` (promo fail-open generated a request burst the gateway classifier treated as abuse)
`August Gateway 403 Surge -> !CAUSED_BY -> Checkout Release v2` (the v2 rollout predates the August surge)
`August Gateway 403 Surge -> !CAUSED_BY -> Launch Flag Gate` (the flag gate executed cleanly; the burst was a response-class shape problem)

## postmortem-004 - postmortem - 2026-06-18
Postmortem: June Lake Gaps

Postmortem for June Lake Gaps (incident:etl-gaps); finalized 2026-06-18; commander Bogdan Traistman.
Proven causal path: Notification Release v6 — notification queue changes shared a retry id with the ETL scheduler; nightly copies skipped partitions.
Explicit negative evidence: ETL Release v12 was cleared by investigation; it did not cause this incident (compaction landed long after the June gaps).
Highlight: Yuki built the June 4-7 gap alert.
Partner filters shipped with Tracker version 13 of the reporting surface.
`Bogdan Traistman -> RCA_BY -> June Lake Gaps`
`June Lake Gaps -> CAUSED_BY -> Notification Release v6` (notification queue changes shared a retry id with the ETL scheduler; nightly copies skipped partitions)
`June Lake Gaps -> !CAUSED_BY -> ETL Release v12` (compaction landed long after the June gaps)

## postmortem-005 - postmortem - 2026-07-07
Postmortem: June Notification Flood

Postmortem for June Notification Flood (incident:notify-flood); finalized 2026-07-07; commander Omar Diaz.
Proven causal path: Notification Release v6 — unbounded retries ran while the backpressure caps were being tuned; the flood forced the cap rollout.
Explicit negative evidence: ETL Release v12 was cleared by investigation; it did not cause this incident (lake compaction is unrelated to the message line).
Cap tuning completed in July; the June 30 storm predated the shipped caps.
`Omar Diaz -> RCA_BY -> June Notification Flood`
`June Notification Flood -> CAUSED_BY -> Notification Release v6` (unbounded retries ran while the backpressure caps were being tuned; the flood forced the cap rollout)
`June Notification Flood -> !CAUSED_BY -> ETL Release v12` (lake compaction is unrelated to the message line)

## postmortem-006 - postmortem - 2026-03-15
Postmortem: Blue Monday Ledger Stall

Postmortem for Blue Monday Ledger Stall (incident:blue-monday); finalized 2026-03-15; commander Taro Kurosawa.
Proven causal path: Checkout Release v2 — quote caching inflated morning checkout concurrency and stalled ledger appends.
Explicit negative evidence: Payments Release v7 was cleared by investigation; it did not cause this incident (charge batching shipped in April; the fault window was March).
Highlight: First cross-cluster ticket between Payments and Intake.
Highlight: Root fix: intake quote throttling.
The Ledger Immutability Control held throughout.
`Taro Kurosawa -> RCA_BY -> Blue Monday Ledger Stall`
`Blue Monday Ledger Stall -> CAUSED_BY -> Checkout Release v2` (quote caching inflated morning checkout concurrency and stalled ledger appends)
`Blue Monday Ledger Stall -> !CAUSED_BY -> Payments Release v7` (charge batching shipped in April; the fault window was March)

## postmortem-007 - postmortem - 2026-04-21
Postmortem: April Overcharge Run

Postmortem for April Overcharge Run (incident:overcharge-run); finalized 2026-04-21; commander Mara Okafor.
Proven causal path: Payments Release v7 — refund dedupe key reused checkout idempotency keys.
Explicit negative evidence: Orders Release v9 was cleared by investigation; it did not cause this incident (intake idempotency keys behaved as designed).
Highlight: Ledger reconciliation issued refunds by April 30.
The Ledger Immutability Control was not violated; corrections were appended only.
`Mara Okafor -> RCA_BY -> April Overcharge Run`
`April Overcharge Run -> CAUSED_BY -> Payments Release v7` (refund dedupe key reused checkout idempotency keys)
`April Overcharge Run -> !CAUSED_BY -> Orders Release v9` (intake idempotency keys behaved as designed)

## postmortem-008 - postmortem - 2026-07-28
Postmortem: July Duplicate Labels

Postmortem for July Duplicate Labels (incident:duplicate-labels); finalized 2026-07-28; commander Ravi Mohan.
Proven causal path: Jesse Moon — vendor scan pose calibration had drifted after the new camera rig.
Explicit negative evidence: Warehouse Release v6 was cleared by investigation; it did not cause this incident (threshold rewrite shipped after the July mismatch).
Highlight: Hardware fix from Pinefork.
Tote reconciliation rerun clean on July 23.
`Ravi Mohan -> RCA_BY -> July Duplicate Labels`
`July Duplicate Labels -> CAUSED_BY -> Jesse Moon` (vendor scan pose calibration had drifted after the new camera rig)
`July Duplicate Labels -> !CAUSED_BY -> Warehouse Release v6` (threshold rewrite shipped after the July mismatch)

## postmortem-009 - postmortem - 2026-10-12
Postmortem: October Dispatch Clock Slip

Postmortem for October Dispatch Clock Slip (incident:dispatch-clock-slip); finalized 2026-10-12; commander Ravi Mohan.
Proven causal path: Nimbus Maps — primary feed handed out skewed timestamps during the vendor swap.
Explicit negative evidence: Orchard Routes was cleared by investigation; it did not cause this incident (the fallback feed stayed healthy all shift).
Explicit negative evidence: Fleet Release v5 was cleared by investigation; it did not cause this incident (the skew guard landed too late to prevent the slip).
Highlight: Clock sync fixed via internal time source from core hosts.
No mapping vendor changes needed afterwards.
`Ravi Mohan -> RCA_BY -> October Dispatch Clock Slip`
`October Dispatch Clock Slip -> CAUSED_BY -> Nimbus Maps` (primary feed handed out skewed timestamps during the vendor swap)
`October Dispatch Clock Slip -> !CAUSED_BY -> Orchard Routes` (the fallback feed stayed healthy all shift)
`October Dispatch Clock Slip -> !CAUSED_BY -> Fleet Release v5` (the skew guard landed too late to prevent the slip)

## postmortem-010 - postmortem - 2026-06-03
Postmortem: May Archive Slowdown

Postmortem for May Archive Slowdown (incident:archive-slowdown); finalized 2026-06-03; commander Celia Hague.
Explicit negative evidence: Orders Release v10 was cleared by investigation; it did not cause this incident (the quota guard shipped well after the slowdown).
Explicit negative evidence: Aurora Compute was cleared by investigation; it did not cause this incident (the hosting vendor showed zero storage contention by audit).
Highlight: Retention schedule rebalanced to overnight.
Explicit negative: the Orders Archive stayed healthy; only read paths slowed.
`Celia Hague -> RCA_BY -> May Archive Slowdown`
`May Archive Slowdown -> !CAUSED_BY -> Orders Release v10` (the quota guard shipped well after the slowdown)
`May Archive Slowdown -> !CAUSED_BY -> Aurora Compute` (the hosting vendor showed zero storage contention by audit)

## kb-notify-rumor - kb - 2026-07-01
Support KB: guessed cause of the June flood

Rumor: Notification Release v7 opened the June flood.
This note was written the day after the storm, before any timeline review.

## kb-mirror-rumor - kb - 2026-04-18
Finance KB: draft copy about the ledger replica

Draft claim: Ledger Mirror reads Orders Primary as a secondary source.
The registry draft that spawned this claim was never promoted.

## kb-retention-rumor - kb - 2026-05-29
Storage KB: suspected drill violation

Rumor: the May archive slowdown broke the Restore Drill Control.
Written by a shift engineer before the drill evidence landed.

## kb-payout-rumor - kb - 2026-05-15
Ops KB: guessed cause of the payout delay

Rumor: Payout Release v2 caused Payout Delay Thursday.
Antedates the release calendar check.

## kb-routes-rumor - kb - 2026-09-20
Routing KB: who feeds the route store

Rumor: Orchard Routes supplies the Ledger Mirror data set.
Conflates the route store with the mirror during an onboarding slide review.

## kb-gateway-rumor - kb - 2026-08-20
Checkout KB: approval gossip

Rumor: approval for Checkout Release v3 was withdrawn in mid-August.
Circulated in a chat thread without a calendar citation.

## corr-001 - correction - 2026-10-04
Correction notice: supersedes kb-notify-rumor

Correction: the June Notification Flood was not opened by Notification Release v7. That release shipped in September; the flood was June 30. The support KB note is superseded.
Superseded statement: 'Notification Release v7 opened the June flood.'
`June Notification Flood -> !CAUSED_BY -> Notification Release v7` (supersedes kb-notify-rumor)
Supersedes: kb-notify-rumor.

## corr-002 - correction - 2026-04-20
Correction notice: supersedes kb-mirror-rumor

Correction: Orders Primary does not replicate into Ledger Mirror. The mirror receives Ledger Primary only. The finance KB draft is superseded.
Superseded statement: 'Ledger Mirror reads Orders Primary as a secondary source.'
`Orders Primary -> !REPLICATES_TO -> Ledger Mirror` (supersedes kb-mirror-rumor)
Supersedes: kb-mirror-rumor.

## corr-003 - correction - 2026-06-12
Correction notice: supersedes kb-retention-rumor

Correction: the Restore Drill Control passed for the archive in May; the slowdown did not breach it. Coverage extends to Orders Archive. The storage KB rumor is superseded.
Superseded statement: 'The May archive slowdown broke the Restore Drill Control.'
`Restore Drill Control -> PROTECTS -> Orders Archive` (supersedes kb-retention-rumor)
Supersedes: kb-retention-rumor.

## corr-004 - correction - 2026-06-10
Correction notice: supersedes kb-payout-rumor

Correction: Payout Release v2 did not cause Payout Delay Thursday. That release shipped in June; the incident ran in May. The ops KB note is superseded.
Superseded statement: 'Payout Release v2 caused Payout Delay Thursday.'
`Payout Delay Thursday -> !CAUSED_BY -> Payout Release v2` (supersedes kb-payout-rumor)
Supersedes: kb-payout-rumor.

## corr-005 - correction - 2026-09-25
Correction notice: supersedes kb-routes-rumor

Correction: Orchard Routes supplies route math only; it does not feed Ledger Mirror or any payment store. The routing KB slide note is superseded.
Superseded statement: 'Orchard Routes supplies the Ledger Mirror data set.'
`Orchard Routes -> !SUPPLIES -> Ledger Mirror` (supersedes kb-routes-rumor)
Supersedes: kb-routes-rumor.

## corr-006 - correction - 2026-08-24
Correction notice: supersedes kb-gateway-rumor

Correction: approval for Checkout Release v3 by Lin Mei was never withdrawn; it stands. The checkout KB gossip note is superseded.
Superseded statement: 'Approval for Checkout Release v3 was withdrawn in mid-August.'
`Lin Mei -> APPROVED -> Checkout Release v3` (supersedes kb-gateway-rumor)
Supersedes: kb-gateway-rumor.

## nr-walkthrough - narrative - 2026-06-05
Narrative memo: one order from portal to partner report

One order from portal to partner report: order state lands in the order record store once intake confirms it, the charge journal books the charge, the mirror copy feeds dashboards, Analytics ETL lifts the charge journal nightly into the lake, and Partner Portal reads the lake through the reporting surface.
Restates: `Orders Intake -> WRITES_TO -> Orders Primary`; `Payments Service -> WRITES_TO -> Ledger Primary`; `Ledger Primary -> REPLICATES_TO -> Ledger Mirror`; `Analytics ETL -> READS_FROM -> Ledger Primary`; `Analytics ETL -> WRITES_TO -> Analytics Lake`; `Partner Portal -> CALLS -> Reporting API`; `Reporting API -> READS_FROM -> Analytics Lake`.

## nr-floor - narrative - 2026-06-30
Narrative memo: how hub counts travel to the lake

How hub counts travel to the lake: vision scan events stream from the camera rail into the hub inventory, and Analytics ETL lifts the hub inventory sample stream nightly. Fleet Dispatch never reads orders directly; it trusts the hub inventory instead.
Restates: `Vision Events Store -> REPLICATES_TO -> Warehouse DB`; `Analytics ETL -> READS_FROM -> Warehouse DB`.

## nr-messages - narrative - 2026-07-04
Narrative memo: message retries without duplicates

Message retries without duplicates: the outbound message line accumulates retries with dedupe keys per milestone, DeltaWave Communications holds the transport throttle for the message line, and Omar Diaz owns retry caps on Notification Service, which writes the message line.
Restates: `Notification Service -> WRITES_TO -> Notification Queue`; `DeltaWave Communications -> SUPPLIES -> Notification Queue`.

## nr-settle - narrative - 2026-07-10
Narrative memo: courier settlement discipline

Courier settlement discipline: settlement batches for couriers queue in the Payout Queue until the retry rules land, Mara Okafor personally approved the settlement retry rules while owning the ledger schema gate, and Vaulttree Estate requires an audit trail on its payouts.
Restates: `Payout Service -> READS_FROM -> Payout Queue`; `Payout Service -> WRITES_TO -> Payout Queue`; `Mara Okafor -> APPROVED -> Payout Release v2`; `Vaulttree Estate -> REQUIRES -> Ledger Immutability Control`.

## nr-swarm - narrative - 2026-07-16
Narrative memo: fan-out adapter riders

Who rides the fan-out adapter: Payments Service reuses the Swarm API to reach vendor mapping services, Nimbus Routing composes turn-by-turn directions through the same adapter, and the adapter alone purges the van sample stream on 90-day windows.
Restates: `Payments Service -> CALLS -> Swarm API`; `Nimbus Routing -> CALLS -> Swarm API`; `Swarm API -> PURGES -> Fleet Telemetry Store`.

## nr-vendors - narrative - 2026-07-22
Narrative memo: how van routes get their traffic sense

Vendor fallback story: the primary mapping vendor feeds the normalized traffic snapshots, the fallback vendor joined after a degraded primary window, and both feed the same store that Fleet Dispatch reads for route assignment.
Restates: `Nimbus Maps -> SUPPLIES -> Route ETL Store`; `Orchard Routes -> SUPPLIES -> Route ETL Store`; `Fleet Dispatch -> READS_FROM -> Route ETL Store`.

## nr-lagprobe - narrative - 2026-07-28
Narrative memo: the lag probe question

Chain of one advisory question: Taro Kurosawa stands on-call for the read-only ledger replica; Piper review of September showed the lag probe shepherded by Payments Release v9 short-circuited an append; the probe idea arrived with Payments Release v9, which shipped into Payments Service.
Restates: `Taro Kurosawa -> ONCALL_FOR -> Ledger Mirror`; `Payments Release v9 -> SHIPS -> Payments Service`; `September Ledger Stall -> CAUSED_BY -> Payments Release v9`.

## nr-approvals - narrative - 2026-08-01
Narrative memo: who signed what

Restated approvals: Lin Mei approved both checkout cuts, the ledger append batching release went out under Mara Okafor, and Sofia Beltan approved both notification cuts.
Restates: `Lin Mei -> APPROVED -> Checkout Release v2`; `Lin Mei -> APPROVED -> Checkout Release v3`; `Mara Okafor -> APPROVED -> Payments Release v7`; `Sofia Beltan -> APPROVED -> Notification Release v6`; `Sofia Beltan -> APPROVED -> Notification Release v7`.

## summary-memo-sept - memo - 2026-09-30
Synthesis memo

Nimbusfield cross-team posture: the intake, payments and warehouse clusters each page through Core Storage controls.
The analytics lake is the only sanctioned place where charge journal, hub inventory and message data are compared side by side.
Every regulated customer needs evidence of the Isolation Control and, for payouts, the ledger audit line.

## summary-memo-aug - memo - 2026-08-30
Synthesis memo

August promo bursts touched three teams at once: intake through checkout, payments through the ledger mirror probe, and dispatch through nothing.
Notifications stayed quiet in the same window; only promo promotions enqueue messages.

## summary-memo-governance - memo - 2026-10-01
Synthesis memo

Governance synthesis: the Ledger Immutability Control and the Restore Drill Control both sit under Core Storage; the Launch Flag Gate belongs to intake; the Fraud Threshold Review belongs to payments.
Two controls protect databases only, two protect customer-facing services, and one protects both.

## summary-memo-negatives - memo - 2026-10-02
Synthesis memo

Negative evidence index: Payments Release v7 was cleared for Blue Monday; Payments Release v8 cleared twice; Warehouse Release v6 cleared for July Duplicate Labels; Orchard Routes cleared for October clock skew.
No record anywhere connects the Legacy Order Feeder to any 2026 incident; retired means retired.

## summary-memo-refusal - memo - 2026-10-03
Synthesis memo

Missing-link memo: nothing in the corpus connects the Solvex Gateway to routing math or geodata.
If a reader feels the urge to bridge payments and van routing through the gateway, the corpus asks them to refuse; the fan-out adapter is the only shared crossing.

## summary-memo-resolution - memo - 2026-10-04
Synthesis memo

Name-collision memo: the Legacy Order Feeder and Orders Intake both touched the Checkout API historically; Fraud Store and Ledger Mirror both ingest from ledger-side sources; Vision Events Store is the real scan archive.
Requests about 'the order thing that duplicates' resolve to the Legacy Order Feeder, never Orders Intake.

## summary-memo-milestones - memo - 2026-10-05
Synthesis memo

Milestone map: each 2026 month held one major incident through October, March through October.
May carried two: Payout Delay Thursday and the May Archive Slowdown.

## audit-001 - audit - 2026-08-22
Audit note: Ledger Primary

Annual retention finding: Ledger Primary archive policy fulfils the Harbour Audit retention scope; the Launch Flag Gate recorded as in place.
Auditor of record: Harbour Audit.
`Ledger Primary -> AUDITED_BY -> Harbour Audit`

## audit-002 - audit - 2026-07-15
Audit note: Payout Queue

Audit note: Payout Queue retention satisfied; no mis-scope found.
Auditor of record: Harbour Audit.
`Payout Queue -> AUDITED_BY -> Harbour Audit`

## audit-003 - audit - 2026-04-10
Audit note: Checkout Storefront

External pen test note: the checkout surface passed; findings closed before the August promo tests.
Auditor of record: Granite Peaks Consulting.
`Checkout Storefront -> AUDITED_BY -> Granite Peaks Consulting`

## audit-004 - audit - 2026-05-20
Audit note: Orders Primary

Audit note: restore drill evidence on the order store met scope; the Isolation Control documented.
Auditor of record: Harbour Audit.
`Orders Primary -> AUDITED_BY -> Harbour Audit`

## audit-005 - audit - 2026-06-25
Audit note: Warehouse DB

Audit note: hub inventory retention scope satisfied; scan-history sampling documented.
Auditor of record: Harbour Audit.
`Warehouse DB -> AUDITED_BY -> Harbour Audit`

## audit-006 - audit - 2026-06-15
Audit note: Payout Service

Audit note: settlement trails complete for the first half of the year; Vaulttree Estate findings closed in June.
Auditor of record: Harbour Audit.
`Payout Service -> AUDITED_BY -> Harbour Audit`

## audit-007 - audit - 2026-05-30
Audit note: Partner Portal

External pen test note: partner dashboard scope reviewed; session controls passed.
Auditor of record: Granite Peaks Consulting.
`Partner Portal -> AUDITED_BY -> Granite Peaks Consulting`

## audit-008 - audit - 2026-04-28
Audit note: Orders Archive

Audit note: retention cold store sampling passed; restore paths verified against Aurora Compute snapshots.
Auditor of record: Harbour Audit.
`Orders Archive -> AUDITED_BY -> Harbour Audit`

## audit-009 - audit - 2026-03-30
Audit note: Fraud Store

Audit note: feature store lineage documented; mirror-derived sampling is nightly only.
Auditor of record: Harbour Audit.
`Fraud Store -> AUDITED_BY -> Harbour Audit`

## rota-001 - rota - 2026-01-30
On-call rota: Ledger Mirror

Standing rota note: the pager targets the Ledger Mirror first, then Payments Service.
Named on-call: Taro Kurosawa.
`Taro Kurosawa -> ONCALL_FOR -> Ledger Mirror`

## rota-002 - rota - 2026-01-30
On-call rota: Vision Events Store

Standing rota note: the Vision Events Store pages the dispatch on-call within five minutes.
Named on-call: Ravi Mohan.
`Ravi Mohan -> ONCALL_FOR -> Vision Events Store`

## rota-003 - rota - 2026-01-30
On-call rota: Orders Primary

Standing rota note: the order store pages Core Storage for both replica and restore drills.
Named on-call: Celia Hague.
`Celia Hague -> ONCALL_FOR -> Orders Primary`

## rota-004 - rota - 2026-01-30
On-call rota: Notification Queue

Standing rota note: the Notification Queue pager respects dedupe key semantics before escalating.
Named on-call: Omar Diaz.
`Omar Diaz -> ONCALL_FOR -> Notification Queue`

## rota-005 - rota - 2026-01-30
On-call rota: Analytics Lake

Standing rota note: the lake pager owns partner filter warnings with Yuki.
Named on-call: Bogdan Traistman.
`Bogdan Traistman -> ONCALL_FOR -> Analytics Lake`

## rota-006 - rota - 2026-01-30
On-call rota: Fraud Store

Standing rota note: the Fraud Store pages the payments SRE for sampling checks.
Named on-call: Samir Hadzhi.
`Samir Hadzhi -> ONCALL_FOR -> Fraud Store`

## rota-007 - rota - 2026-01-30
On-call rota: Analytics ETL

Standing rota note: the ETL surfaces pager as data platform analyst.
Named on-call: Yuki Tanabe.
`Yuki Tanabe -> ONCALL_FOR -> Analytics ETL`

## rota-008 - rota - 2026-01-30
On-call rota: Pricing Engine

Standing rota note: the pricing pager escalates quote-band changes to intake leadership.
Named on-call: Lin Mei.
`Lin Mei -> ONCALL_FOR -> Pricing Engine`

## rota-009 - rota - 2026-01-30
On-call rota: Route ETL Store

Standing rota note: the route store pages the vendor feed owner first.
Named on-call: Jesse Moon.
`Jesse Moon -> ONCALL_FOR -> Route ETL Store`

## rota-010 - rota - 2026-01-30
On-call rota: Helpdesk Service

Standing rota note: the helpdesk pager pairs the care PM with the agent console owner.
Named on-call: Sofia Beltan.
`Sofia Beltan -> ONCALL_FOR -> Helpdesk Service`

## rota-011 - rota - 2026-02-15
On-call rota: Ledger Primary

Standing rota note: Core Storage owns append-failure pages on the ledger primary.
Named on-call: Celia Hague.
`Celia Hague -> ONCALL_FOR -> Ledger Primary`

## rota-012 - rota - 2026-02-15
On-call rota: Fleet Telemetry Store

Standing rota note: the telemetry store pages dispatch for purge-window checks.
Named on-call: Ravi Mohan.
`Ravi Mohan -> ONCALL_FOR -> Fleet Telemetry Store`

End of corpus.
