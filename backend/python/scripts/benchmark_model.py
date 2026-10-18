"""Nimbusfield Logistics - Graph RAG architecture fingerprint benchmark model.

Single source of truth for the fictional benchmark corpus, evaluation
questions and computed answer key. Rendering lives in generate_benchmark.py;
ingestion lives in publish_benchmark.py.

Honesty: the domain is fictional, labeled as a synthetic benchmark fixture,
and never presented as real operational history. Every fact is asserted in
code so the answer key can be computed, never guessed.
"""

from __future__ import annotations

from collections import defaultdict, deque

REVISION = "benchmark-2026-10-18"

# ---------------------------------------------------------------------------
# Entity registry
# ---------------------------------------------------------------------------
ENTITY_TYPES = ["Person", "Team", "Vendor", "Customer", "Service", "Api", "Database", "Release", "Incident", "Control"]
E: dict[str, tuple[str, str, str]] = {}

def ent(eid: str, etype: str, name: str, desc: str) -> str:
    assert eid not in E, f"duplicate entity {eid}"
    assert etype in ENTITY_TYPES, f"unknown type {etype}"
    E[eid] = (etype, name, desc)
    return eid

# Teams
T_INTAKE = ent("team:intake", "Team", "Order Intake Team", "Builds and operates the customer-facing order path.")
T_PAYMENTS = ent("team:payments", "Team", "Payments Team", "Runs charges, ledger writes and payout batches.")
T_DISPATCH = ent("team:dispatch", "Team", "Dispatch Team", "Owns routing, warehouse and fleet orchestration.")
T_SUPPORT = ent("team:care", "Team", "Care Platform Team", "Runs notifications, helpdesk and partner portals.")
T_DATA = ent("team:data", "Team", "Data Platform Team", "Runs the analytics lake and partner reporting surface.")
T_COREDB = ent("team:coredb", "Team", "Core Storage Team", "Runs primary transactional databases and replicas.")

# Order intake cluster
S_CHECKOUT = ent("service:checkout-storefront", "Service", "Checkout Storefront", "Web portal customers use to place parcel pickup orders.")
S_ORDERS = ent("service:orders-intake", "Service", "Orders Intake", "Turns accepted checkout sessions into durable parcel orders.")
S_PRICING = ent("service:pricing-engine", "Service", "Pricing Engine", "Quotes price bands and promotion effects for checkout.")
A_CHECKOUT = ent("api:checkout-api", "Api", "Checkout API", "Session-to-order transition surface.")
A_PROMO = ent("api:promo-api", "Api", "Promotions API", "Discount accounting endpoint of Orders Intake.")
A_PRICING = ent("api:pricing-api", "Api", "Pricing API", "Quote endpoint of the Pricing Engine.")
DB_ORDERS = ent("db:orders-primary", "Database", "Orders Primary", "Transactional store of record for parcel orders.")
DB_ORDERS_ARCH = ent("db:orders-archive", "Database", "Orders Archive", "Cold retention copy of completed orders; serves no live traffic.")
S_ORDERS_LEGACY = ent("service:orders-legacy-etl", "Service", "Legacy Order Feeder", "Deprecated feeder job that once duplicated intake writes.")
DB_LEDGER_MIRROR = ent("db:ledger-mirror", "Database", "Ledger Mirror", "Read-only ledger replica for finance dashboards.")

# Payments cluster
S_PAYMENTS = ent("service:payments", "Service", "Payments Service", "Charges the ledger once an order is confirmed.")
S_PAYOUT = ent("service:payouts", "Service", "Payout Service", "Batch settles courier and driver earnings.")
A_PAYMENTS = ent("api:payments-gateway-api", "Api", "Payments Gateway API", "Charge and refund surface of Payments Service.")
DB_LEDGER = ent("db:ledger-primary", "Database", "Ledger Primary", "Append-only ledger of customer charges and refunds.")
DB_FRAUD = ent("db:fraud-store", "Database", "Fraud Store", "Feature store used by fraud scoring jobs.")
DB_PAYOUT = ent("db:payout-queue", "Database", "Payout Queue", "Pending settlement queue for courier invoices.")

# Warehouse and fleet cluster
S_WAREHOUSE = ent("service:warehouse-mgmt", "Service", "Warehouse Management", "Tracks parcels, totes and racks inside sortation hubs.")
S_FLEET = ent("service:fleet-dispatch", "Service", "Fleet Dispatch", "Assigns routes, vans and courier stops each day.")
S_ROUTING = ent("service:nimbus-routing", "Service", "Nimbus Routing", "Composes turn-by-turn directions from vendor feeds.")
A_WAREHOUSE = ent("api:warehouse-api", "Api", "Warehouse API", "Scan-to-rack and load-event surface.")
A_DISPATCH = ent("api:dispatch-api", "Api", "Dispatch API", "Route assignment endpoint of Fleet Dispatch.")
A_SWARM = ent("api:swarm-api", "Api", "Swarm API", "Fan-out surface that dispatches to vendor mapping services.")
DB_VISION = ent("db:vision-events", "Database", "Vision Events Store", "Raw camera scan events from sortation lines.")
DB_TELEMETRY = ent("db:telemetry", "Database", "Fleet Telemetry Store", "Van position and temperature samples from runs.")
DB_WAREHOUSE = ent("db:warehouse-db", "Database", "Warehouse DB", "Hub inventory of totes and rack positions.")
DB_ROUTE = ent("db:route-etl", "Database", "Route ETL Store", "Normalized traffic snapshots ingested from vendors.")

# Support cluster
S_NOTIFY = ent("service:notify", "Service", "Notification Service", "Sends customer texts and emails at parcel milestones.")
S_HELPDESK = ent("service:helpdesk", "Service", "Helpdesk Service", "Agent console for parcel support cases.")
A_NOTIFY = ent("api:notify-api", "Api", "Notification API", "Template send endpoint of Notification Service.")
A_HELPDESK = ent("api:helpdesk-api", "Api", "Helpdesk API", "Case create and update surface of Helpdesk.")
DB_QUEUE = ent("db:notify-queue", "Database", "Notification Queue", "Outbound message queue with retry bookkeeping.")

# Analytics bridge cluster
S_ETL = ent("service:analytics-etl", "Service", "Analytics ETL", "Nightly extraction from operational stores into the lake.")
S_PARTNER = ent("service:partner-portal", "Service", "Partner Portal", "Dashboards surfaced to enterprise customers.")
A_REPORT = ent("api:reporting-api", "Api", "Reporting API", "Read endpoint over the lake exposed by Analytics ETL.")
DB_LAKE = ent("db:analytics-lake", "Database", "Analytics Lake", "Columnar lake of nightly snapshots across clusters.")

# Shared registries / controls
C_IMMUTABLE = ent("control:ledger-immutability", "Control", "Ledger Immutability Control", "Forbids updates and deletes on ledger tables; requires append-only history.")
C_FLAG = ent("control:launch-flag-gate", "Control", "Launch Flag Gate", "Requires a ramped feature flag on high-traffic order paths.")
C_ISOLATION = ent("control:customer-isolation", "Control", "Isolation Control", "Enforces per-customer row scoping on shared stores.")
C_FRAUD = ent("control:fraud-threshold-review", "Control", "Fraud Threshold Review", "Weekly review of fraud cutoffs before promotions run.")
C_VENDOR_SCAN = ent("control:vendor-vuln-scan", "Control", "Vendor Vulnerability Scan", "Vendor dependencies must pass the monthly scan gate.")
C_BACKUP_DRILL = ent("control:backup-restore-drill", "Control", "Restore Drill Control", "Quarterly restore proof for every transactional store.")
C_ONCALL = ent("control:oncall-escalation", "Control", "On-call Escalation Control", "Incidents must page a named on-call within five minutes.")
C_PENTEST = ent("control:pen-test-cycle", "Control", "Annual Penetration Test", "Yearly external penetration test of customer surfaces.")

# Releases
R_CHECKOUT_V2 = ent("release:checkout-v2", "Release", "Checkout Release v2", "Added promo stacking to checkout sessions.")
R_CHECKOUT_V3 = ent("release:checkout-v3", "Release", "Checkout Release v3", "Expanded quote caching; promoted promo fail-open behavior.")
R_ORDERS_V9 = ent("release:orders-v9", "Release", "Orders Release v9", "Idempotency keys across intake writes.")
R_PAYMENTS_V7 = ent("release:payments-v7", "Release", "Payments Release v7", "Ledger append batching with refund dedupe.")
R_PAYMENTS_V8 = ent("release:payments-v8", "Release", "Payments Release v8", "Split payout scheduling out of the charge path.")
R_WAREHOUSE_V6 = ent("release:warehouse-v6", "Release", "Warehouse Release v6", "Vision scan early-warning thresholds rewrite.")
R_FLEET_V5 = ent("release:fleet-v5", "Release", "Fleet Release v5", "Clock-skew guard on dispatch assignment.")
R_NOTIFY_V6 = ent("release:notify-v6", "Release", "Notification Release v6", "Queue backpressure caps with retry limits.")
R_ETL_V12 = ent("release:etl-v12", "Release", "ETL Release v12", "Lake compaction changes and partner filters.")
R_HELPDESK_V3 = ent("release:helpdesk-v3", "Release", "Helpdesk Release v3", "Case linking across parcels and orders.")
R_PAYOUT_V2 = ent("release:payout-v2", "Release", "Payout Release v2", "Settlement retry scheduling rules.")
R_ORDERS_V10 = ent("release:orders-v10", "Release", "Orders Release v10", "Quota guard for intake burst writes.")
R_NOTIFY_V7 = ent("release:notify-v7", "Release", "Notification Release v7", "Template dedupe for milestone repeats.")
R_PAYMENTS_V9 = ent("release:payments-v9", "Release", "Payments Release v9", "Ledger mirror lag probe across dashboards.")

# Incidents (all fictional)
I_BLUE = ent("incident:blue-monday", "Incident", "Blue Monday Ledger Stall", "2026-03-09 ledger write stalls during morning peaks.")
I_OVERCHARGE = ent("incident:overcharge-run", "Incident", "April Overcharge Run", "2026-04-14 duplicate charge rows during promo tests.")
I_PAYOUT_DELAY = ent("incident:payout-delay", "Incident", "Payout Delay Thursday", "2026-05-14 courier settlements delayed.")
I_ETL_GAPS = ent("incident:etl-gaps", "Incident", "June Lake Gaps", "2026-06-11 nightly loads skipped partitions in the lake.")
I_NOTIFY_FLOOD = ent("incident:notify-flood", "Incident", "June Notification Flood", "2026-06-30 retry storm produced duplicate texts.")
I_LABELS = ent("incident:duplicate-labels", "Incident", "July Duplicate Labels", "2026-07-21 vision scans matched two totes to one carton.")
I_GATEWAY = ent("incident:gateway-403", "Incident", "August Gateway 403 Surge", "2026-08-05 checkout bursts of 403 through the gateway.")
I_LEDGER_STALL = ent("incident:ledger-stall", "Incident", "September Ledger Stall", "2026-09-02 a replica failed over mid-append.")
I_CLOCK = ent("incident:dispatch-clock-slip", "Incident", "October Dispatch Clock Slip", "2026-10-06 route assignments shifted by skew.")
I_ARCHIVE = ent("incident:archive-slowdown", "Incident", "May Archive Slowdown", "2026-05-28 retention copy scans slowed order reads.")

# People
P_MARA = ent("person:mara-okafor", "Person", "Mara Okafor", "Payments Team lead; runs ledger architecture reviews.")
P_RAVI = ent("person:ravi-mohan", "Person", "Ravi Mohan", "Dispatch SRE; incident commander for hub pages.")
P_SOFIA = ent("person:sofia-beltan", "Person", "Sofia Beltan", "Care Platform PM; owns customer comms standards.")
P_BOGDAN = ent("person:bogdan-traistman", "Person", "Bogdan Traistman", "Data Platform lead; holds the lake contract.")
P_LIN = ent("person:lin-mei", "Person", "Lin Mei", "Intake Team engineering manager; approves checkout releases.")
P_TARO = ent("person:taro-kurosawa", "Person", "Taro Kurosawa", "Payments SRE; on-call for ledger and payouts.")
P_CELIA = ent("person:celia-hague", "Person", "Celia Hague", "Core Storage DBA; runs replication and restore drills.")
P_JESSE = ent("person:jesse-moon", "Person", "Jesse Moon", "Dispatch engineer; vendor feed integrations.")
P_NILA = ent("person:nila-venkat", "Person", "Nila Venkat", "Intake engineer; checkout idempotency work.")
P_OMAR = ent("person:omar-diaz", "Person", "Omar Diaz", "Care Platform engineer; retry caps for notifications.")
P_YUKI = ent("person:yuki-tanabe", "Person", "Yuki Tanabe", "Data analyst; partner filters and lake quality.")
P_SAMIR = ent("person:samir-hadzhi", "Person", "Samir Hadzhi", "Payments engineer; gateway vendor checks.")

# Vendors and customers
V_AURORA = ent("vendor:aurora-compute", "Vendor", "Aurora Compute", "Managed hosting for operational databases.")
V_GRANITE = ent("vendor:granite-peaks", "Vendor", "Granite Peaks Consulting", "Runs the annual external penetration test.")
V_SOLVEX = ent("vendor:solvex-gateway", "Vendor", "Solvex Gateway", "Card acquiring gateway behind Payments Service.")
V_ORCHARD = ent("vendor:orchard-routes", "Vendor", "Orchard Routes", "Secondary geodata provider; fallback traffic feed.")
V_DELTAWAVE = ent("vendor:deltawave-comms", "Vendor", "DeltaWave Communications", "SMS and email transport for notifications.")
V_HARBOUR = ent("vendor:harbour-audit", "Vendor", "Harbour Audit", "Industry bench auditor covering ledger archive retention.")
V_PINEFORK = ent("vendor:pinefork-hardware", "Vendor", "Pinefork Hardware", "Sortation line cameras and scan hardware supplier.")
V_NIMBUS = ent("vendor:nimbus-maps", "Vendor", "Nimbus Maps", "Primary geodata and traffic provider for route ETA.")

CUST_ACME = ent("customer:acme-retail", "Customer", "Acme Retail", "Enterprise retailer with order-acceptance latency SLA.")
CUST_WINDWARD = ent("customer:windward-grocers", "Customer", "Windward Grocers", "Perishables chain requiring telemetry freshness.")
CUST_LAKESIDE = ent("customer:lakeside-pharmacy", "Customer", "Lakeside Pharmacy", "Regulated deliveries; needs isolation evidence.")
CUST_SOLSTICE = ent("customer:solstice-media", "Customer", "Solstice Media", "Marketing parcels, promo stacking in August tests.")
CUST_VAULTTREE = ent("customer:vaulttree-estate", "Customer", "Vaulttree Estate", "High-value shipments; demands payout audit trail.")
CUST_NORDHOLLOW = ent("customer:nordhollow-books", "Customer", "Nordhollow Books", "Standard delivery tiers across the north region.")
CUST_CINDERGATE = ent("customer:cindergate-supply", "Customer", "Cindergate Supply", "Industrial goods; scan-heavy hubs.")
CUST_ORCHID = ent("customer:orchid-lake-boutique", "Customer", "Orchid Lake Boutique", "Seasonal drops with June marketing moments.")
CUST_TRAMLINE = ent("customer:tramline-couriers", "Customer", "Tramline Couriers", "Aggregates courier settlements through payouts.")
CUST_GREENFIELD = ent("customer:greenfield-care", "Customer", "Greenfield Care", "Pharmacy partner requiring notified templates.")

assert len(E) == 103, f"expected 103 entities, got {len(E)}"

# ---------------------------------------------------------------------------
# Facts and records
# ---------------------------------------------------------------------------
FACTS: list[dict] = []   # {subject, predicate, object, origin, polarity, note}
RECORDS: list[dict] = [] # {id, kind, stamp, title, prose, owned, links}

def fact(sub: str, pred: str, obj: str, origin: str, polarity: str = "affirmed", note: str = "") -> int:
    assert sub in E and obj in E, f"unknown endpoint {sub} or {obj}"
    assert polarity, "polarity required, use negated for explicit negative evidence"
    FACTS.append({"subject": sub, "predicate": pred, "object": obj, "origin": origin, "polarity": polarity, "note": note})
    return len(FACTS) - 1

def facts_for(sub: str, pred: str, obj: str) -> list[int]:
    return [i for i, f in enumerate(FACTS) if f["subject"] == sub and f["predicate"] == pred and f["object"] == obj]

PRED_DOC = "Every fact line appears as `SUBJECT -> PREDICATE -> OBJECT`. All edges are directed exactly as written."

PREDICATES = [
    ("MEMBER_OF", "person -> team"),
    ("OWNS", "team -> service"),
    ("CALLS", "service -> api"),
    ("EXPOSES", "service -> api"),
    ("READS_FROM", "service|api -> database"),
    ("WRITES_TO", "service|api -> database"),
    ("DELETES", "service -> database"),
    ("PURGES", "api|service -> database"),
    ("REPLICATES_TO", "database -> database"),
    ("SHIPS", "release -> service"),
    ("CAUSED_BY", "incident -> release; negated form records explicit clearance"),
    ("AFFECTED", "incident -> service"),
    ("AFFECTED_D", "incident -> database"),
    ("ALERTED", "incident -> service|database"),
    ("RCA_BY", "person -> incident"),
    ("APPROVED", "person -> release"),
    ("INTRODUCED", "release -> api|database"),
    ("SUPPLIES", "vendor -> service|api|database"),
    ("USES", "customer -> service"),
    ("REQUIRES", "customer -> control"),
    ("HELD_BY", "customer -> service"),
    ("PROTECTS", "control -> service|database"),
    ("GOVERNED_BY", "control -> team"),
    ("ONCALL_FOR", "person -> service|database"),
    ("AUDITED_BY", "audited target -> vendor auditor"),
]

def record(rec_id: str, kind: str, stamp: str, title: str, prose: list[str], owned: list[int] | None = None, links: dict | None = None) -> dict:
    for r in RECORDS:
        assert r["id"] != rec_id, f"duplicate record {rec_id}"
    item = {"id": rec_id, "kind": kind, "stamp": stamp, "title": title, "prose": prose, "owned": owned or [], "links": links or {}}
    RECORDS.append(item)
    return item

RID_COUNTS: dict[str, int] = defaultdict(int)
def rid(prefix: str) -> str:
    RID_COUNTS[prefix] += 1
    return f"{prefix}-{RID_COUNTS[prefix]:03d}"

# profile builders ---------------------------------------------------------
def svc_profile(svc: str, owner: str, calls: list[str], exposes: list[str], reads: list[str], writes: list[str], deletes: list[str], deal: str, traps: list[str] = []):
    ids = []
    ids.append(fact(owner, "OWNS", svc, "pending"))
    for a in calls:
        ids.append(fact(svc, "CALLS", a, "pending"))
    for a in exposes:
        ids.append(fact(svc, "EXPOSES", a, "pending"))
    for d in reads:
        ids.append(fact(svc, "READS_FROM", d, "pending"))
    for d in writes:
        ids.append(fact(svc, "WRITES_TO", d, "pending"))
    for d in deletes:
        ids.append(fact(svc, "DELETES", d, "pending"))
    for l in (owner, *calls, *exposes, *reads, *writes, *deletes):
        assert l in E, f"{svc} references unknown endpoint {l}"
    sentences = [f"Profile record for {E[svc][1]} ({svc})."]
    for group, label in ((calls, "calls"), (exposes, "publicly exposes"), (reads, "reads"), (writes, "owns writes to"), (deletes, "runs its legacy purge routine on")):
        if group:
            names = ", ".join(E[g][1] for g in group)
            sentences.append(f"It {label} {names}.")
    for t in traps:
        sentences.append("Care note: " + t)
    sentences.append(deal)
    r = record(rid("svc"), "profile", "2026-01-15", "Service profile: " + E[svc][1], sentences, owned=ids)
    for i in ids:
        FACTS[i]["origin"] = r["id"]
    return r

def api_spec(api: str, host: str, reads: list[str], writes: list[str], purges: list[str] = [], note: str = ""):
    ids = []
    if api not in [f["object"] for f in FACTS if f["predicate"] == "EXPOSES" and f["object"] == api] or True:
        ids.append(fact(host, "EXPOSES", api, "pending"))
    for d in reads:
        ids.append(fact(api, "READS_FROM", d, "pending"))
    for d in writes:
        ids.append(fact(api, "WRITES_TO", d, "pending"))
    for d in purges:
        ids.append(fact(api, "PURGES", d, "pending"))
    sentences = [f"Spec record for {E[api][1]} ({api}).", f"Hosted by {E[host][1]}."]
    if reads:
        sentences.append("Reads " + ", ".join(E[d][1] for d in reads) + ".")
    if writes:
        sentences.append("Writes " + ", ".join(E[d][1] for d in writes) + " under transaction scope.")
    for d in purges:
        sentences.append(f"Purge responsibility against {E[d][1]} runs through this endpoint only.")
    if note:
        sentences.append("Care note: " + note)
    r = record(rid("api"), "profile", "2026-01-16", "API spec: " + E[api][1], sentences, owned=ids)
    for i in ids:
        FACTS[i]["origin"] = r["id"]
    return r

def db_reg(db: str, replicates: list[str], role: str, traps: list[str] = []):
    ids = [fact(db, "REPLICATES_TO", t, "pending") for t in replicates]
    for t in replicates:
        assert t in E, f"{db} references unknown target {t}"
    sentences = [f"Registry record for {E[db][1]} ({db})."]
    if replicates:
        sentences.append("Replicates forward into: " + ", ".join(E[t][1] for t in replicates) + ".")
    sentences.append(role)
    for t in traps:
        sentences.append("Disambiguation note: " + t)
    r = record(rid("db"), "profile", "2026-01-17", "Database registry: " + E[db][1], sentences, owned=ids)
    for i in ids:
        FACTS[i]["origin"] = r["id"]
    return r

def release_note(rel: str, ships: list[str], approved: str, window: str, extra_facts: list[tuple[str, str, str]] = [], extra_prose_text: str = ""):
    ids = []
    for s in ships:
        ids.append(fact(rel, "SHIPS", s, "pending"))
    ids.append(fact(approved, "APPROVED", rel, "pending"))
    for sub, p, obj in extra_facts:
        ids.append(fact(sub, p, obj, "pending"))
    sentences = [f"Release record for {E[rel][1]} ({rel})."]
    if ships:
        sentences.append("Shipped changes into: " + ", ".join(E[s][1] for s in ships) + ".")
    sentences.append(f"Approved by {E[approved][1]}; available in the {window} window.")
    for sub, p, obj in extra_facts:
        sentences.append(f"Side fact: {E[sub][1]} {p.lower().replace('_', ' ')} {E[obj][1]}.")
    if extra_prose_text:
        sentences.append(extra_prose_text)
    r = record(rid("rel"), "profile", "2026-01-18", "Release note: " + E[rel][1], sentences, owned=ids)
    for i in ids:
        FACTS[i]["origin"] = r["id"]
    return r

def incident_rec(inc: str, stamp: str, commander: str, affected_services: list[str], affected_dbs: list[str], caused_by: tuple[str, str] | None, cleared_releases: list[tuple[str, str]] = [], symptoms: str = "", mentions: list[str] = []):
    ids = []
    for s in affected_services:
        ids.append(fact(inc, "AFFECTED", s, "pending"))
    for d in affected_dbs:
        ids.append(fact(inc, "AFFECTED_D", d, "pending"))
    for a in affected_services + affected_dbs:
        ids.append(fact(inc, "ALERTED", a, "pending"))
    ids.append(fact(commander, "RCA_BY", inc, "pending"))
    if caused_by is not None:
        rel, how = caused_by
        ids.append(fact(inc, "CAUSED_BY", rel, "pending", note=how))
    for rel, note in cleared_releases:
        ids.append(fact(inc, "CAUSED_BY", rel, "pending", polarity="negated", note=note))
    sentences = [f"Incident record {E[inc][1]} ({inc}); opened {stamp}."]
    sentences.append("Service impact: " + (", ".join(E[s][1] for s in affected_services) or "none") + ".")
    if affected_dbs:
        sentences.append("Store impact: " + ", ".join(E[d][1] for d in affected_dbs) + ".")
    sentences.append(f"Incident commander: {E[commander][1]} (the on-call escalation rule requires a named responder within five minutes).")
    if caused_by:
        rel, how = caused_by
        sentences.append(f"Preliminary attribution: {E[rel][1]} — {how}.")
    for rel, note in cleared_releases:
        sentences.append(f"Negative evidence: investigation cleared {E[rel][1]}; it did not cause this incident ({note}).")
    if symptoms:
        sentences.append("Customer-visible symptoms: " + symptoms)
    for m in mentions:
        sentences.append("Cross-reference: " + m)
    r = record(rid("inc"), "profile", stamp[:10], "Incident record: " + E[inc][1], sentences, owned=ids)
    for i in ids:
        FACTS[i]["origin"] = r["id"]
    return r

def control_rec(ctrl: str, protects: list[str], governed: str, note: str):
    ids = [fact(ctrl, "PROTECTS", s, "pending") for s in protects]
    ids.append(fact(ctrl, "GOVERNED_BY", governed, "pending"))
    sentences = [f"Control record for {E[ctrl][1]} ({ctrl})."]
    if protects:
        sentences.append("Protects: " + ", ".join(E[s][1] for s in protects) + ".")
    sentences.append(f"Governed by {E[governed][1]}.")
    sentences.append(note)
    r = record(rid("ctl"), "profile", "2026-01-20", "Control record: " + E[ctrl][1], sentences, owned=ids)
    for i in ids:
        FACTS[i]["origin"] = r["id"]
    return r

def vendor_rec(v: str, supplies: list[str], note: str, extra: list[tuple[str, str, str]] = []):
    ids = [fact(v, "SUPPLIES", s, "pending") for s in supplies]
    for sub, p, obj in extra:
        ids.append(fact(sub, p, obj, "pending"))
    sentences = [f"Vendor record for {E[v][1]} ({v})."]
    if supplies:
        sentences.append("Supplies: " + ", ".join(E[s][1] for s in supplies) + ".")
    sentences.append(note)
    for sub, p, obj in extra:
        sentences.append(f"Also stated here: {E[sub][1]} {p.lower().replace('_', ' ')} {E[obj][1]}.")
    r = record(rid("vend"), "profile", "2026-01-22", "Vendor record: " + E[v][1], sentences, owned=ids)
    for i in ids:
        FACTS[i]["origin"] = r["id"]
    return r

def customer_rec(c: str, uses: list[str], requires: list[str], holds: list[str] = [], notes: str = "", mentions: list[str] = []):
    ids = [fact(c, "USES", s, "pending") for s in uses]
    ids += [fact(c, "REQUIRES", ct, "pending") for ct in requires]
    ids += [fact(c, "HELD_BY", s, "pending") for s in holds]
    sentences = [f"Customer entitlement record for {E[c][1]} ({c})."]
    if uses:
        sentences.append("Uses: " + ", ".join(E[s][1] for s in uses) + ".")
    if requires:
        sentences.append("Requires controls: " + ", ".join(E[r][1] for r in requires) + ".")
    if holds:
        sentences.append("Held under high-priority thresholds with: " + ", ".join(E[s][1] for s in holds) + ".")
    if notes:
        sentences.append(notes)
    for m in mentions:
        sentences.append("Cross-reference: " + m)
    r = record(rid("cust"), "profile", "2026-01-25", "Customer record: " + E[c][1], sentences, owned=ids)
    for i in ids:
        FACTS[i]["origin"] = r["id"]
    return r

def team_page(t: str, members: list[str], notes: str = ""):
    ids = [fact(p, "MEMBER_OF", t, "pending") for p in members]
    sentences = [f"Team page for {E[t][1]} ({t}).", "Members: " + ", ".join(E[p][1] for p in members) + "."]
    if notes:
        sentences.append(notes)
    r = record(rid("team"), "profile", "2026-01-14", "Team page: " + E[t][1], sentences, owned=ids)
    for i in ids:
        FACTS[i]["origin"] = r["id"]
    return r

def person_card(p: str, teams: list[str], oncall: list[str], note: str = ""):
    ids = [fact(p, "MEMBER_OF", t, "pending") for t in teams]
    ids += [fact(p, "ONCALL_FOR", s, "pending") for s in oncall]
    names = " and ".join(E[t][1] for t in teams)
    sentences = [f"Directory card for {E[p][1]} ({p}).", f"Member of {names}."]
    if oncall:
        sentences.append("Standing on-call rota: " + ", ".join(E[s][1] for s in oncall) + ".")
    if note:
        sentences.append(note)
    r = record(rid("person"), "profile", "2026-01-13", "Person card: " + E[p][1], sentences, owned=ids)
    for i in ids:
        FACTS[i]["origin"] = r["id"]
    return r

def postmortem(inc: str, stamp: str, commander: str, caused_by: tuple[str, str] | None, cleared: list[tuple[str, str]] = [], highlights: list[str] = [], notes: str = ""):
    ids = [fact(commander, "RCA_BY", inc, "pending")]
    if caused_by is not None:
        rel, how = caused_by
        ids.append(fact(inc, "CAUSED_BY", rel, "pending", note=how))
    for rel, note in cleared:
        ids.append(fact(inc, "CAUSED_BY", rel, "pending", polarity="negated", note=note))
    sentences = ["Postmortem for " + E[inc][1] + f" ({inc}); finalized {stamp}; commander {E[commander][1]}."]
    if caused_by:
        rel, how = caused_by
        sentences.append(f"Proven causal path: {E[rel][1]} — {how}.")
    for rel, note in cleared:
        sentences.append(f"Explicit negative evidence: {E[rel][1]} was cleared by investigation; it did not cause this incident ({note}).")
    for h in highlights:
        sentences.append("Highlight: " + h)
    if notes:
        sentences.append(notes)
    r = record(rid("postmortem"), "postmortem", stamp[:10], "Postmortem: " + E[inc][1], sentences, owned=ids)
    for i in ids:
        FACTS[i]["origin"] = r["id"]
    return r

def correction(old_rec_id: str, sub: str, pred: str, obj: str, polarity: str, corrected_text: str, superseded_text: str, stamp: str):
    assert any(r["id"] == old_rec_id for r in RECORDS), f"correction references unknown record {old_rec_id}"
    idx = fact(sub, pred, obj, "pending", polarity=polarity, note="supersedes " + old_rec_id)
    corrected = corrected_text
    superseded = superseded_text
    if not superseded.startswith("Superseded statement:"):
        superseded = "Superseded statement: " + superseded_text
    r = record(rid("corr"), "correction", stamp[:10], f"Correction notice: supersedes {old_rec_id}", [corrected, superseded], owned=[idx], links={"supersedes": old_rec_id})
    FACTS[idx]["origin"] = r["id"]
    return r

def kb_note(kb_id: str, stamp: str, title: str, lines: list[str]):
    return record(kb_id, "kb", stamp[:10], title, lines)

def narrative(stamp: str, storyline: list[str], restates: list[int],	record_id: str | None = None, title_prefix: str = "Narrative memo"):
    r = record(record_id or rid("nr"), "narrative", stamp[:10], title_prefix, storyline, links={"restates": restates})
    return r

def memo(stamp: str, storyline: list[str], notes_id: str | None = None):
    return record(notes_id or rid("memo"), "memo", stamp[:10], "Synthesis memo", storyline)

def audit_rec(target: str, stamp: str, auditor: str, line: str):
    idx = fact(target, "AUDITED_BY", auditor, "pending")
    r = record(rid("audit"), "audit", stamp[:10], "Audit note: " + E[target][1], [line, f"Auditor of record: {E[auditor][1]}."], owned=[idx])
    FACTS[idx]["origin"] = r["id"]
    return r

def rota_rec(person: str, svc: str, stamp: str, note: str):
    idx = fact(person, "ONCALL_FOR", svc, "pending")
    r = record(rid("rota"), "rota", stamp[:10], f"On-call rota: {E[svc][1]}", [note, f"Named on-call: {E[person][1]}."], owned=[idx])
    FACTS[idx]["origin"] = r["id"]
    return r

# =============================================================================
# Authoring. 103 entities across five clusters.
# =============================================================================

# --- Teams and people
team_page(T_INTAKE, [P_LIN, P_NILA], notes="Charter note: owns the order-acceptance path only; does not own charges.")
team_page(T_PAYMENTS, [P_MARA, P_TARO, P_SAMIR], notes="Charter note: owns charging, ledger and payouts; does not own intake sessions.")
team_page(T_DISPATCH, [P_RAVI, P_JESSE], notes="Charter note: hub and van routing; does not own customer messages.")
team_page(T_SUPPORT, [P_SOFIA, P_OMAR], notes="Charter note: notification and helpdesk; no order-state ownership.")
team_page(T_DATA, [P_BOGDAN, P_YUKI], notes="Charter note: nightly lake copies and the fan-out reporting surface.")
team_page(T_COREDB, [P_CELIA], notes="Charter note: database primaries and replicas only.")

person_card(P_MARA, [T_PAYMENTS], [S_PAYMENTS], note="Standing note: personal sign-off is the approval gate for ledger schema changes.")
person_card(P_RAVI, [T_DISPATCH], [S_WAREHOUSE, S_FLEET], note="Standing note: leads hub incident command; pages the warehouse rota.")
person_card(P_SOFIA, [T_SUPPORT], [], note="Standing note: templates customer comms; requests block write access to customer PII.")
person_card(P_BOGDAN, [T_DATA], [S_ETL], note="Standing note: owns the partner data contract; must clear partner filters with Yuki.")
person_card(P_LIN, [T_INTAKE], [S_ORDERS, S_CHECKOUT], note="Standing note: approvals for checkout releases only after flag-gate evidence.")
person_card(P_TARO, [T_PAYMENTS], [DB_LEDGER_MIRROR, S_PAYOUT], note="Standing note: primary pager for ledger mirror and payouts.")
person_card(P_CELIA, [T_COREDB], [DB_ORDERS], note="Standing note: runs restore drills on every transactional store.")
person_card(P_JESSE, [T_DISPATCH], [], note="Standing note: integrates vendor traffic feeds; owns the fallback provider switch.")
person_card(P_NILA, [T_INTAKE], [S_PRICING], note="Standing note: builds idempotency keys for intake.")
person_card(P_OMAR, [T_SUPPORT], [S_NOTIFY], note="Standing note: owns retry caps and dedupe keys on notifications.")
person_card(P_YUKI, [T_DATA], [], note="Standing note: quality of lake snapshots; partner filter co-owner.")
person_card(P_SAMIR, [T_PAYMENTS], [], note="Standing note: gateway vendor checks and fraud thresholds.")

# --- Order intake cluster
svc_profile(S_CHECKOUT, T_INTAKE, calls=[A_CHECKOUT], exposes=[], reads=[DB_ORDERS], writes=[], deletes=[], deal="Web portal only; never writes on its own.")
svc_profile(S_ORDERS, T_INTAKE, calls=[], exposes=[A_CHECKOUT, A_PROMO], reads=[], writes=[DB_ORDERS], deletes=[DB_ORDERS_ARCH], deal="Durable order state machine; idempotency keys keep retries safe.", traps=["Do not confuse with the Legacy Order Feeder, which duplicated intake writes and was retired."])
svc_profile(S_PRICING, T_INTAKE, calls=[], exposes=[A_PRICING], reads=[DB_ORDERS_ARCH], writes=[], deletes=[], deal="Quote bands with fail-open behavior; also reads the archive for promo history.")
svc_profile(S_ORDERS_LEGACY, T_INTAKE, calls=[], exposes=[A_CHECKOUT], reads=[DB_ORDERS_ARCH], writes=[], deletes=[], deal="Retired history-aware feeder; reads only, writes nothing new. It once shared the Checkout API with Orders Intake.")
api_spec(A_CHECKOUT, S_ORDERS, reads=[DB_ORDERS], writes=[])
api_spec(A_PROMO, S_ORDERS, reads=[DB_ORDERS], writes=[])
api_spec(A_PRICING, S_PRICING, reads=[DB_ORDERS], writes=[])
db_reg(DB_ORDERS, [DB_ORDERS_ARCH], role="Store of record; immutable primary for orders.")
db_reg(DB_ORDERS_ARCH, [], role="Offline retention only; never queried in live order paths.", traps=["Name overlap trick: the Vision Events Store also gets called an archive in marketing decks; only Orders Archive copies orders."])
db_reg(DB_LEDGER_MIRROR, [], role="Read replica for finance dashboards; not written by charge paths.")

# --- Payments cluster
svc_profile(S_PAYMENTS, T_PAYMENTS, calls=[A_CHECKOUT, A_WAREHOUSE, A_SWARM], exposes=[A_PAYMENTS], reads=[], writes=[DB_LEDGER], deletes=[], deal="Confirms intake through the checkout surface, then charges once.", traps=["Never writes Orders Primary; ledger persistence only."])
svc_profile(S_PAYOUT, T_PAYMENTS, calls=[], exposes=[], reads=[DB_PAYOUT], writes=[DB_PAYOUT], deletes=[], deal="Settles courier days with batch retry rules.")
api_spec(A_PAYMENTS, S_PAYMENTS, reads=[], writes=[DB_LEDGER])
db_reg(DB_LEDGER, [DB_LEDGER_MIRROR], role="Append-only ledger; the Ledger Immutability Control forbids in-place updates.")
db_reg(DB_FRAUD, [], role="Feature store built from ledger mirrors by nightly jobs.", traps=["Name pairing caution: Fraud Store is not a mirror of Orders Primary."])
db_reg(DB_PAYOUT, [], role="Settlement queue; head-of-line blocking caused an incident here.", traps=["Do not confuse with Ledger Mirror; the payout queue is write input, the ledger mirror is read output."])

# --- Warehouse and fleet cluster
svc_profile(S_WAREHOUSE, T_DISPATCH, calls=[], exposes=[A_WAREHOUSE], reads=[], writes=[DB_WAREHOUSE], deletes=[], deal="Tracks parcel totes inside hubs.")
svc_profile(S_FLEET, T_DISPATCH, calls=[A_WAREHOUSE], exposes=[A_SWARM], reads=[DB_ROUTE], writes=[DB_TELEMETRY], deletes=[], deal="Route assignment with vendor traffic feeds.", traps=["Never queries Orders Primary; only uses warehouse scan events and vendor routes."])
svc_profile(S_ROUTING, T_DISPATCH, calls=[A_SWARM], exposes=[], reads=[DB_ROUTE], writes=[], deletes=[], deal="Turn-by-turn engine composed from vendors and internal traffic math.")
api_spec(A_WAREHOUSE, S_WAREHOUSE, reads=[], writes=[DB_VISION])
api_spec(A_DISPATCH, S_FLEET, reads=[DB_ROUTE], writes=[])
api_spec(A_SWARM, S_FLEET, reads=[], writes=[], note="Fan-out adapter. Payments Service reuses it to reach vendor mapping services.", purges=[DB_TELEMETRY])
db_reg(DB_VISION, [DB_WAREHOUSE], role="Raw scan events; feeds nightly tote reconciliation into the hub inventory store.")
db_reg(DB_TELEMETRY, [], role="Van samples; purged on 90-day windows by the Swarm API.", traps=["Never used as a ledger mirror; unrelated to charge paths."])
db_reg(DB_WAREHOUSE, [], role="Hub inventory of totes and rack positions; fed by vision event ingest.")

# --- Support cluster
svc_profile(S_NOTIFY, T_SUPPORT, calls=[], exposes=[A_NOTIFY], reads=[], writes=[DB_QUEUE], deletes=[], deal="Milestone texts and emails with strict dedupe keys.")
svc_profile(S_HELPDESK, T_SUPPORT, calls=[A_NOTIFY], exposes=[A_HELPDESK], reads=[DB_ORDERS], writes=[], deletes=[], deal="Agent console; links cases to parcels and orders.")
api_spec(A_NOTIFY, S_NOTIFY, reads=[], writes=[DB_QUEUE])
api_spec(A_HELPDESK, S_HELPDESK, reads=[DB_ORDERS], writes=[])
db_reg(DB_QUEUE, [], role="Outbound queue; scoped keys keep milestone repeats unique.")

# --- Analytics bridge cluster
svc_profile(S_ETL, T_DATA, calls=[], exposes=[A_REPORT], reads=[DB_LEDGER, DB_WAREHOUSE, DB_TELEMETRY, DB_QUEUE], writes=[DB_LAKE], deletes=[], deal="Nightly extraction into the lake; the bridge across intake, payments, warehouse and support clusters. Note: the lake never ingests Orders Primary; intake history stays in intake storage only.")
svc_profile(S_PARTNER, T_DATA, calls=[A_REPORT], exposes=[], reads=[], writes=[], deletes=[], deal="Enterprise dashboards.")
api_spec(A_REPORT, S_ETL, reads=[DB_LAKE], writes=[])
db_reg(DB_LAKE, [], role="Columnar lake; carries shared snapshots across every cluster.")

# --- Vendor-linked geodata routing
db_reg(DB_ROUTE, [], role="Vendor-normalized traffic snapshots.", traps=["Do not confuse with Fleet Telemetry Store; Route ETL Store holds vendor math."])

# --- Controls
control_rec(C_IMMUTABLE, [DB_LEDGER, DB_LEDGER_MIRROR], T_COREDB, note="Append-only enforcement; violations page Core Storage immediately.")
control_rec(C_FLAG, [S_CHECKOUT, S_ORDERS], T_INTAKE, note="Higher-traffic order paths must ramp behind feature flags.")
control_rec(C_ISOLATION, [DB_ORDERS, DB_WAREHOUSE], T_COREDB, note="Row scoping enforced on shared stores; a hard requirement for regulated customers.")
control_rec(C_FRAUD, [DB_FRAUD, DB_LEDGER], T_PAYMENTS, note="Cutoff review before every promotion run.")
control_rec(C_VENDOR_SCAN, [S_FLEET, S_CHECKOUT], T_INTAKE, note="Vendor dependencies pass the scan gate monthly.")
control_rec(C_BACKUP_DRILL, [DB_ORDERS, DB_LEDGER, DB_WAREHOUSE], T_COREDB, note="Quarterly restore proof for every transactional store; Aurora Compute keeps the restore points.")
control_rec(C_ONCALL, [DB_ORDERS], T_COREDB, note="Pages a named responder within five minutes of dispatch.")
control_rec(C_PENTEST, [], T_PAYMENTS, note="Annual external test of customer surfaces such as checkout and partner portals.")

# --- Vendors
vendor_rec(V_AURORA, [DB_ORDERS, DB_LEDGER], note="Managed hosting of the two stores of record; provides backup restore points.")
vendor_rec(V_SOLVEX, [A_PAYMENTS], note="Acquiring gateway behind Payments Service; the only vendor authorized to clear charge requests.")
vendor_rec(V_ORCHARD, [DB_ROUTE], note="Fallback geodata vendor; used after the primary mapping feed degraded. Route math only; never payment data.")
vendor_rec(V_DELTAWAVE, [DB_QUEUE], note="Transport vendor; holds the retry throttle for customer texts.")
vendor_rec(V_HARBOUR, [], note="Independent ledger archive auditor; issues the annual retention finding.")
vendor_rec(V_PINEFORK, [S_WAREHOUSE], note="Hardware cameras on sortation lines.")
vendor_rec(V_GRANITE, [], note="External pen-test vendor; scope is checkout and partner surfaces.")
vendor_rec(V_NIMBUS, [DB_ROUTE], note="Primary geodata and traffic vendor for Fleet Dispatch.")

# --- Customers
customer_rec(CUST_ACME, uses=[S_ORDERS, S_CHECKOUT], requires=[C_ISOLATION], notes="Latency SLA posture; escalation path is Lin Mei or on-call intake.")
customer_rec(CUST_WINDWARD, uses=[S_ORDERS, S_FLEET], requires=[C_ISOLATION, C_BACKUP_DRILL], notes="Perishables; telemetry freshness is contractual.")
customer_rec(CUST_LAKESIDE, uses=[S_ORDERS, S_WAREHOUSE], requires=[C_ISOLATION, C_PENTEST], notes="Regulated deliveries with pharmacy notifications.")
customer_rec(CUST_SOLSTICE, uses=[S_CHECKOUT, S_ORDERS], requires=[C_FRAUD], notes="Runs the August promo stacking pilot alongside Solstice Media benchmark tests.")
customer_rec(CUST_VAULTTREE, uses=[S_ORDERS, S_PAYOUT], requires=[C_IMMUTABLE], holds=[S_PAYOUT], notes="High-value shipments demand payout ledger history.")
customer_rec(CUST_NORDHOLLOW, uses=[S_ORDERS], requires=[C_ISOLATION], notes="Shield tier across the north region.")
customer_rec(CUST_CINDERGATE, uses=[S_WAREHOUSE, S_FLEET], requires=[C_ISOLATION], notes="Scan-heavy industrial account.")
customer_rec(CUST_ORCHID, uses=[S_NOTIFY, S_ORDERS], requires=[C_ONCALL], notes="June seasonal drops drive customer text volume.")
customer_rec(CUST_TRAMLINE, uses=[S_PAYOUT, S_ORDERS], requires=[C_IMMUTABLE], holds=[S_PAYOUT], notes="Courier settlement aggregator.")
customer_rec(CUST_GREENFIELD, uses=[S_NOTIFY], requires=[C_ONCALL], notes="Notified templates for pharmacy reminders.")

# --- Releases
release_note(R_CHECKOUT_V2, [S_CHECKOUT], approved=P_LIN, window="February", extra_prose_text="Shipping note: builds the promo stacking pilot.")
release_note(R_CHECKOUT_V3, [S_CHECKOUT], approved=P_LIN, window="August", extra_facts=[(R_CHECKOUT_V3, "INTRODUCED", A_PROMO)], extra_prose_text="Side fact: promo fail-open defaults shipped in this cut.")
release_note(R_ORDERS_V9, [S_ORDERS], approved=P_LIN, window="May", extra_prose_text="Idempotency keys landed as the intake retry-safety change.")
release_note(R_ORDERS_V10, [S_ORDERS], approved=P_LIN, window="September", extra_prose_text="Intake burst quota brought under the gateway cut.")
release_note(R_PAYMENTS_V7, [S_PAYMENTS], approved=P_MARA, window="April", extra_facts=[(R_PAYMENTS_V7, "INTRODUCED", DB_LEDGER)], extra_prose_text="Known consequence: contributed to the April overcharge run through refund dedupe gaps; the incident record carries the causal edge.")
release_note(R_PAYMENTS_V8, [S_PAYMENTS, S_PAYOUT], approved=P_MARA, window="July", extra_prose_text="Held by Mara before clearing payout ownership.")
release_note(R_PAYMENTS_V9, [S_PAYMENTS], approved=P_MARA, window="December", extra_prose_text="Ledger mirror lag probe flows for dashboards.")
release_note(R_WAREHOUSE_V6, [S_WAREHOUSE], approved=P_RAVI, window="August", extra_prose_text="Vision thresholds shipped after the July mismatch was reviewed.")
release_note(R_FLEET_V5, [S_FLEET], approved=P_RAVI, window="October", extra_prose_text="Clock-skew guard landed straight into the release used after the dispatch glitch.")
release_note(R_NOTIFY_V6, [S_NOTIFY], approved=P_SOFIA, window="July", extra_prose_text="Queue backpressure caps introduced before the June flood fix.")
release_note(R_NOTIFY_V7, [S_NOTIFY], approved=P_SOFIA, window="September", extra_prose_text="Milestone template dedupe keys.")
release_note(R_ETL_V12, [S_ETL], approved=P_BOGDAN, window="November", extra_prose_text="Lake compaction plus partner filter surfaces land together.")
release_note(R_HELPDESK_V3, [S_HELPDESK], approved=P_SOFIA, window="June", extra_prose_text="Cross-parcel case linking shipped.")
release_note(R_PAYOUT_V2, [S_PAYOUT], approved=P_MARA, window="June", extra_prose_text="Settlement retry scheduling rules after the head-of-line finding.")

# --- Incidents
incident_rec(I_BLUE, "2026-03-09", commander=P_TARO, affected_services=[S_PAYMENTS], affected_dbs=[DB_LEDGER], caused_by=None, cleared_releases=[(R_PAYMENTS_V7, "charge batching is unrelated; batching landed later in April")], symptoms="Ledger writes stalled during morning peaks; payouts unaffected.")
incident_rec(I_OVERCHARGE, "2026-04-14", commander=P_MARA, affected_services=[S_PAYMENTS], affected_dbs=[], caused_by=(R_PAYMENTS_V7, "refund dedupe missed stale idempotency keys"), symptoms="Duplicate charge rows on promo tests; Windward Grocers and Solstice Media both issued refunds.")
incident_rec(I_PAYOUT_DELAY, "2026-05-14", commander=P_TARO, affected_services=[S_PAYOUT], affected_dbs=[DB_PAYOUT], caused_by=None, cleared_releases=[(R_PAYMENTS_V8, "charge-side split had no settlement residue")], symptoms="Courier batches delayed by head-of-line blocking in the Payout Queue.")
incident_rec(I_ETL_GAPS, "2026-06-11", commander=P_BOGDAN, affected_services=[S_PARTNER, S_ETL], affected_dbs=[DB_LAKE], caused_by=None, cleared_releases=[(R_ETL_V12, "compaction shipped in November; cannot explain the June gap")], symptoms="Partner dashboards showed June 4-7 ledger partitions missing.")
incident_rec(I_NOTIFY_FLOOD, "2026-06-30", commander=P_OMAR, affected_services=[S_NOTIFY], affected_dbs=[DB_QUEUE], caused_by=None, cleared_releases=[], symptoms="Retry storm produced duplicate customer texts for Windward Grocers.")
incident_rec(I_LABELS, "2026-07-21", commander=P_RAVI, affected_services=[S_WAREHOUSE], affected_dbs=[DB_VISION, DB_WAREHOUSE], caused_by=None, cleared_releases=[(R_WAREHOUSE_V6, "threshold rewrite shipped in August after this incident; timing excludes it")], symptoms="Two totes matched one carton on the Pinefork line.")
incident_rec(I_GATEWAY, "2026-08-05", commander=P_JESSE, affected_services=[S_CHECKOUT, S_ORDERS], affected_dbs=[], caused_by=None, cleared_releases=[], symptoms="Bursts of 403 through the public path during promo stacking.")
incident_rec(I_LEDGER_STALL, "2026-09-02", commander=P_TARO, affected_services=[S_PAYMENTS], affected_dbs=[DB_LEDGER, DB_LEDGER_MIRROR], caused_by=None, cleared_releases=[(R_PAYMENTS_V8, "the payout split did not touch failover logic")], symptoms="An append lost a replica mid-failover; mirror lag spiked.")
incident_rec(I_CLOCK, "2026-10-06", commander=P_RAVI, affected_services=[S_FLEET], affected_dbs=[DB_TELEMETRY], caused_by=None, cleared_releases=[(R_FLEET_V5, "skew guard shipped in the same month as the slip; not causal")], symptoms="Route assignments shifted 40 minutes during the vendor feed swap.")
incident_rec(I_ARCHIVE, "2026-05-28", commander=P_CELIA, affected_services=[S_ORDERS], affected_dbs=[DB_ORDERS_ARCH, DB_ORDERS], caused_by=None, cleared_releases=[], symptoms="Retention scans slowed reads on the order path; the Orders Archive copy itself stayed healthy.")

# --- Postmortems (one proved chain, several cleared releases)
postmortem(I_LEDGER_STALL, "2026-09-09", P_TARO, caused_by=(R_PAYMENTS_V9, "ledger mirror lag probe read stale failover state and short-circuited an append"), cleared=[(R_PAYMENTS_V8, "the payout split did not touch failover logic"), (C_IMMUTABLE, "the control executed correctly; the probe bypassed it")], highlights=["Cross-cluster probing between payments and dispatch was needed.", "Timeline pinned at 14:12 local through mirror audit."], notes="Compliance: the Ledger Immutability Control held; the probe read-only path was the gap.")
postmortem(I_PAYOUT_DELAY, "2026-05-20", P_TARO, caused_by=None, cleared=[(R_PAYMENTS_V8, "charge-side split had no settlement residue"), (C_ONCALL, "paging escalated within the five-minute rule as required")], highlights=["Payout queue head-of-line shape documented.", "Fixes landed in Payout Release v2 in June."], notes="The settlement queue now alerts on the first blocked batch.")
postmortem(I_GATEWAY, "2026-08-11", P_JESSE, caused_by=(R_CHECKOUT_V3, "promo fail-open generated a request burst the gateway classifier treated as abuse"), cleared=[(R_CHECKOUT_V2, "the v2 rollout predates the August surge"), (C_FLAG, "the flag gate executed cleanly; the burst was a response-class shape problem")], highlights=["Vendor Solvex saw the same shape and confirmed burst classification."], notes="Promo burst caps shipped as a hotfix.")
postmortem(I_ETL_GAPS, "2026-06-18", P_BOGDAN, caused_by=(R_NOTIFY_V6, "notification queue changes shared a retry id with the ETL scheduler; nightly copies skipped partitions"), cleared=[(R_ETL_V12, "compaction landed long after the June gaps")], highlights=["Yuki built the June 4-7 gap alert."], notes="Partner filters shipped with Tracker version 13 of the reporting surface.")
postmortem(I_NOTIFY_FLOOD, "2026-07-07", P_OMAR, caused_by=(R_NOTIFY_V6, "unbounded retries ran while the backpressure caps were being tuned; the flood forced the cap rollout"), cleared=[(R_ETL_V12, "lake compaction is unrelated to the message line")], highlights=[], notes="Cap tuning completed in July; the June 30 storm predated the shipped caps.")
postmortem(I_BLUE, "2026-03-15", P_TARO, caused_by=(R_CHECKOUT_V2, "quote caching inflated morning checkout concurrency and stalled ledger appends"), cleared=[(R_PAYMENTS_V7, "charge batching shipped in April; the fault window was March")], highlights=["First cross-cluster ticket between Payments and Intake.", "Root fix: intake quote throttling."], notes="The Ledger Immutability Control held throughout.")
postmortem(I_OVERCHARGE, "2026-04-21", P_MARA, caused_by=(R_PAYMENTS_V7, "refund dedupe key reused checkout idempotency keys"), cleared=[(R_ORDERS_V9, "intake idempotency keys behaved as designed")], highlights=["Ledger reconciliation issued refunds by April 30."], notes="The Ledger Immutability Control was not violated; corrections were appended only.")
postmortem(I_LABELS, "2026-07-28", P_RAVI, caused_by=(P_JESSE, "vendor scan pose calibration had drifted after the new camera rig"), cleared=[(R_WAREHOUSE_V6, "threshold rewrite shipped after the July mismatch")], highlights=["Hardware fix from Pinefork."], notes="Tote reconciliation rerun clean on July 23.")
postmortem(I_CLOCK, "2026-10-12", P_RAVI, caused_by=(V_NIMBUS, "primary feed handed out skewed timestamps during the vendor swap"), cleared=[(V_ORCHARD, "the fallback feed stayed healthy all shift"), (R_FLEET_V5, "the skew guard landed too late to prevent the slip")], highlights=["Clock sync fixed via internal time source from core hosts."], notes="No mapping vendor changes needed afterwards.")
postmortem(I_ARCHIVE, "2026-06-03", P_CELIA, caused_by=None, cleared=[(R_ORDERS_V10, "the quota guard shipped well after the slowdown"), (V_AURORA, "the hosting vendor showed zero storage contention by audit")], highlights=["Retention schedule rebalanced to overnight."], notes="Explicit negative: the Orders Archive stayed healthy; only read paths slowed.")

# =============================================================================
# Knowledge-base notes: rumor prose that carries NO fact lines. Several exist
# only so dated correction records can supersede them.
# =============================================================================
kb_note("kb-notify-rumor", "2026-07-01", "Support KB: guessed cause of the June flood", ["Rumor: Notification Release v7 opened the June flood.", "This note was written the day after the storm, before any timeline review."])
kb_note("kb-mirror-rumor", "2026-04-18", "Finance KB: draft copy about the ledger replica", ["Draft claim: Ledger Mirror reads Orders Primary as a secondary source.", "The registry draft that spawned this claim was never promoted."])
kb_note("kb-retention-rumor", "2026-05-29", "Storage KB: suspected drill violation", ["Rumor: the May archive slowdown broke the Restore Drill Control.", "Written by a shift engineer before the drill evidence landed."])
kb_note("kb-payout-rumor", "2026-05-15", "Ops KB: guessed cause of the payout delay", ["Rumor: Payout Release v2 caused Payout Delay Thursday.", "Antedates the release calendar check."])
kb_note("kb-routes-rumor", "2026-09-20", "Routing KB: who feeds the route store", ["Rumor: Orchard Routes supplies the Ledger Mirror data set.", "Conflates the route store with the mirror during an onboarding slide review."])
kb_note("kb-gateway-rumor", "2026-08-20", "Checkout KB: approval gossip", ["Rumor: approval for Checkout Release v3 was withdrawn in mid-August.", "Circulated in a chat thread without a calendar citation."])

# =============================================================================
# Corrections: dated records that explicitly supersede the rumor notes above.
# =============================================================================
correction("kb-notify-rumor", I_NOTIFY_FLOOD, "CAUSED_BY", R_NOTIFY_V7, "negated",
    "Correction: the June Notification Flood was not opened by Notification Release v7. That release shipped in September; the flood was June 30. The support KB note is superseded.",
    "Superseded statement: 'Notification Release v7 opened the June flood.'",
    "2026-10-04")
correction("kb-mirror-rumor", DB_ORDERS, "REPLICATES_TO", DB_LEDGER_MIRROR, "negated",
    "Correction: Orders Primary does not replicate into Ledger Mirror. The mirror receives Ledger Primary only. The finance KB draft is superseded.",
    "Superseded statement: 'Ledger Mirror reads Orders Primary as a secondary source.'",
    "2026-04-20")
correction("kb-retention-rumor", C_BACKUP_DRILL, "PROTECTS", DB_ORDERS_ARCH, "affirmed",
    "Correction: the Restore Drill Control passed for the archive in May; the slowdown did not breach it. Coverage extends to Orders Archive. The storage KB rumor is superseded.",
    "Superseded statement: 'The May archive slowdown broke the Restore Drill Control.'",
    "2026-06-12")
correction("kb-payout-rumor", I_PAYOUT_DELAY, "CAUSED_BY", R_PAYOUT_V2, "negated",
    "Correction: Payout Release v2 did not cause Payout Delay Thursday. That release shipped in June; the incident ran in May. The ops KB note is superseded.",
    "Superseded statement: 'Payout Release v2 caused Payout Delay Thursday.'",
    "2026-06-10")
correction("kb-routes-rumor", V_ORCHARD, "SUPPLIES", DB_LEDGER_MIRROR, "negated",
    "Correction: Orchard Routes supplies route math only; it does not feed Ledger Mirror or any payment store. The routing KB slide note is superseded.",
    "Superseded statement: 'Orchard Routes supplies the Ledger Mirror data set.'",
    "2026-09-25")
correction("kb-gateway-rumor", P_LIN, "APPROVED", R_CHECKOUT_V3, "affirmed",
    "Correction: approval for Checkout Release v3 by Lin Mei was never withdrawn; it stands. The checkout KB gossip note is superseded.",
    "Superseded statement: 'Approval for Checkout Release v3 was withdrawn in mid-August.'",
    "2026-08-24")

# =============================================================================
# Narratives: cross-cluster storytelling that restates earlier facts with
# different words. Restated edges keep their profile-record provenance; the
# narrative cites the records it rewords.
# =============================================================================
narrative("2026-06-05", [
    "One order from portal to partner report: order state lands in the order record store once intake confirms it, the charge journal books the charge, the mirror copy feeds dashboards, Analytics ETL lifts the charge journal nightly into the lake, and Partner Portal reads the lake through the reporting surface.",
], facts_for(S_ORDERS, "WRITES_TO", DB_ORDERS) + facts_for(S_PAYMENTS, "WRITES_TO", DB_LEDGER) + facts_for(DB_LEDGER, "REPLICATES_TO", DB_LEDGER_MIRROR) + facts_for(S_ETL, "READS_FROM", DB_LEDGER) + facts_for(S_ETL, "WRITES_TO", DB_LAKE) + facts_for(S_PARTNER, "CALLS", A_REPORT) + facts_for(A_REPORT, "READS_FROM", DB_LAKE), record_id="nr-walkthrough", title_prefix="Narrative memo: one order from portal to partner report")

narrative("2026-06-30", [
    "How hub counts travel to the lake: vision scan events stream from the camera rail into the hub inventory, and Analytics ETL lifts the hub inventory sample stream nightly. Fleet Dispatch never reads orders directly; it trusts the hub inventory instead.",
], facts_for(DB_VISION, "REPLICATES_TO", DB_WAREHOUSE) + facts_for(S_ETL, "READS_FROM", DB_WAREHOUSE), record_id="nr-floor", title_prefix="Narrative memo: how hub counts travel to the lake")

narrative("2026-07-04", [
    "Message retries without duplicates: the outbound message line accumulates retries with dedupe keys per milestone, DeltaWave Communications holds the transport throttle for the message line, and Omar Diaz owns retry caps on Notification Service, which writes the message line.",
], facts_for(S_NOTIFY, "WRITES_TO", DB_QUEUE) + facts_for(V_DELTAWAVE, "SUPPLIES", DB_QUEUE), record_id="nr-messages", title_prefix="Narrative memo: message retries without duplicates")

narrative("2026-07-10", [
    "Courier settlement discipline: settlement batches for couriers queue in the Payout Queue until the retry rules land, Mara Okafor personally approved the settlement retry rules while owning the ledger schema gate, and Vaulttree Estate requires an audit trail on its payouts.",
], facts_for(S_PAYOUT, "READS_FROM", DB_PAYOUT) + facts_for(S_PAYOUT, "WRITES_TO", DB_PAYOUT) + facts_for(P_MARA, "APPROVED", R_PAYOUT_V2) + facts_for(CUST_VAULTTREE, "REQUIRES", C_IMMUTABLE), record_id="nr-settle", title_prefix="Narrative memo: courier settlement discipline")

narrative("2026-07-16", [
    "Who rides the fan-out adapter: Payments Service reuses the Swarm API to reach vendor mapping services, Nimbus Routing composes turn-by-turn directions through the same adapter, and the adapter alone purges the van sample stream on 90-day windows.",
], facts_for(S_PAYMENTS, "CALLS", A_SWARM) + facts_for(S_ROUTING, "CALLS", A_SWARM) + facts_for(A_SWARM, "PURGES", DB_TELEMETRY), record_id="nr-swarm", title_prefix="Narrative memo: fan-out adapter riders")

narrative("2026-07-22", [
    "Vendor fallback story: the primary mapping vendor feeds the normalized traffic snapshots, the fallback vendor joined after a degraded primary window, and both feed the same store that Fleet Dispatch reads for route assignment.",
], facts_for(V_NIMBUS, "SUPPLIES", DB_ROUTE) + facts_for(V_ORCHARD, "SUPPLIES", DB_ROUTE) + facts_for(S_FLEET, "READS_FROM", DB_ROUTE), record_id="nr-vendors", title_prefix="Narrative memo: how van routes get their traffic sense")

narrative("2026-07-28", [
    "Chain of one advisory question: Taro Kurosawa stands on-call for the read-only ledger replica; Piper review of September showed the lag probe shepherded by Payments Release v9 short-circuited an append; the probe idea arrived with Payments Release v9, which shipped into Payments Service.",
], facts_for(P_TARO, "ONCALL_FOR", DB_LEDGER_MIRROR) + facts_for(R_PAYMENTS_V9, "SHIPS", S_PAYMENTS) + facts_for(I_LEDGER_STALL, "CAUSED_BY", R_PAYMENTS_V9), record_id="nr-lagprobe", title_prefix="Narrative memo: the lag probe question")

narrative("2026-08-01", [
    "Restated approvals: Lin Mei approved both checkout cuts, the ledger append batching release went out under Mara Okafor, and Sofia Beltan approved both notification cuts.",
], facts_for(P_LIN, "APPROVED", R_CHECKOUT_V2) + facts_for(P_LIN, "APPROVED", R_CHECKOUT_V3) + facts_for(P_MARA, "APPROVED", R_PAYMENTS_V7) + facts_for(P_SOFIA, "APPROVED", R_NOTIFY_V6) + facts_for(P_SOFIA, "APPROVED", R_NOTIFY_V7), record_id="nr-approvals", title_prefix="Narrative memo: who signed what")

# =============================================================================
# Synthesis memos
# =============================================================================
memo("2026-09-30", [
    "Nimbusfield cross-team posture: the intake, payments and warehouse clusters each page through Core Storage controls.",
    "The analytics lake is the only sanctioned place where charge journal, hub inventory and message data are compared side by side.",
    "Every regulated customer needs evidence of the Isolation Control and, for payouts, the ledger audit line.",
], notes_id="summary-memo-sept")
memo("2026-08-30", [
    "August promo bursts touched three teams at once: intake through checkout, payments through the ledger mirror probe, and dispatch through nothing.",
    "Notifications stayed quiet in the same window; only promo promotions enqueue messages.",
], notes_id="summary-memo-aug")
memo("2026-10-01", [
    "Governance synthesis: the Ledger Immutability Control and the Restore Drill Control both sit under Core Storage; the Launch Flag Gate belongs to intake; the Fraud Threshold Review belongs to payments.",
    "Two controls protect databases only, two protect customer-facing services, and one protects both.",
], notes_id="summary-memo-governance")
memo("2026-10-02", [
    "Negative evidence index: Payments Release v7 was cleared for Blue Monday; Payments Release v8 cleared twice; Warehouse Release v6 cleared for July Duplicate Labels; Orchard Routes cleared for October clock skew.",
    "No record anywhere connects the Legacy Order Feeder to any 2026 incident; retired means retired.",
], notes_id="summary-memo-negatives")
memo("2026-10-03", [
    "Missing-link memo: nothing in the corpus connects the Solvex Gateway to routing math or geodata.",
    "If a reader feels the urge to bridge payments and van routing through the gateway, the corpus asks them to refuse; the fan-out adapter is the only shared crossing.",
], notes_id="summary-memo-refusal")
memo("2026-10-04", [
    "Name-collision memo: the Legacy Order Feeder and Orders Intake both touched the Checkout API historically; Fraud Store and Ledger Mirror both ingest from ledger-side sources; Vision Events Store is the real scan archive.",
    "Requests about 'the order thing that duplicates' resolve to the Legacy Order Feeder, never Orders Intake.",
], notes_id="summary-memo-resolution")
memo("2026-10-05", [
    "Milestone map: each 2026 month held one major incident through October, March through October.",
    "May carried two: Payout Delay Thursday and the May Archive Slowdown.",
], notes_id="summary-memo-milestones")

# =============================================================================
# Audits
# =============================================================================
audit_rec(DB_LEDGER, "2026-08-22", V_HARBOUR, "Annual retention finding: Ledger Primary archive policy fulfils the Harbour Audit retention scope; the Launch Flag Gate recorded as in place.")
audit_rec(DB_PAYOUT, "2026-07-15", V_HARBOUR, "Audit note: Payout Queue retention satisfied; no mis-scope found.")
audit_rec(S_CHECKOUT, "2026-04-10", V_GRANITE, "External pen test note: the checkout surface passed; findings closed before the August promo tests.")
audit_rec(DB_ORDERS, "2026-05-20", V_HARBOUR, "Audit note: restore drill evidence on the order store met scope; the Isolation Control documented.")
audit_rec(DB_WAREHOUSE, "2026-06-25", V_HARBOUR, "Audit note: hub inventory retention scope satisfied; scan-history sampling documented.")
audit_rec(S_PAYOUT, "2026-06-15", V_HARBOUR, "Audit note: settlement trails complete for the first half of the year; Vaulttree Estate findings closed in June.")
audit_rec(S_PARTNER, "2026-05-30", V_GRANITE, "External pen test note: partner dashboard scope reviewed; session controls passed.")
audit_rec(DB_ORDERS_ARCH, "2026-04-28", V_HARBOUR, "Audit note: retention cold store sampling passed; restore paths verified against Aurora Compute snapshots.")
audit_rec(DB_FRAUD, "2026-03-30", V_HARBOUR, "Audit note: feature store lineage documented; mirror-derived sampling is nightly only.")

# =============================================================================
# Rotas
# =============================================================================
rota_rec(P_TARO, DB_LEDGER_MIRROR, "2026-01-30", "Standing rota note: the pager targets the Ledger Mirror first, then Payments Service.")
rota_rec(P_RAVI, DB_VISION, "2026-01-30", "Standing rota note: the Vision Events Store pages the dispatch on-call within five minutes.")
rota_rec(P_CELIA, DB_ORDERS, "2026-01-30", "Standing rota note: the order store pages Core Storage for both replica and restore drills.")
rota_rec(P_OMAR, DB_QUEUE, "2026-01-30", "Standing rota note: the Notification Queue pager respects dedupe key semantics before escalating.")
rota_rec(P_BOGDAN, DB_LAKE, "2026-01-30", "Standing rota note: the lake pager owns partner filter warnings with Yuki.")
rota_rec(P_SAMIR, DB_FRAUD, "2026-01-30", "Standing rota note: the Fraud Store pages the payments SRE for sampling checks.")
rota_rec(P_YUKI, S_ETL, "2026-01-30", "Standing rota note: the ETL surfaces pager as data platform analyst.")
rota_rec(P_LIN, S_PRICING, "2026-01-30", "Standing rota note: the pricing pager escalates quote-band changes to intake leadership.")
rota_rec(P_JESSE, DB_ROUTE, "2026-01-30", "Standing rota note: the route store pages the vendor feed owner first.")
rota_rec(P_SOFIA, S_HELPDESK, "2026-01-30", "Standing rota note: the helpdesk pager pairs the care PM with the agent console owner.")
rota_rec(P_CELIA, DB_LEDGER, "2026-02-15", "Standing rota note: Core Storage owns append-failure pages on the ledger primary.")
rota_rec(P_RAVI, DB_TELEMETRY, "2026-02-15", "Standing rota note: the telemetry store pages dispatch for purge-window checks.")

# =============================================================================
# Finalization and validation
# =============================================================================
def validate() -> dict:
    orphans = [(i, f["subject"], f["predicate"], f["object"]) for i, f in enumerate(FACTS) if f["origin"] == "pending" or f["origin"] not in {r["id"] for r in RECORDS}]
    assert not orphans, f"{len(orphans)} facts never got a record origin: {orphans[:5]}"
    record_ids = {r["id"] for r in RECORDS}
    for r in RECORDS:
        superseded = r["links"].get("supersedes")
        superseded = superseded if isinstance(superseded, list) else ([superseded] if superseded else [])
        for rid_ in superseded:
            assert rid_ in record_ids, f"record {r['id']} supersedes unknown {rid_}"
    assert len(RECORDS) >= 150, f"record count {len(RECORDS)} below the 150 requirement"
    by_kind: dict[str, int] = defaultdict(int)
    for r in RECORDS:
        by_kind[r["kind"]] += 1
    used_preds = sorted({f["predicate"] for f in FACTS})
    return {"entities": len(E), "facts": len(FACTS), "records": len(RECORDS), "by_kind": dict(by_kind), "predicates": used_preds}

def entity_records() -> dict[str, list[str]]:
    """Map entity id -> record ids whose prose mentions the entity name."""
    out: dict[str, list[str]] = defaultdict(list)
    for r in RECORDS:
        blob = " ".join(r["prose"]) + " " + r["title"]
        for eid, (etype, name, desc) in E.items():
            if name in blob:
                out[eid].append(r["id"])
    return out

def edge_map(include_negated: bool = False, dedupe: bool = True) -> dict[str, list[tuple[str, str, dict, str]]]:
    """eid -> list of (direction, predicate, fact, other_eid). Affirmed edges only by default."""
    seen: set[tuple[str, str, str]] = set()
    out: dict[str, list[tuple[str, str, dict, str]]] = defaultdict(list)
    for f in FACTS:
        if f["polarity"] != "affirmed" and not include_negated:
            continue
        triple = (f["subject"], f["predicate"], f["object"])
        if dedupe:
            if triple in seen:
                continue
            seen.add(triple)
        out[f["subject"]].append(("out", f["predicate"], f, f["object"]))
        out[f["object"]].append(("in", f["predicate"], f, f["subject"]))
    return out

def allowed_preds(preds: set[str] | None) -> callable:
    def check(pred: str) -> bool:
        return True if preds is None else pred in preds
    return check

def affirmed_edges() -> list[tuple[str, str, str]]:
    seen: set[tuple[str, str, str]] = set()
    out = []
    for f in FACTS:
        if f["polarity"] != "affirmed":
            continue
        triple = (f["subject"], f["predicate"], f["object"])
        if triple not in seen:
            seen.add(triple)
            out.append(triple)
    return out

def paths_between(src: str, dst: str, max_hops: int = 6, preds: set[str] | None = None) -> list[list[tuple[str, str, str, str]]]:
    """All shortest-ish paths up to max_hops over affirmed edges, both directions traversable.
    Returns list of paths; each path is a list of (from, predicate, to, direction_followed) steps."""
    check = allowed_preds(preds)
    out = []
    em = edge_map()
    q = deque([(src, [])])
    best = None
    while q:
        node, path = q.popleft()
        if best is not None and len(path) > best:
            continue
        if node == dst and path:
            out.append(path)
            best = len(path)
            continue
        if len(path) >= max_hops:
            continue
        for _direction, pred, _f, other in em.get(node, []):
            if not check(pred):
                continue
            q.append((other, path + [(node, pred, other, "reverse" if other == _f["subject"] else "forward")]))
    return out

def closure(start: str, max_hops: int = 2, preds: set[str] | None = None) -> tuple[set[str], list[tuple[str, str, str, str]]]:
    """BFS closure over affirmed edges with the traversing steps listed."""
    check = allowed_preds(preds)
    em = edge_map()
    seen, steps, q = {start}, [], deque([(start, 0)])
    while q:
        node, depth = q.popleft()
        if depth >= max_hops:
            continue
        for _direction, pred, _f, other in em.get(node, []):
            if not check(pred):
                continue
            if other not in seen:
                seen.add(other)
                steps.append((node, pred, other, "reverse" if other == _f["subject"] else "forward"))
                q.append((other, depth + 1))
    return seen, steps

if __name__ == "__main__":
    import json
    print(json.dumps(validate(), indent=2))
