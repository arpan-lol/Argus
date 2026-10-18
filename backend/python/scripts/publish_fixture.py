import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from falkordb import FalkorDB
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.database import connection, migrate
from app.ingestion.config import fingerprint, processing_config
from app.ingestion.publication import semantic_graph_name
from app.services.corpus import publish_document


QUALITY = {"fallbackChunks": 0, "quality": "manual_fixture", "warnings": ["This source was published directly by scripts/publish_fixture.py without the ingestion pipeline; entities and assertions were authored by hand."], "sourceCoverage": None}
PROCESS = {"method": "manual_fixture", "llmVerified": False, "fallback": False, "spanStatus": "exact", "label": "Authored directly by scripts/publish_fixture.py; no ingestion, parsing or model processing was run."}
HN = dict(name="hydrothermal synthesis", type="Method", description="Synthetic fixture preparation step used for retrieval testing.")
CARB = dict(name="activated carbon", type="Product", description="Synthetic comparator sorbent used for retrieval testing.")
SPECS = [
 {
  "slug": "manual-fixture-mof-bpa", "title": "Synthetic fixture: MOF-BP-1 and bisphenol A", "sourceUrl": None, "join": "space", "authors": ["Surrogate Author Alfa"], "processedAt": "2026-10-18T00:00:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Fixture text", [0, 1])],
  "paragraphs": [
   "Synthetic fixture prepared for Argus retrieval testing without the ingestion pipeline. MOF-BP-1 adsorbed 91 percent of bisphenol A from water within two hours at pH 6.5 and 25 degrees Celsius. Activated carbon adsorbed a comparable share of bisphenol A under identical conditions in this same fixture.",
   "All statements in this document were authored for testing and were not measured in any laboratory. Hydrothermal synthesis did not change the adsorption capacity of MOF-BP-1 in this authored account, and no real publication supports this fixture.",
  ],
  "entities": {
   "mof": {"name": "MOF-BP-1", "type": "Product", "description": "Synthetic fixture placeholder material used for retrieval testing."},
   "bpa": {"name": "bisphenol A", "type": "Concept", "description": "Synthetic fixture placeholder chemical used for retrieval testing."},
   "carb": {"name": "Activated carbon", "type": "Product", "description": "Synthetic fixture comparator material used for retrieval testing."},
   "hydr": {"name": "Hydrothermal synthesis", "type": "Method", "description": "Synthetic fixture preparation step used for retrieval testing."},
  },
  "assertions": [
   {"subject": "mof", "predicate": "adsorbs", "object": "bpa", "quote": "MOF-BP-1 adsorbed 91 percent of bisphenol A from water within two hours at pH 6.5 and 25 degrees Celsius", "conditions": ["two hour contact", "pH 6.5", "25 degrees Celsius"], "polarity": "affirmed"},
   {"subject": "carb", "predicate": "adsorbs", "object": "bpa", "quote": "Activated carbon adsorbed a comparable share of bisphenol A under identical conditions", "conditions": ["identical fixture conditions"], "polarity": "affirmed"},
   {"subject": "hydr", "predicate": "changes", "object": "mof", "quote": "Hydrothermal synthesis did not change the adsorption capacity of MOF-BP-1 in this authored account", "conditions": ["synthetic fixture text"], "polarity": "negated"},
  ],
 },
 {
  "slug": "corpus-mof-9x-bpa", "title": "Synthetic fixture: MOF-BP-9X bisphenol A uptake", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Beta", "Surrogate Author Gamma"], "processedAt": "2026-02-03T09:00:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Uptake results", [0]), ("Limitations", [1])],
  "paragraphs": [
   "Synthetic fixture authored for retrieval testing. MOF-BP-9X removed 83 percent of bisphenol A from water within ninety minutes at pH 7 and 22 degrees Celsius, and activated carbon removed 61 percent under the same batch conditions. Uptake dropped to 54 percent when competing sulfate was present at ten milligrams per liter.",
   "These uptake values were invented for Argus retrieval testing and were never measured in a laboratory. The effect of sulfate competition in this fixture is a plausible guess and not an experimental result.",
  ],
  "entities": {
   "mof9": {"name": "MOF-BP-9X", "type": "Product", "description": "Synthetic sorbent placeholder used for retrieval testing."},
   "bpa": {"name": "bisphenol A", "type": "Concept", "description": "Synthetic placeholder analyte used for retrieval testing."},
   "carb": {"name": "activated carbon", "type": "Product", "description": "Synthetic comparator sorbent used for retrieval testing."},
  },
  "assertions": [
   {"subject": "mof9", "predicate": "removes", "object": "bpa", "quote": "MOF-BP-9X removed 83 percent of bisphenol A from water within ninety minutes at pH 7 and 22 degrees Celsius", "conditions": ["ninety minutes", "pH 7", "22 degrees Celsius"], "polarity": "affirmed"},
   {"subject": "carb", "predicate": "removes", "object": "bpa", "quote": "activated carbon removed 61 percent under the same batch conditions", "conditions": ["same batch conditions"], "polarity": "affirmed"},
  ],
 },
 {
  "slug": "corpus-biochar-bpa", "title": "Synthetic fixture: rice husk biochar and bisphenol A", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Delta"], "processedAt": "2026-03-11T13:00:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Biochar results", [0]), ("Notes", [1])],
  "paragraphs": [
   "Synthetic fixture for retrieval testing. Rice husk biochar heated to 700 degrees Celsius adsorbed 78 percent of bisphenol A from water after four hours at pH 6.5. A commercial batch of activated carbon reached 95 percent in the same authored comparison. Freundlich isotherms were invented to keep the narrative tidy and describe no real batch data.",
   "The isotherm parameters in this document are fictional shorthand. Laboratory conditions were not simulated. No instrument was involved.",
  ],
  "entities": {
   "bio": {"name": "rice husk biochar", "type": "Product", "description": "Synthetic sorbent placeholder used for retrieval testing."},
   "bpa": {"name": "bisphenol A", "type": "Concept", "description": "Synthetic placeholder analyte used for retrieval testing."},
   "carb": {"name": "activated carbon", "type": "Product", "description": "Synthetic comparator sorbent used for retrieval testing."},
  },
  "assertions": [
   {"subject": "bio", "predicate": "adsorbs", "object": "bpa", "quote": "Rice husk biochar heated to 700 degrees Celsius adsorbed 78 percent of bisphenol A from water after four hours at pH 6.5", "conditions": ["700 degrees Celsius pyrolysis", "four hours", "pH 6.5"], "polarity": "affirmed"},
  ],
 },
 {
  "slug": "corpus-graphite-bpa-negative", "title": "Synthetic fixture: graphite powder failed to take up bisphenol A", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Epsilon", "Surrogate Author Zeta"], "processedAt": "2026-04-22T10:00:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Failed trial", [0]), ("Why this matters", [1])],
  "paragraphs": [
   "Synthetic fixture for retrieval testing with a negative result. Six hours of graphite powder circulation in a pH 7 water batch did not take up a measurable share of bisphenol A and repeatedly returned an invented background concentration near the starting value.",
   "Negative results keep retrieval rounds honest. A reader looking for uptake should see this fixture as a distractor that answers no to uptake for the analyte in question.",
  ],
  "entities": {
   "gr": {"name": "graphite powder", "type": "Product", "description": "Synthetic failed sorbent placeholder used for retrieval testing."},
   "bpa": {"name": "bisphenol A", "type": "Concept", "description": "Synthetic placeholder analyte used for retrieval testing."},
  },
  "assertions": [
   {"subject": "gr", "predicate": "takes up", "object": "bpa", "quote": "Six hours of graphite powder circulation in a pH 7 water batch did not take up a measurable share of bisphenol A", "conditions": ["six hours", "pH 7"], "polarity": "negated"},
  ],
 },
 {
  "slug": "corpus-bpa-panel", "title": "Synthetic fixture: surrogate panel record on bisphenol A intake", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Eta"], "processedAt": "2025-11-30T08:00:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Panel record", [0]), ("Unresolved items", [1])],
  "paragraphs": [
   "Synthetic fixture styled as a surrogate regulatory panel record. The panel set a tolerable daily intake of 0.05 milligrams per kilogram for bisphenol A and listed uncertainty about neonatal exposure windows.",
   "This record was authored for Argus retrieval testing. No real committee met, no real intake threshold exists here, and the document deliberately avoids uptake claims.",
  ],
  "entities": {
   "bpa": {"name": "bisphenol A", "type": "Concept", "description": "Synthetic placeholder analyte used for retrieval testing."},
  },
  "assertions": [],
 },
 {
  "slug": "corpus-bpa-method", "title": "Synthetic fixture: LC-MS method note for bisphenol A in water", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Theta"], "processedAt": "2026-01-19T14:30:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Method note", [0]), ("Caveats", [1])],
  "paragraphs": [
   "Synthetic fixture about an analytical method, not a treatment trial. The note pairs liquid chromatography with tandem mass spectrometry and would take 0.2 nanograms per liter as a method floor for bisphenol A in tap water when extraction concentrates 250 milliseconds through a cartridge.",
   "No recovery experiment backs the floor value; the fixture only checks whether retrieval separates method notes from uptake studies.",
  ],
  "entities": {
   "bpa": {"name": "bisphenol A", "type": "Concept", "description": "Synthetic placeholder analyte used for retrieval testing."},
   "lcms": {"name": "liquid chromatography", "type": "Method", "description": "Synthetic placeholder analytical method used for retrieval testing."},
  },
  "assertions": [],
 },
 {
  "slug": "corpus-bpa-packaging", "title": "Synthetic fixture: migration report for bisphenol A packaging", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Iota"], "processedAt": "2026-05-06T11:00:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Migration report", [0]), ("Scope limits", [1])],
  "paragraphs": [
   "Synthetic fixture about migration from packaging, not sorbent performance. Polycarbonate bottles stored a week above 60 degrees Celsius released up to 0.9 micrograms of bisphenol A per liter in this invented account, and bisphenol S released a fifth of that amount.",
   "Migration numbers here describe neither removal nor adsorption; the fixture exists to check distractor ranking when only packaging vocabulary is present.",
  ],
  "entities": {
   "bpa": {"name": "bisphenol A", "type": "Concept", "description": "Synthetic placeholder analyte used for retrieval testing."},
   "bps": {"name": "bisphenol S", "type": "Concept", "description": "Synthetic placeholder substitute compound used for retrieval testing."},
  },
  "assertions": [],
 },
 {
  "slug": "corpus-urban-roofs", "title": "Synthetic fixture: white roofs and summer warmth", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Kappa"], "processedAt": "2026-06-14T07:45:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Roof outcomes", [0]), ("Honest labels", [1])],
  "paragraphs": [
   "Synthetic fixture about reflective roof paint, unrelated to water pollutants. Blocks that had residential roofs repainted white cooled about 1.8 degrees Celsius at noon in the made-up district, and albedo rose from 0.12 to 0.74.",
   "English speakers call this a cooling study; the temperatures are invented for retrieval testing and no city council approved anything.",
  ],
  "entities": {
   "albedo": {"name": "albedo", "type": "Concept", "description": "Synthetic placeholder reflectivity term used for retrieval testing."},
  },
  "assertions": [],
 },
 {
  "slug": "corpus-espresso-grind", "title": "Synthetic fixture: espresso grind dialogs", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Lambda"], "processedAt": "2026-07-02T16:00:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Grind search", [0]), ("About the notes", [1])],
  "paragraphs": [
   "Synthetic fixture about dialing in an espresso shot. A 210 micrometer grind at 19 grams ran 27 seconds and tasted hollow in the invented log, then a bump to 230 micrometers held 31 seconds with a rounder cup.",
   "Every log line here is fiction for retrieval testing. The crema judgments were never paired with a tasting panel.",
  ],
  "entities": {
   "grind": {"name": "grind", "type": "Product", "description": "Synthetic placeholder coffee setting used for retrieval testing."},
  },
  "assertions": [],
 },
 {
  "slug": "corpus-cycling-brakes", "title": "Synthetic fixture: brake dust complaints on a hill road", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Mu"], "processedAt": "2026-02-27T12:20:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Complaint log", [0]), ("Fiction reminder", [1])],
  "paragraphs": [
   "Synthetic fixture about brake dust on a hill road. Pads rich in copper and iron threw about 41 milligrams per kilometer of particles onto the descent in the fabricated tally, while organic pads cut the number only slightly.",
   "The tally was written to test retrieval ranking against road vocabulary. No municipality measured anything.",
  ],
  "entities": {
   "copper": {"name": "copper", "type": "Concept", "description": "Synthetic placeholder brake pad element used for retrieval testing."},
  },
  "assertions": [],
 },
 {
  "slug": "corpus-zinc-ports", "title": "Synthetic fixture: zinc in port sediment", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Nu", "Surrogate Author Xi"], "processedAt": "2026-03-29T09:10:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Sediment tally", [0]), ("Invented caution", [1])],
  "paragraphs": [
   "Synthetic fixture about a surrogate port survey. Harbor sediment held 120 milligrams of zinc per kilogram near the slips in the invented survey and dropped toward 48 milligrams per kilogram away from ship traffic.",
   "The survey is fiction for retrieval testing. Zinc here is unrelated to any pollutant-uptake storyline.",
  ],
  "entities": {
   "zinc": {"name": "zinc", "type": "Concept", "description": "Synthetic placeholder sediment element used for retrieval testing."},
  },
  "assertions": [],
 },
 {
  "slug": "corpus-office-humidity", "title": "Synthetic fixture: towel room humidity grumbles", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Omicron"], "processedAt": "2026-01-08T17:40:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Facility grumble", [0]), ("Label", [1])],
  "paragraphs": [
   "Synthetic fixture about a towel room. Fans ran while relative humidity stayed at 92 percent overnight and a faint mildew smell persisted in the invented facility note until a new vent moved three liters per second.",
   "Nothing scientific is claimed. Rooms, towels and smells are placeholders for retrieval testing.",
  ],
  "entities": {
   "humidity": {"name": "relative humidity", "type": "Concept", "description": "Synthetic placeholder facility variable used for retrieval testing."},
  },
  "assertions": [],
 },
 {
  "slug": "corpus-glacier-terminus", "title": "Synthetic fixture: glacier retreat dispute", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Pi"], "processedAt": "2026-04-15T06:30:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Retreat argument", [0]), ("Fiction note", [1])],
  "paragraphs": [
   "Synthetic fixture about a mountain glacier. Two observers disputed whether the terminus receded 4.2 percent per year or 1.1 percent per year, and a third invented an east lobe that slowed to 0.3 percent.",
   "Observers and rates are fictional for retrieval testing and no satellite mission is referenced.",
  ],
  "entities": {
   "terminus": {"name": "terminus", "type": "Concept", "description": "Synthetic placeholder glacier feature used for retrieval testing."},
  },
  "assertions": [],
 },
 {
  "slug": "corpus-led-flicker", "title": "Synthetic fixture: LED flicker and tired eyes", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Rho", "Surrogate Author Sigma"], "processedAt": "2026-05-21T10:05:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Flicker note", [0]), ("Reminder", [1])],
  "paragraphs": [
   "Synthetic fixture about screen and lamp flicker. A 240 hertz pulse width modulation cycle split eye comfort readings in the fabricated office survey, and a dimmer dropped modulation depth from 41 percent to 6 percent.",
   "Lamp inventories and eye comfort ratings are placeholders for retrieval testing. Nobody wore electrodes.",
  ],
  "entities": {
   "pwm": {"name": "pulse width modulation", "type": "Method", "description": "Synthetic placeholder dimming method used for retrieval testing."},
  },
  "assertions": [],
 },
 {
  "slug": "corpus-soil-lime", "title": "Synthetic fixture: farm field liming adjustment", "sourceUrl": None, "join": "blank", "authors": ["Surrogate Author Tau"], "processedAt": "2026-08-12T08:55:00Z",
  "coverage": "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements",
  "sections": [("Field result", [0]), ("Fiction marker", [1])],
  "paragraphs": [
   "Synthetic fixture about field liming. A lime spread of three tonnes per hectare lifted a fabricated soil pH from 5.2 to 6.4, and clover coverage edged upward the following season in the invented notes.",
   "Field trials here are fiction for retrieval testing and were never run.",
  ],
  "entities": {
   "lime": {"name": "lime", "type": "Product", "description": "Synthetic placeholder soil amendment used for retrieval testing."},
  },
  "assertions": [],
 },
]


def canonical(graph_name, key, spec):
    entity = spec["entities"][key]
    return "entity:" + fingerprint([graph_name, entity["name"].strip().lower(), entity["type"].strip().lower()]), entity


def spans(chunk, quote):
    cursor = 0
    result = []
    while True:
        index = chunk["text"].find(quote, cursor)
        if index < 0:
            break
        result.append({"chunkStart": index, "chunkEnd": index + len(quote), "startOffset": chunk["startOffset"] + index, "endOffset": chunk["startOffset"] + index + len(quote), "offsetUnit": "unicode_code_point"})
        cursor = index + 1
    return result


def stage_text(spec, text, digest):
    base = settings.data_dir / "fixtures" / (spec["slug"] + ".md")
    base.parent.mkdir(parents=True, exist_ok=True)
    base.write_text(text, encoding="utf-8")
    original_dir = settings.data_dir / "originals" / digest[:2]
    original_dir.mkdir(parents=True, exist_ok=True)
    original = original_dir / (digest + "-" + spec["slug"] + ".md")
    if not original.exists() or original.read_bytes() != base.read_bytes():
        original.write_bytes(base.read_bytes())
    return original


def build(text, config, spec):
    revision = fingerprint([text])
    version = fingerprint(config)
    graph_name = semantic_graph_name(config)
    paragraph_spans = []
    cursor = 0
    for paragraph in spec["paragraphs"]:
        paragraph_spans.append((cursor, cursor + len(paragraph)))
        cursor += len(paragraph) + (1 if spec["join"] == "space" else 2)
    section_chunks = [set(indexes) for _, indexes in spec["sections"]]
    chunk_to_section = {}
    for ordinals, used in enumerate(section_chunks):
        for index in used:
            chunk_to_section[index] = ordinals
    chunks = []
    chunk_section = []
    for ordinal, (left, right) in enumerate(paragraph_spans):
        section_index = chunk_to_section[ordinal]
        section_id = "section:" + fingerprint([section_index, graph_name, spec["slug"]])
        chunks.append({"id": "chunk:" + fingerprint([chunk_scope(config, spec), left, right]), "ordinal": ordinal, "text": text[left:right], "startOffset": left, "endOffset": right, "tokenCount": None, "offsetUnit": "unicode_code_point", "blockOrdinals": [ordinal]})
        chunk_section.append((section_id, ordinal))
    sections = []
    for ordinal, (title, indexes) in enumerate(spec["sections"], 1):
        first, last = indexes[0], indexes[-1]
        sections.append({"id": "section:" + fingerprint([ordinal - 1, graph_name, spec["slug"]]), "title": title, "ordinal": ordinal, "startOffset": paragraph_spans[first][0], "endOffset": paragraph_spans[last][1]})
    sections_merged = [{**section, "documentId": section["id"], "locationKind": "source", "sourceLocation": None} for section in sections]
    mentions = []
    for key, entity in spec["entities"].items():
        for chunk in chunks:
            found = spans(chunk, entity["name"])
            if not found:
                continue
            primary = found[0]
            mentions.append({"id": "mention:" + fingerprint([chunk["id"], key]), "chunkId": chunk["id"], "key": key, "quote": entity["name"], "startOffset": primary["startOffset"], "endOffset": primary["endOffset"], "sourceSpans": found, "sourceSpanStatus": "multiple_occurrences" if len(found) > 1 else "exact"})
    assertions = []
    for ordinal, assertion in enumerate(spec["assertions"], 1):
        holders = [chunk for chunk in chunks if spans(chunk, assertion["quote"])]
        if not holders:
            raise SystemExit("Assertion quote not found in text: " + spec["slug"] + " :: " + assertion["quote"][:60])
        holder = holders[0]
        primary = spans(holder, assertion["quote"])[0]
        all_spans = spans(holder, assertion["quote"])
        for key in (assertion["subject"], assertion["object"]):
            if key not in spec["entities"]:
                raise SystemExit("Unknown assertion participant " + key + " in " + spec["slug"])
        assertions.append({**assertion, "id": "assertion:" + fingerprint([holder["id"], ordinal, assertion["predicate"], assertion["quote"]]), "chunkId": holder["id"], "startOffset": primary["startOffset"], "endOffset": primary["endOffset"], "sourceSpans": all_spans, "sourceSpanStatus": "exact" if len(all_spans) == 1 else "multiple_occurrences"})
    return revision, version, graph_name, sections_merged, chunks, chunk_section, mentions, assertions


def chunk_scope(config, spec):
    return ["fixture", spec["slug"], config.get("semanticGraph"), fingerprint(config)]


def publish(project_id, spec):
    text = ("" if spec["paragraphs"][0] else "") + spec["paragraphs"][0]
    for paragraph in spec["paragraphs"][1:]:
        text += (" " if spec["join"] == "space" else "\n\n") + paragraph
    quality = {**QUALITY, "sourceCoverage": spec["coverage"]}
    config = processing_config(project_id)
    revision, version, graph_name, sections, chunks, chunk_section, mentions, assertions = build(text, config, spec)
    section_by_id = {section["id"]: section for section in sections}
    source_id = "source:" + fingerprint([config.get("projectId") or "workspace", spec["slug"]])
    digest = fingerprint([text])
    original = stage_text(spec, text, digest)
    job_id = "job:" + fingerprint([source_id, revision, version])
    payload_chunks = []
    for chunk, (section_id, _) in zip(chunks, chunk_section, strict=True):
        section = section_by_id[section_id]
        payload_chunks.append({**chunk, "documentId": source_id, "revisionId": revision, "processingVersion": version, "sectionId": section["id"], "sectionIds": [section["id"]], "sectionTitle": section["title"], "sourceUrl": None, "locationKind": "source", "extractionMetadata": PROCESS, "authors": spec["authors"], "processedAt": spec["processedAt"], "structuralRank": chunk["ordinal"]})
    payload = {
        "id": source_id, "revisionId": revision, "processingVersion": version, "rawPath": str(original), "title": spec["title"], "text": text, "textLength": len(text),
        "sections": sections, "chunks": payload_chunks,
        "entities": [{"id": canonical(graph_name, key, spec)[0], "label": entity["name"], "type": entity["type"], "extractionMethod": PROCESS["method"], "llmVerified": False, "mention_count": sum(1 for mention in mentions if mention["key"] == key)} for key, entity in spec["entities"].items()],
        "sourceUrl": spec["sourceUrl"], "offsetUnit": "unicode_codepoint",
        "blocks": [], "normalization": {"method": "manual_fixture", "steps": ["fixture"]},
        "extractionQuality": quality, "warnings": quality["warnings"],
        "extractionBoundary": "This is a synthetic fixture; entities and assertions were authored manually and no model processed the text.",
        "synthetic": True, "fixture": "scripts/publish_fixture.py", "authors": spec["authors"], "processedAt": spec["processedAt"],
    }
    counts = {"documents": 1, "sections": len(sections), "chunks": len(chunks), "entities": len(spec["entities"]), "mentions": len(mentions), "assertions": len(assertions), "graph": graph_name, **quality}
    normalize = {"text": text, "metadata": {"synthetic": True, "authors": spec["authors"], "processedAt": spec["processedAt"], "stage": "fixture"}, "blocks": [], "normalization": {"method": "manual_fixture", "steps": ["fixture"]}}
    graph = FalkorDB(host=settings.falkor_host, port=settings.falkor_port).select_graph(graph_name)
    for label, property_name in (("Document", "id"), ("SourceRevision", "sourceId"), ("SourceRevision", "id"), ("Section", "id"), ("Section", "documentId"), ("Chunk", "id"), ("Chunk", "documentId"), ("Chunk", "jobId"), ("Entity", "id"), ("Entity", "label"), ("Mention", "id"), ("Mention", "documentId"), ("Assertion", "id"), ("Assertion", "documentId"), ("Assertion", "jobId")):
        try:
            graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{property_name})")
        except Exception as error:
            if "already" not in str(error).lower() and "exists" not in str(error).lower():
                raise
    graph.query("MERGE (d:Document {id:$id}) SET d.title=$title MERGE (r:SourceRevision {id:$job}) SET r.sourceId=$id,r.revision=$revision,r.processingVersion=$version,r.active=false MERGE (d)-[:HAS_REVISION]->(r)", {"id": source_id, "job": job_id, "title": spec["title"], "revision": revision, "version": version})
    for key, entity in spec["entities"].items():
        entity_id, _ = canonical(graph_name, key, spec)
        graph.query("MERGE (e:Entity {id:$id}) SET e.label=$label,e.type=$type,e.description=$description,e.sourceId=$source", {"id": entity_id, "label": entity["name"], "type": entity["type"], "description": entity["description"], "source": source_id})
    for section in sections:
        graph.query("MATCH (d:Document {id:$document}),(r:SourceRevision {id:$job}) MERGE (s:Section {id:$id}) SET s.documentId=$document,s.jobId=$job,s.title=$title,s.startOffset=$start,s.endOffset=$end,s.active=false MERGE (d)-[:HAS_SECTION]->(s) MERGE (r)-[:HAS_SECTION]->(s)", {"document": source_id, "job": job_id, "id": section["id"], "title": section["title"], "start": section["startOffset"], "end": section["endOffset"]})
    previous = None
    for chunk, (section_id, _) in zip(chunks, chunk_section, strict=True):
        graph.query("MATCH (s:Section {id:$section}) MERGE (c:Chunk {id:$id}) SET c.documentId=$document,c.sectionId=$section,c.jobId=$job,c.text=$text,c.ordinal=$ordinal,c.startOffset=$start,c.endOffset=$end,c.extractionMethod=$method,c.llmVerified=$verified,c.extractionFallback=$fallback,c.active=false MERGE (s)-[:HAS_CHUNK]->(c)", {"section": section_id, "id": chunk["id"], "document": source_id, "job": job_id, "text": chunk["text"], "ordinal": chunk["ordinal"], "start": chunk["startOffset"], "end": chunk["endOffset"], "method": PROCESS["method"], "verified": False, "fallback": False})
        if previous:
            graph.query("MATCH (a:Chunk {id:$a}),(b:Chunk {id:$b}) MERGE (a)-[:NEXT_CHUNK {id:$relation}]->(b)", {"a": previous, "b": chunk["id"], "relation": fingerprint([previous, chunk["id"]])})
        previous = chunk["id"]
    for mention in mentions:
        entity_id, entity = canonical(graph_name, mention["key"], spec)
        graph.query("MATCH (c:Chunk {id:$chunk}),(e:Entity {id:$entity}) MERGE (m:Mention {id:$mention}) SET m.jobId=$job,m.documentId=$document,m.text=$quote,m.startOffset=$start,m.endOffset=$end,m.sourceSpans=$source_spans,m.sourceSpanStatus=$status,m.sourceSpanAmbiguous=$ambiguous,m.extractionMethod=$method,m.llmVerified=$verified,m.active=false MERGE (c)-[:HAS_MENTION]->(m) MERGE (m)-[:RESOLVED_TO]->(e) MERGE (c)-[:MENTIONS]->(e)", {"chunk": mention["chunkId"], "entity": entity_id, "mention": mention["id"], "job": job_id, "document": source_id, "quote": mention["quote"], "start": mention["startOffset"], "end": mention["endOffset"], "source_spans": json.dumps(mention["sourceSpans"]), "status": mention["sourceSpanStatus"], "ambiguous": mention["sourceSpanStatus"] == "multiple_occurrences", "method": PROCESS["method"], "verified": False})
    for record in assertions:
        graph.query("MATCH (c:Chunk {id:$chunk}),(s:Entity {id:$subject}),(o:Entity {id:$object}) MERGE (a:Assertion {id:$id}) SET a.jobId=$job,a.documentId=$document,a.predicate=$predicate,a.quote=$quote,a.conditions=$conditions,a.polarity=$polarity,a.startOffset=$start,a.endOffset=$end,a.sourceSpans=$source_spans,a.sourceSpanStatus=$status,a.extractionMethod=$method,a.llmVerified=$verified,a.active=false MERGE (a)-[:SUPPORTED_BY]->(c) MERGE (a)-[:SUBJECT]->(s) MERGE (a)-[:OBJECT]->(o)", {"chunk": record["chunkId"], "id": record["id"], "job": job_id, "document": source_id, "predicate": record["predicate"], "quote": record["quote"], "conditions": json.dumps(record["conditions"]), "polarity": record["polarity"], "start": record["startOffset"], "end": record["endOffset"], "source_spans": json.dumps(record["sourceSpans"]), "status": record["sourceSpanStatus"], "method": PROCESS["method"], "verified": False, "subject": canonical(graph_name, record["subject"], spec)[0], "object": canonical(graph_name, record["object"], spec)[0]})
        graph.query("MATCH (s:Entity {id:$subject}),(o:Entity {id:$object}) MERGE (s)-[r:RELATES {assertionId:$id}]->(o) SET r.predicate=$predicate,r.jobId=$job,r.sourceId=$source,r.active=false", {"id": record["id"], "subject": canonical(graph_name, record["subject"], spec)[0], "object": canonical(graph_name, record["object"], spec)[0], "predicate": record["predicate"], "job": job_id, "source": source_id})
    with connection() as conn:
        conn.execute("INSERT INTO ingestion_sources(id,filename,original_path,project_id) VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET filename=excluded.filename,original_path=excluded.original_path", (source_id, spec["slug"] + ".md", str(original), project_id))
        conn.execute("INSERT INTO ingestion_jobs(id,source_id,project_id,revision,processing_version,configuration,original_path,status,current_stage) VALUES(%s,%s,%s,%s,%s,%s,%s,'complete','publish') ON CONFLICT(id) DO UPDATE SET status='complete',current_stage='publish',configuration=excluded.configuration", (job_id, source_id, project_id, revision, version, Jsonb(config), str(original)))
        conn.execute("INSERT INTO ingestion_artifacts(job_id,stage,payload,digest) VALUES(%s,'normalize',%s,%s) ON CONFLICT(job_id,stage) DO UPDATE SET payload=excluded.payload,digest=excluded.digest,created_at=now()", (job_id, Jsonb(normalize), fingerprint(normalize)))
        conn.execute("UPDATE ingestion_publications SET active=false WHERE source_id=%s AND job_id<>%s", (source_id, job_id))
        publish_document(payload, conn)
        conn.execute("INSERT INTO ingestion_publications(job_id,source_id,counts,active) VALUES(%s,%s,%s,true) ON CONFLICT(job_id) DO UPDATE SET active=true,counts=excluded.counts,published_at=now()", (job_id, source_id, Jsonb(counts)))
    for label, ids_parameter in (("SourceRevision", [job_id]), ("Section", [section["id"] for section in sections]), ("Chunk", [chunk["id"] for chunk in chunks]), ("Mention", [mention["id"] for mention in mentions]), ("Assertion", [record["id"] for record in assertions])):
        graph.query(f"MATCH (n:{label}) WHERE n.documentId=$source OR n.sourceId=$source OR n.id=$source SET n.active=CASE WHEN n.id IN $ids THEN true ELSE false END", {"source": source_id, "ids": ids_parameter})
    graph.query("MATCH ()-[r:RELATES]->() WHERE r.sourceId=$source SET r.active=(r.jobId=$job)", {"source": source_id, "job": job_id})
    graph.query("MATCH (e:Entity) WHERE e.id IN $ids SET e.active=true", {"ids": [canonical(graph_name, key, spec)[0] for key in spec["entities"]]})
    graph.query("MATCH (d:Document {id:$source}) SET d.active=true,d.activeJobId=$job,d.title=$title,d.extractionQuality=$quality,d.sourceCoverage=$coverage", {"source": source_id, "job": job_id, "title": spec["title"], "quality": json.dumps(quality), "coverage": json.dumps({"sourceCoverage": spec["coverage"]})})
    graph.query("MATCH (r:SourceRevision {id:$job}) SET r.graphComplete=true", {"job": job_id})
    if project_id:
        with connection() as conn:
            for mode in ("network", "grouped"):
                conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("project-layout:" + project_id + mode,))
                root = conn.execute("SELECT x,y FROM project_layouts WHERE project_id=%s AND mode=%s AND node_id=%s", (project_id, mode, source_id)).fetchone()
                count = conn.execute("SELECT count(*) AS n FROM project_layouts WHERE project_id=%s AND mode=%s AND payload->>'type'='document'", (project_id, mode)).fetchone()["n"]
                angle = count * math.pi * (3 - math.sqrt(5))
                radius = 1200 * math.sqrt(count)
                location = (root["x"], root["y"]) if root else (radius * math.cos(angle), radius * math.sin(angle))

                def put(identifier, kind, px, py, label, **metadata):
                    record = {"id": identifier, "type": kind, "label": label[:100], "preview": label[:180], "jobId": job_id, **metadata}
                    conn.execute("INSERT INTO project_layouts(project_id,mode,node_id,x,y,payload) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(project_id,mode,node_id) DO UPDATE SET payload=excluded.payload", (project_id, mode, identifier, px, py, Jsonb(record)))

                put(source_id, "document", location[0], location[1], spec["title"], documentId=source_id)
                for position, section in enumerate(sections):
                    if mode == "grouped":
                        sx, sy = location[0] + (position - len(sections) / 2) * 130, location[1] + 150
                    else:
                        spread = math.tau * position / max(1, len(sections))
                        sx, sy = location[0] + 250 * math.cos(spread), location[1] + 250 * math.sin(spread)
                    put(section["id"], "section", sx, sy, section["title"], documentId=source_id, sectionId=section["id"])
                    grouped_chunks = [(chunk, sid) for chunk, (sid, _) in zip(chunks, chunk_section, strict=True) if sid == section["id"]]
                    for ordinal, (chunk, sid) in enumerate(grouped_chunks, 0):
                        golden = ordinal * math.pi * (3 - math.sqrt(5))
                        if mode == "grouped":
                            cx, cy = sx + (ordinal % 9 - 4) * 28, sy + 90 + ordinal // 9 * 30
                        else:
                            cx, cy = sx + 55 * math.sqrt(ordinal + 1) * math.cos(golden), sy + 55 * math.sqrt(ordinal + 1) * math.sin(golden)
                        put(chunk["id"], "chunk", cx, cy, chunk["text"], documentId=source_id, sectionId=section["id"], chunkId=chunk["id"])
                        mentioned = sorted({mention["key"] for mention in mentions if mention["chunkId"] == chunk["id"]})
                        for key in mentioned:
                            entity_id, entity = canonical(graph_name, key, spec)
                            head = int(hashlib.sha256(entity_id.encode()).hexdigest()[:12], 16)
                            ea = head / (16 ** 12) * math.tau
                            put(entity_id, "entity", cx + 80 * math.cos(ea), cy + 80 * math.sin(ea), entity["name"], entityType=entity["type"])
            for mention in mentions:
                conn.execute("INSERT INTO ingestion_resolution_decisions(id,job_id,mention_id,canonical_id,decision,rationale,votes) VALUES(%s,%s,%s,%s,'same',%s,%s) ON CONFLICT(id) DO UPDATE SET canonical_id=excluded.canonical_id,decision=excluded.decision,rationale=excluded.rationale WHERE NOT ingestion_resolution_decisions.reverted", ("resolution:" + fingerprint([job_id, mention["id"]]), job_id, mention["id"], canonical(graph_name, mention["key"], spec)[0], "Authored fixture resolution; no duplicate-check judgment was performed.", "[]"))
    return {"sourceId": source_id, "jobId": job_id, "revision": revision, "processingVersion": version, "graph": graph_name, "path": str(original), "counts": counts, "slug": spec["slug"], "project": project_id or "workspace"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", help="Project id; omit for the workspace scope")
    parser.add_argument("--only", help="Publish a single spec by slug")
    arguments = parser.parse_args()
    if arguments.project:
        with connection() as conn:
            if not conn.execute("SELECT 1 FROM projects WHERE id=%s", (arguments.project,)).fetchone():
                raise SystemExit("Unknown project id")
    migrate()
    specs = [spec for spec in SPECS if not arguments.only or spec["slug"] == arguments.only]
    results = [publish(arguments.project, spec) for spec in specs]
    print(json.dumps({"published": len(results), "results": results}))


if __name__ == "__main__":
    main()
