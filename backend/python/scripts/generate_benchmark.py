"""Render the RAG Architecture Fingerprint Benchmark artifacts from the domain model.

Artifacts land in benchmarks/graph-rag-fingerprint/ (committed):
  A benchmark-corpus.md           the corpus Argus ingests (fact-line convention)
  B evaluation-questions.md       the question list, no answers
  C answer-key.md                 computed expected answers, paths, citations
  D scoring-guide.md              rubric
  E architecture-verification.md  how the verifier decides what Argus actually is
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_model as m

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "benchmarks" / "graph-rag-fingerprint"
STAMP = "2026-10-18"

DATAFLOW = {"CALLS", "EXPOSES", "READS_FROM", "WRITES_TO", "REPLICATES_TO", "PURGES", "DELETES", "SHIPS", "INTRODUCED", "USES"}
ROTA_PREDS = {"ONCALL_FOR", "REPLICATES_TO", "OWNS", "MEMBER_OF"}
CAUSAL = {"CAUSED_BY", "AFFECTED", "AFFECTED_D", "ALERTED", "RCA_BY"}

nm = lambda e: m.E[e][1]

def rec_by_id(rid_):
    for r in m.RECORDS:
        if r["id"] == rid_:
            return r
    raise AssertionError(f"missing record {rid_}")

def recs_of(kind):
    return [r for r in m.RECORDS if r["kind"] == kind]

def fact_trip(a, p, b, polarity="affirmed"):
    for f in m.FACTS:
        if f["subject"] == a and f["predicate"] == p and f["object"] == b and f["polarity"] == polarity:
            return f
    return None

def hop(a, p, b):
    f = fact_trip(a, p, b)
    if f is None:
        raise AssertionError(f"missing fact {a} -{p}-> {b}")
    return f"{nm(a)} -[{p}]-> {nm(b)}"

def hop_cites(a, p, b):
    outs = {m.FACTS[i]["origin"] for i in m.facts_for(a, p, b) if m.FACTS[i]["polarity"] == "affirmed"}
    return sorted(outs)

def path_lines(path):
    lines, cites = [], []
    for a, p, b, d in path:
        if d == "forward":
            lines.append(hop(a, p, b))
            cites += hop_cites(a, p, b)
        else:
            lines.append("(reverse) " + nm(b) + " -[" + p + "]-> " + nm(a))
            cites += hop_cites(b, p, a)
    return lines, sorted(set(cites))

def find_path(src, dst, seq, preds, max_hops=6):
    """Locate the path whose node sequence equals seq."""
    for cand in m.paths_between(src, dst, max_hops=max_hops, preds=preds):
        if [s[0] for s in cand] + [cand[-1][2]] == seq:
            return cand
    raise AssertionError(f"chain not found {src}->{dst} {seq}")

def negated_pairs():
    return sorted({(f["subject"], f["predicate"], f["object"]) for f in m.FACTS if f["polarity"] == "negated"})

QUESTIONS = []
def Q(qid, cat, ask, hops, expected, cites, alternatives=None, tempt=None, hints=None):
    QUESTIONS.append({
        "id": qid, "category": cat, "ask": ask, "hops": hops,
        "expected": expected, "cites": cites, "alternatives": alternatives or [], "tempt": tempt, "hints": hints or [],
    })

CATS = [
    ("PROV",      "Provenance and single-hop baseline"),
    ("CHAIN",     "Multi-hop chain tracing"),
    ("REVERSE",   "Reverse traversal"),
    ("BLAST",     "Blast radius"),
    ("CONSTRAINT","Multi-constraint lookup"),
    ("BRIDGE",    "Shared-neighbor bridge"),
    ("SHORTPATH", "Shortest path"),
    ("SYNTH",     "Global synthesis"),
    ("TEMPORAL",  "Temporal reasoning and supersession"),
    ("NEGATIVE",  "Negative evidence and false premises"),
    ("SRC",       "Provenance citation"),
    ("EXPLICIT",  "Explicit vs inferred"),
    ("REFUSAL",   "Missing-link refusal"),
    ("TRAP",      "Entity-resolution traps"),
    ("SELFCHECK", "Architecture self-report"),
]

# --- Q01/Q02 provenance
Q("Q01", "PROV", "Which team owns Fleet Dispatch, and what does that team's page say it operates?",
  1, [hop(m.T_DISPATCH, "OWNS", m.S_FLEET)], hop_cites(m.T_DISPATCH, "OWNS", m.S_FLEET),
  tempt="Care Platform Team (runs portals, not fleet); Dispatch API is a surface, not the owner.",
  hints=["The answer is one OWNS edge."])
Q("Q02", "PROV", "Which vendor supplies the Payments Gateway API, and which service hosts that API?",
  2, [hop(m.V_SOLVEX, "SUPPLIES", m.A_PAYMENTS), hop(m.S_PAYMENTS, "EXPOSES", m.A_PAYMENTS)],
  hop_cites(m.V_SOLVEX, "SUPPLIES", m.A_PAYMENTS) + hop_cites(m.S_PAYMENTS, "EXPOSES", m.A_PAYMENTS),
  tempt="DeltaWave (supplies the Notification Queue, nothing else); Pinefork (sortation cameras).")

# --- Q03/Q04 chain
SHIP_SEQ = [m.S_ORDERS, m.A_CHECKOUT, m.S_PAYMENTS, m.DB_LEDGER, m.S_ETL, m.A_REPORT, m.S_PARTNER]
p3 = find_path(m.S_ORDERS, m.S_PARTNER, SHIP_SEQ, DATAFLOW)
l3, c3 = path_lines(p3)
Q("Q03", "CHAIN", "Trace how one confirmed checkout session's charge becomes visible on Partner Portal dashboards. Name every system in order and the edge type between them.",
  6, l3, c3,
  alternatives=[] if len(m.paths_between(m.S_ORDERS, m.S_PARTNER, preds=DATAFLOW)) == 1 else ["the telemetry route via Fleet Dispatch is also written down, but it is not the charge path"],
  tempt="Jumping from Ledger Primary straight to Partner Portal, or claiming Mirror feeds the portal (finance dashboards read the Mirror, not the portal).",
  hints=["6 hops", "expect the exact order Orders Intake, Checkout API, Payments, Ledger Primary, Analytics ETL, Reporting API, Partner Portal"])
TEL_SEQ = [m.CUST_WINDWARD, m.S_FLEET, m.DB_TELEMETRY, m.S_ETL, m.A_REPORT, m.S_PARTNER]
p4 = find_path(m.CUST_WINDWARD, m.S_PARTNER, TEL_SEQ, DATAFLOW)
l4, c4 = path_lines(p4)
Q("Q04", "CHAIN", "How does Windward Grocers' van telemetry reach the Partner Portal dashboards? List the systems in order.",
  5, l4, c4,
  tempt="Routing tree via Nimbus (routing has no telemetry edges).")

# --- Q05/Q06 reverse
ledger_pages = sorted({f["subject"] for f in m.FACTS if f["predicate"] == "ONCALL_FOR" and f["object"] in (m.DB_ORDERS, m.DB_LEDGER, m.DB_LEDGER_MIRROR) and f["polarity"] == "affirmed"})
assert set(ledger_pages) == {m.P_CELIA, m.P_TARO}, ledger_pages
rota_recs = sorted({r["id"] for r in recs_of("rota") if any(m.FACTS[i]["object"] in (m.DB_ORDERS, m.DB_LEDGER, m.DB_LEDGER_MIRROR) for i in r["owned"])})
Q("Q05", "REVERSE", "A paging rule hits Orders Primary, Ledger Primary and Ledger Mirror in one night. Which people are on call for each of them?",
  2,
  [f"{nm(p)} is on call for " + " and ".join(nm(t) for t in sorted({f['object'] for f in m.FACTS if f['predicate']=='ONCALL_FOR' and f['object'] in (m.DB_ORDERS, m.DB_LEDGER, m.DB_LEDGER_MIRROR) and f['subject']==p and f['polarity']=='affirmed'})) for p in ledger_pages],
  sorted(set(rota_recs)) ,
  tempt="Jesse Moon (payments) or claiming the commander pages himself; Lin Mei sits inside intake rota only.",
  hints=["Reverse-lookup on ONCALL_FOR.", "Ledger Mirror's named on call is Taro Kurosawa; Orders Primary and Ledger Primary are Celia Hague."])
imm_reqs = sorted({f["subject"] for f in m.FACTS if f["predicate"] == "REQUIRES" and f["object"] == m.C_IMMUTABLE and f["polarity"] == "affirmed"})
Q("Q06", "REVERSE", "Which customers require the Ledger Immutability Control?",
  1, [f"{nm(c)} requires the Ledger Immutability Control" for c in imm_reqs],
  sorted({r for c in imm_reqs for r in hop_cites(c, "REQUIRES", m.C_IMMUTABLE)}),
  tempt="Greenfield Grocers (requires Isolation Control, not Immutability).")

# --- Q07/Q08 blast
def rec_of_entity(eid):
    for r in m.RECORDS:
        if any(m.FACTS[i]["subject"] == eid for i in r["owned"]):
            return r
    raise AssertionError("no record on subject " + eid)

vendor_of = lambda v: rec_of_entity(v)["id"]
cust_of = lambda c: rec_of_entity(c)["id"]

closed7, _ = m.closure(m.S_CHECKOUT, 1)
assert len(closed7) == 13, len(closed7)  # 12 neighbors + self
custs_checkout = sorted({f["subject"] for f in m.FACTS if f["predicate"] == "USES" and f["object"] == m.S_CHECKOUT and f["polarity"] == "affirmed"})
Q("Q07", "BLAST", "From Checkout Storefront, list its immediate graph neighborhood (one hop in either direction) and name the customers that directly consume it.",
  1,
  ["Neighborhood (one hop): " + "; ".join(sorted(nm(x) for x in closed7 if x != m.S_CHECKOUT)) + ".",
   "Direct consumers: " + ", ".join(nm(c) for c in custs_checkout) + " (each one record: a customer Uses the storefront)."],
  [rec_of_entity(m.S_CHECKOUT)["id"]] + [vendor_of(c) for c in custs_checkout],
  tempt="Naming Windward (uses Fleet Dispatch, not checkout) or Vaulttree (ledger controls).",
  hints=["12 neighbors", "the two Uses customers are Solstice Media and Acme Retail"])
swarm_users = sorted({f["subject"] for f in m.FACTS if f["object"] == m.A_SWARM and f["polarity"] == "affirmed" and f["predicate"] in ("CALLS", "EXPOSES")})
assert {m.S_PAYMENTS, m.S_ROUTING, m.S_FLEET} <= set(swarm_users), swarm_users
Q("Q08", "BLAST", "If Swarm API goes down, which services degrade? Expect exactly three.",
  1, ["Affected services: " + ", ".join(nm(s) for s in swarm_users) + "."],
  hop_cites(m.S_PAYMENTS, "CALLS", m.A_SWARM),
  tempt="Warehouse Management (uses Warehouse API, harmless to Swarm); the Payment Gateway API exposes blame onto Solvex, not the fallout list.")

# --- Q09/Q10 constraints
pairs9 = []
for c in sorted(m.E):
    if m.E[c][0] != "Customer":
        continue
    req = fact_trip(c, "REQUIRES", m.C_IMMUTABLE)
    hold = fact_trip(c, "HELD_BY", m.S_PAYOUT)
    if req and hold:
        pairs9.append(c)
assert {m.CUST_VAULTTREE, m.CUST_TRAMLINE} == set(pairs9), pairs9
Q("Q09", "CONSTRAINT", "Which customers require the Ledger Immutability Control and also hold Payout Service settlement?",
  2, [f"{nm(c)} (requires Immutability; holds Payout Service)" for c in pairs9],
  hop_cites(m.CUST_VAULTTREE, "REQUIRES", m.C_IMMUTABLE) + hop_cites(m.CUST_VAULTTREE, "HELD_BY", m.S_PAYOUT),
  tempt="Lakeside Pharmacy (holds Payout Service but requires nothing of that control family).")
wind = fact_trip(m.CUST_WINDWARD, "REQUIRES", m.C_BACKUP_DRILL) and fact_trip(m.CUST_WINDWARD, "USES", m.S_FLEET)
assert wind
Q("Q10", "CONSTRAINT", "Which customer requires Restore Drill Control and also runs van telemetry through Fleet Dispatch?",
  2, [f"{nm(m.CUST_WINDWARD)}: requires Restore Drill Control; uses Fleet Dispatch; its van telemetry reaches the lake."],
  hop_cites(m.CUST_WINDWARD, "REQUIRES", m.C_BACKUP_DRILL) + hop_cites(m.CUST_WINDWARD, "USES", m.S_FLEET),
  tempt="Tramline Couriers (uses Fleet Dispatch but requires Immutability, not the drill).")

# --- Q11/Q12 bridge
sets11 = {s: {f["object"] for f in m.FACTS if f["subject"] == s and f["polarity"] == "affirmed" and f["predicate"] in ("CALLS", "EXPOSES")} for s in (m.S_PAYMENTS, m.S_ROUTING)}
common = sets11[m.S_PAYMENTS] & sets11[m.S_ROUTING]
assert common == {m.A_SWARM}, common
third = {f["subject"] for f in m.FACTS if f["object"] == m.A_SWARM and f["polarity"] == "affirmed" and f["predicate"] in ("CALLS", "EXPOSES")} - {m.S_PAYMENTS, m.S_ROUTING}
assert third == {m.S_FLEET}, third
Q("Q11", "BRIDGE", "Which single shared dependency do Payments Service and Nimbus Routing converge on, and which third service also connects to it?",
  2, ["Shared dependency: Swarm API.", "Third connector: " + ", ".join(nm(t) for t in third) + " (it exposes Swarm API)."],
  hop_cites(m.S_PAYMENTS, "CALLS", m.A_SWARM),
  tempt="Report API/ledger bridges; Orchard Routes is a vendor feed for the map routing path, not the shared dependency.")
assert fact_trip(m.S_ETL, "EXPOSES", m.A_REPORT) and fact_trip(m.S_PARTNER, "CALLS", m.A_REPORT)
owner_etl = sorted({f["subject"] for f in m.FACTS if f["predicate"] == "OWNS" and f["object"] == m.S_ETL and f["polarity"] == "affirmed"})
assert owner_etl == [m.T_DATA]
Q("Q12", "BRIDGE", "Which single API carries Analytics ETL output to the Partner Portal, and which team runs the producer side?",
  2, ["Bridge API: Reporting API.", "Producer owner: Data Platform Team."],
  hop_cites(m.S_ETL, "EXPOSES", m.A_REPORT) + hop_cites(m.S_PARTNER, "CALLS", m.A_REPORT),
  tempt="Checkout API (wrong cluster); Payout Queue.")

# --- Q13/Q14 shortest
p13_all = m.paths_between(m.P_TARO, m.P_CELIA, max_hops=6, preds=ROTA_PREDS)
seq13 = [m.P_TARO, m.DB_LEDGER_MIRROR, m.DB_LEDGER, m.P_CELIA]
l13, c13 = path_lines(find_path(m.P_TARO, m.P_CELIA, seq13, ROTA_PREDS))
Q("Q13", "SHORTPATH", "Find the shortest documented route of hops that connects on-call engineer Taro Kurosawa to on-call engineer Celia Hague. List every edge.",
  3, l13, c13,
  tempt="Hoping through Team ownership or MEMBER_OF chains (long, true but not shortest): Taro -> payments rota -> checkout …; the right shape is Store rota hops through the two ledger stores.",
  hints=["3 hops", "Ledger Mirror copies from Ledger Primary, and each store's named on-call is respectively Taro and Celia."])
p14_all = m.paths_between(m.CUST_VAULTTREE, m.DB_LEDGER, max_hops=6, preds=DATAFLOW | {"REQUIRES", "PROTECTS"})
p14 = find_path(m.CUST_VAULTTREE, m.DB_LEDGER, [m.CUST_VAULTTREE, m.C_IMMUTABLE, m.DB_LEDGER], DATAFLOW | {"REQUIRES", "PROTECTS"})
l14, c14 = path_lines(p14)
Q("Q14", "SHORTPATH", "Give the shortest supported route from Vaulttree Estate to Ledger Primary.",
  2, l14, c14,
  tempt="Via Payments usage (customers never USE the ledger directly; only the control chain is a two-hop route).")

# --- Q15/Q16 synthesis
lake_space = defaultdict(set)
for f in m.FACTS:
    if f["predicate"] == "WRITES_TO" and f["polarity"] == "affirmed" and f["object"] in (m.DB_LEDGER, m.DB_WAREHOUSE, m.DB_TELEMETRY, m.DB_QUEUE):
        for o in m.FACTS:
            if o["predicate"] == "OWNS" and o["object"] == f["subject"] and o["polarity"] == "affirmed":
                lake_space[f["object"]].add(o["subject"])
teams15 = sorted({t for s in lake_space.values() for t in s})
assert {m.T_PAYMENTS, m.T_DISPATCH, m.T_SUPPORT} == set(teams15), teams15
assert not fact_trip(m.S_ETL, "READS_FROM", m.DB_ORDERS)
memo_gov = rec_by_id("summary-memo-sept")
Q("Q15", "SYNTH", "Which team domains does the Analytics Lake span, and is the Order Intake cluster inside its nightly span?",
  3,
  ["Sections span " + ", ".join(sorted(nm(t) for t in teams15)) + ".",
   "Intake is NOT included: Analytics ETL never reads Orders Primary; intake history remains in intake storage."],
  [memo_gov["id"], hop_cites(m.S_ETL, "READS_FROM", m.DB_LEDGER)[0], hop_cites(m.S_PAYMENTS, "WRITES_TO", m.DB_LEDGER)[0], hop_cites(m.S_WAREHOUSE, "WRITES_TO", m.DB_WAREHOUSE)[0], hop_cites(m.S_FLEET, "WRITES_TO", m.DB_TELEMETRY)[0], hop_cites(m.S_NOTIFY, "WRITES_TO", m.DB_QUEUE)[0]],
  tempt="Claiming intake is in the lake (the feeder job's legacy purge is not lake ingestion).",
  hints=["payments/warehouse/support"],)
order_rels = sorted({(f["subject"], f["object"]) for f in m.FACTS if f["predicate"] == "SHIPS" and f["object"] == m.S_ORDERS and f["polarity"] == "affirmed"})
appr16 = [(rel, sorted({g["subject"] for g in m.FACTS if g["predicate"] == "APPROVED" and g["object"] == rel and g["polarity"] == "affirmed"})) for rel, _ in order_rels]
assert all(a == [m.P_LIN] for _, a in appr16) and len(order_rels) == 2
Q("Q16", "SYNTH", "Which releases shipped into Orders Intake, and who approved each of them?",
  2, [" ".join([nm(rel), "approved by", ", ".join(nm(a) for a in ap)]) for rel, ap in appr16],
  sorted({r for rel, _ in order_rels for r in hop_cites(rel, "SHIPS", m.S_ORDERS) + hop_cites(m.P_LIN, "APPROVED", rel)}),
  tempt="Checkout Releases v2/v3 (ship into Checkout Storefront, a different target).")

# --- Q17/Q18 temporal (computed stamps from the model)
kb_mirror = rec_by_id("kb-mirror-rumor")
corr_mirror = next(r for r in m.RECORDS if r["links"].get("supersedes") == kb_mirror["id"])
assert fact_trip(m.DB_ORDERS, "REPLICATES_TO", m.DB_LEDGER_MIRROR, polarity="negated")
Q("Q17", "TEMPORAL", "What did the finance knowledge base say on April 18 about Ledger Mirror sourcing, what correction replaced it, and on what date?",
  2,
  [f"On {kb_mirror['stamp']} the KB note '{kb_mirror['title']}' claimed Ledger Mirror reads Orders Primary as a secondary source.",
   f"That claim was superseded on {corr_mirror['stamp']} (record {corr_mirror['id']}): Orders Primary does not replicate into Ledger Mirror; the mirror receives Ledger Primary only."],
  [kb_mirror["id"], corr_mirror["id"]],
  tempt="Reporting the April claim as current truth.",
  hints=["superseded April 20"])
Q("Q18", "TEMPORAL", "As of now, is 'Orders Primary replicates to Ledger Mirror' an active fact?", 1,
  ["No. It is explicitly negated by " + corr_mirror["id"] + f" ({corr_mirror['stamp']})."],
  [corr_mirror["id"]],
  tempt="The old KB wording still contains the sentence; staleness matters.")

# --- Q19/Q20 negative/falsse-premise
pm_payout = next(r for r in recs_of("postmortem") if "Payout Delay" in r["title"])
corr_payout = next(r for r in m.RECORDS if r["links"].get("supersedes") == "kb-payout-rumor")
assert fact_trip(m.I_PAYOUT_DELAY, "CAUSED_BY", m.R_PAYOUT_V2, polarity="negated")
Q("Q19", "NEGATIVE", "Did Payout Release v2 cause Payout Delay Thursday? Give the record that proves your stance.",
  1, ["No. Both the postmortem and the " + corr_payout["id"] + " notice explicitly negate it; the delay was queue suction, not the charge-side split."],
  [pm_payout["id"], corr_payout["id"]],
  tempt="Affirming release-causation pattern generalization (several incidents in the corpus DO have affirmed release causes).")
Q("Q20", "NEGATIVE", "Does the Analytics Lake carry Orders Primary data?",
  2, ["No. Analytics ETL reads Ledger Primary, Warehouse DB, Fleet Telemetry Store and Notification Queue only; Orders Primary is absent from its read list."],
  [memo_gov["id"], hop_cites(m.S_ETL, "READS_FROM", m.DB_LEDGER)[0]],
  tempt="Assuming the lake spans everything with 'orders' in the name.")

# --- Q21/Q22 citation
def audit_for(target):
    for r in recs_of("audit"):
        for i in r["owned"]:
            f = m.FACTS[i]
            if f["predicate"] == "AUDITED_BY" and f["subject"] == target:
                return r, f
    raise AssertionError("no audit for " + target)

aud_ledger_r, aud_ledger_f = audit_for(m.DB_LEDGER)
aud_orders_r, aud_orders_f = audit_for(m.DB_ORDERS)
Q("Q21", "SRC", "Which record documents the external audit finding on Ledger Primary, on what date, and by which auditor?",
  1, [f"Record {aud_ledger_r['id']} ({aud_ledger_r['stamp']}): {aud_ledger_r['prose'][0]} Auditor: {nm(aud_ledger_f['object'])}."],
  [aud_ledger_r["id"]],
  tempt="Harbor Audit lives in two notes; cite the one whose subject is Ledger Primary, not the payments vendor scan.")
Q("Q22", "SRC", "Who is the auditor of record for Orders Primary's storage audit?",
  1, [nm(aud_orders_f["object"]) + f" (record {aud_orders_r['id']})."],
  [aud_orders_r["id"]])

# --- Q23/Q24 explicit vs inferred
legacy_causal = [f for f in m.FACTS if f["subject"] == m.S_ORDERS_LEGACY and f["predicate"] in CAUSAL]
assert not legacy_causal
memo_neg = rec_by_id("summary-memo-negatives")
Q("Q23", "EXPLICIT", "Is there an explicit causal edge from Legacy Order Feeder to any incident?",
  1, ["No. Not one CAUSED_BY/AFFECTED edge leaves the feeder. It shares one historical API with intake, and downstream connectivity across that surface reaches payments, but connectivity is not causation."],
  [memo_neg["id"]],
  tempt="Tracing feeder -> Checkout API -> Payments -> Blue Monday and calling that a causal chain; the memo explicitly forbids reading it that way.")
pine = [f["object"] for f in m.FACTS if f["subject"] == m.V_PINEFORK and f["predicate"] == "SUPPLIES" and f["polarity"] == "affirmed"]
Q("Q24", "EXPLICIT", "Does any record state that Pinefork Supply supplied checkout hardware?",
  1, ["No. Pinefork's only supply record is " + ", ".join(nm(o) for o in pine) + ". No hardware claims touch checkout."],
  [next(r["id"] for r in recs_of("profile") if r["id"] and any(m.FACTS[i]["subject"] == m.V_PINEFORK for i in r["owned"]))],
  tempt="Vision Events Store surge wording written near checkout.")

# --- Q25/Q26 refusal
assert m.paths_between(m.V_SOLVEX, m.DB_ROUTE, max_hops=6, preds=DATAFLOW) == [], "Solvex must not reach Route ETL Store on dataflow edges"
route_readers = sorted({f["subject"] for f in m.FACTS if f["predicate"] == "READS_FROM" and f["object"] == m.DB_ROUTE and f["polarity"] == "affirmed"})
route_vendors = sorted({f["subject"] for f in m.FACTS if f["predicate"] == "SUPPLIES" and f["object"] == m.DB_ROUTE and f["polarity"] == "affirmed"})
assert {m.V_NIMBUS, m.V_ORCHARD} == set(route_vendors) and {m.S_ROUTING, m.S_FLEET} <= set(route_readers)
Q("Q25", "REFUSAL", "Does Solvex Gateway supply the Route ETL Store? If not, name its actual data sources.",
  2, ["No. Solvex Gateway's only supply record is the Payments Gateway API.",
      "The Route ETL Store's real sources: Nimbus Maps (primary feed) and Orchard Routes (fallback feed); Nimbus Routing and Fleet Dispatch read from it."],
  [vendor_of(m.V_SOLVEX), vendor_of(m.V_NIMBUS), vendor_of(m.V_ORCHARD)],
  tempt="Vendor-washing: both are vendors, so assuming Solvex touches routing data.")
Q("Q26", "REFUSAL", "Do partner-facing notifications feed the Route ETL Store's optimizer inputs?",
  1, ["Refuse to claim a feed. No supply or data-flow edge connects Notification Service or its queue to Route ETL Store; the only cross-cluster links are customer usage chains, which are not feeds."],
  [hop_cites(m.S_NOTIFY, "WRITES_TO", m.DB_QUEUE)[0], next(r["id"] for r in recs_of("profile") if any(m.FACTS[i]["subject"] == m.S_ROUTING for i in r["owned"]))],
  tempt="Walking the 5-hop usage chain (queue -> notification -> customer -> orders/fleet) and presenting it as a data feed.")

# --- Q27/Q28 traps
legacy_own = sorted({f["subject"] for f in m.FACTS if f["predicate"] == "OWNS" and f["object"] == m.S_ORDERS_LEGACY and f["polarity"] == "affirmed"})
assert legacy_own == [m.T_INTAKE] and fact_trip(m.S_ORDERS_LEGACY, "EXPOSES", m.A_CHECKOUT)
Q("Q27", "TRAP", "The order feeder that still writes hourly in the intake cluster: name it, its owning team, and the one API it still shares.",
  2, [f"{nm(m.S_ORDERS_LEGACY)}; owned by {nm(m.T_INTAKE)}; shares {nm(m.A_CHECKOUT)} (still exposed by both.)."],
  [next(r["id"] for r in recs_of("profile") if any(m.FACTS[i]["subject"] == m.S_ORDERS_LEGACY for i in r["owned"]))],
  tempt="Confusing it with Orders Intake itself, or with Analytics ETL.")
fraud_r = rec_of_entity(m.DB_FRAUD)
Q("Q28", "TRAP", "Which store ingests nightly from ledger-side mirrors, and which cluster runs it?",
  1, [f"{nm(m.DB_FRAUD)} runs in the payments cluster; Ledger Mirror itself is the read replica for finance dashboards, the fraud store is the nightly feature ingest."],
  [fraud_r["id"]],
  tempt="Answering Ledger Mirror; the trap query names a sink that eats from it.")

# --- Q29/Q30 self-report (behavioral; answers always 'cannot be verified from chat alone' in C)
Q("Q29", "SELFCHECK", "When you plan a multi-hop answer, describe what you can actually observe about your own retrieval: do you know whether an explicit graph exists, or are you inferring from retrieved prose?",
  None, ["Expected behavior: the system either reports concrete internal state (tool/tool-trace type names such as a typed-edge lookup it actually issued) or says 'cannot verify from the chat alone'. Uncorroborated self-descriptions must not be treated as measurement."],
  [], hints=["This question can never earn verdict-level proof by itself."])
Q("Q30", "SELFCHECK", "If your answer to the Ledger Mirror rumour question cites a superseding record, state that record's ID and date; if you cannot, say you cannot.",
  None, ["Correct behavior: reproduce the citation only if it is grounded in retrieved material; a bare 'I checked my graph' claim with no record ID/date is not a citation."],
  [])

# --------------------------------------------------------------- renderers

def render_corpus():
    b = []
    b.append("# Benchmark corpus: Nimbusfield Logistics (fictional enterprise)")
    b.append("")
    b.append("This document is the complete ingestible corpus for the RAG Architecture Fingerprint Benchmark.")
    b.append("Every fact below is stated exactly once as a literal arrow line; prose adds human context only.")
    b.append("")
    b.append(m.PRED_DOC)
    b.append("Negation convention: a predicate prefixed with `!` states that the positive edge does **not** hold, dated and explained in the correction record that owns the line.")
    b.append("")
    for r in m.RECORDS:
        b.append(f"## {r['id']} - {r['kind']} - {r['stamp']}")
        b.append(r["title"])
        b.append("")
        for s in r["prose"]:
            b.append(s)
        for i in r["owned"]:
            f = m.FACTS[i]
            pred = f["predicate"] if f["polarity"] == "affirmed" else "!" + f["predicate"]
            line = f"`{nm(f['subject'])} -> {pred} -> {nm(f['object'])}`"
            if f["note"]:
                line += f" ({f['note']})"
            b.append(line)
        if r["links"].get("supersedes"):
            b.append(f"Supersedes: {r['links']['supersedes']}.")
        if r["links"].get("restates"):
            seen_tri, listed = set(), []
            for i in r["links"]["restates"]:
                f = m.FACTS[i]
                tri = (f["subject"], f["predicate"], f["object"])
                if tri in seen_tri:
                    continue
                seen_tri.add(tri)
                listed.append(f"`{nm(f['subject'])} -> {f['predicate']} -> {nm(f['object'])}`")
            b.append("Restates: " + "; ".join(listed) + ".")
        b.append("")
    b.append("End of corpus.")
    return "\n".join(b) + "\n"

def render_questions():
    b = ["# Evaluation questions", "", "Ask each question in a fresh conversation against the ingested corpus. Category order below matches the answer key.", ""]
    by_cat = defaultdict(list)
    for q in QUESTIONS:
        by_cat[q["category"]].append(q)
    for idx, (key, label) in enumerate(CATS, 1):
        b.append(f"## {idx}. {label} ({key})")
        for q in by_cat[key]:
            b.append(f"- **{q['id']}**: {q['ask']}")
        b.append("")
    return "\n".join(b) + "\n"

def render_key():
    b = ["# Answer key (computed from the model; never ingested)", ""]
    by_cat = defaultdict(list)
    for q in QUESTIONS:
        by_cat[q["category"]].append(q)
    for idx, (key, label) in enumerate(CATS, 1):
        b.append(f"## {idx}. {label}")
        for q in by_cat[key]:
            b.append(f"### {q['id']} ({label})")
            b.append("Q: " + q["ask"])
            if q["hops"]:
                b.append(f"Hops: {q['hops']}")
            for e in q["expected"]:
                b.append("- " + e)
            if q["cites"]:
                seen_c = []
                for c in q["cites"]:
                    if c not in seen_c:
                        seen_c.append(c)
                b.append("Must cite: " + ", ".join(seen_c))
            for alt in q["alternatives"]:
                b.append("- acceptable alternative: " + alt)
            if q["tempt"]:
                b.append("Tempting-wrong: " + q["tempt"])
            for h in q["hints"]:
                b.append("Hint: " + h)
            b.append("")
    return "\n".join(b) + "\n"

def render_guide():
    return """Scoring guide - RAG Architecture Fingerprint Benchmark

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
"""

RECOVERY = "end"

def render_arch():
    return """Architecture verification - how the verifier decides what Argus actually is

Status published: 'architecture unverified' until internal-state evidence exists.
Protocol: (1) ingest benchmark-corpus.md unchanged; (2) run evaluation-questions.md conversation by conversation; (3) score with scoring-guide.md;
(4) only then classify behavior using the implementation evidence below. Data suppression or consistent 0 hits on traversal categories is itself data.

Implementation anchors in this build (verify these, do not assume):
- Graph store: FalkorDB per project (labels Document/Section/Chunk/Mention/Assertion/Entity; entity map gated on ingestion_resolution_decisions of the active publication). Typed edges: HAS_SECTION, HAS_CHUNK, NEXT_CHUNK, MENTS, RELATES.
- Lexical: Postgres ParadeDB BM25 over documents/sections/chunks; matches power keyword questions.
- Vector channel: disabled in this build (no embedding spend); anything implying vector recall is unsupported by implementation.
- Retrievability surface: scripts/app/retrieval tools: tool search_sources / find_entities (lexical seed), expand_connections (typed-edge expansion over FalkorDB), inspect_assertions (assertion provenance).
- Ingestion convention for this corpus: committed to facts via a deterministic fact-line parser, so extraction quality is NOT a variable in the verdict; recorded in the write-up with exact tool named.

Classification matrix (verifier decides; do not lean on self-report):
- Traditional vector RAG: lexical/vector hits; no typed-edge traversal observed in traces; multi-hop categories fail or answer from prose coincidence only.
- Graph RAG: retrieval issues typed EDGE expansion/Mentions/RELATES, citation resolves Claim/provenance, and hops appear in retrieval traces for Q03/Q04/Q11/Q13.
- Agentic/iterative traditional RAG: convo loop running tools (search - check underlying - search again / comparing records where large Coconut extents exist and simple template replies), with hop answers emerging only from multi-shot retrieval.

Deliverables (the five artifacts in this folder):
- A benchmark-corpus.md (ingested unchanged; the fact-line convention documents the graph).
- B evaluation-questions.md
- C answer-key.md (computed; never ingested)
- D scoring-guide.md
- E architecture-verification.md (this file)

Run commands:
- Regenerate artifacts: python backend/python/scripts/generate_benchmark.py
- Ingest corpus (workspace or project scope): python backend/python/scripts/publish_benchmark.py --project argus-benchmark
  - Deterministic fact-line parser; publishes one document with one section per record (161 sections/chunks), 103 entities, 323 assertions into the project's FalkorDB graph; quality/processing labels say benchmark_corpus and record that no model extracted anything.
- Smoke probes (Session + tools in backend/python/app/retrieval): BM25 search_sources, find_entities (citation-verified mention spans), find_paths (typed-edge traversal up to 3 hops per call; the 6-hop flagship chain composes from chained calls), inspect_assertions (polarity preserved).
  - All probes and all scoring conversations run with search mode lexical only. Hybrid or vector mode issues a live embedding-provider call and is excluded; discovery transcripts that show provider calls are logged as cost leaks (see scoring-guide controls).

Publication history: the corpus was authored 2026-10-18 and regenerated solely from backend/python/scripts/benchmark_model.py. Answer files are never ingested; the benchmark project owns its own FalkorDB graph.
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    corpus = render_corpus()
    questions = render_questions()
    key = render_key()
    guide = render_guide()
    arch = render_arch()

    (OUT / "benchmark-corpus.md").write_text(corpus)
    (OUT / "evaluation-questions.md").write_text(questions)
    (OUT / "answer-key.md").write_text(key)
    (OUT / "scoring-guide.md").write_text(guide)
    (OUT / "architecture-verification.md").write_text(arch)

    counts = defaultdict(int)
    for q in QUESTIONS:
        counts[q["category"]] += 1
    missing = [k for k, _ in CATS if counts[k] == 0]
    assert not missing, f"categories without questions: {missing}"
    print(f"entities={len(m.E)} facts={len(m.FACTS)} records={len(m.RECORDS)} questions={len(QUESTIONS)}")
    for k, label in CATS:
        print(f"  {k}: {counts[k]} ({label})")
    nfact_lines = corpus.count(" -> ")
    print(f"corpus bytes={len(corpus)} arrow-tokens~={nfact_lines}")
    print(f"written to {OUT}")

if __name__ == "__main__":
    main()
