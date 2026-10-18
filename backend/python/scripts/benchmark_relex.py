import argparse
import json
import re
import time
from pathlib import Path
from xml.etree import ElementTree

import gzip

from gliner import GLiNER


CASES = [
    {
        "pmcid": "PMC516445",
        "anchor": "Adsorption of Al(III) demonstrate",
        "end": "removal of aluminium.",
        "expected": {"source": "magnetic dye-affinity beads", "target": "Al(III)", "meaning": "adsorbs"},
    },
    {
        "pmcid": "PMC516445",
        "anchor": "These beads were used for the removal",
        "end": "magnetically stabilized fluidized bed.",
        "expected": {"source": "beads", "target": "Al(III)", "meaning": "removes"},
    },
    {
        "pmcid": "PMC12489670",
        "anchor": "CON-LDU8-30% functioned as an efficient",
        "end": "respectively.",
        "expected": {"source": "CON-LDU8-30%", "target": "CrO", "meaning": "adsorbs"},
    },
    {
        "pmcid": "PMC12489670",
        "anchor": "CON-LDU8-30% exhibited high sensitivity",
        "end": "fluorescence response.",
        "expected": {"source": "CON-LDU8-30%", "target": "CrO", "meaning": "detects"},
    },
    {
        "pmcid": "PMC12540740",
        "anchor": "All PAs were used for the removal",
        "end": "for biogenic amines,",
        "expected": {"source": "PAs", "target": "biogenic amines", "meaning": "removes"},
    },
    {
        "pmcid": "PMC13273936",
        "anchor": "Under optimized conditions (40 ppm CV",
        "end": "pseudo-first-order kinetics (k = 0.025 min-1).",
        "expected": {"source": "LCFO-5", "target": "CV", "meaning": "degrades"},
    },
    {
        "pmcid": "PMC13273936",
        "anchor": "In this study, Fe-doped lanthanum cobaltite",
        "end": "pseudo-first-order kinetics (k = 0.025 min-1).",
        "expected": {"source": "LCFO-5", "target": "crystal violet", "meaning": "degrades"},
    },
]

LABEL_SETS = {
    "broad": {
        "material": "A synthesized substance, sorbent, catalyst, polymer or named formulation",
        "pollutant": "A contaminant, dye, metal ion or chemical being removed or detected",
        "chemical": "A chemical compound, element or ion discussed in the passage",
    },
    "materials": {
        "adsorbent": "A named material or sorbent used to adsorb or remove another substance",
        "photocatalyst": "A named material used to degrade another substance under light",
        "pollutant": "A named contaminant, dye, metal ion or chemical being removed or detected",
        "other": "An additional named entity participating in a stated relationship",
    },
}
RELATION_LABELS = ["adsorbs", "removes", "detects", "degrades"]


def abstract_text(path):
    with gzip.open(path, "rb") as source:
        root = ElementTree.fromstring(source.read())
    abstract = next((node for node in root.iter() if node.tag.split("}")[-1] == "abstract"), None)
    if abstract is None:
        raise ValueError(f"No abstract in {path.name}")
    return " ".join("".join(abstract.itertext()).split())


def source_case(root, case):
    matches = list(root.rglob(f"*-{case['pmcid']}.xml.gz"))
    if len(matches) != 1:
        raise ValueError(f"Expected one original for {case['pmcid']}; found {len(matches)}")
    full_text = abstract_text(matches[0])
    match = re.search(re.escape(case["anchor"]), full_text, flags=re.IGNORECASE)
    if match is None:
        raise ValueError(f"Anchor not present in {case['pmcid']}: {case['anchor']}")
    end = full_text.find(case["end"], match.start())
    if end < 0:
        raise ValueError(f"End anchor not present in {case['pmcid']}: {case['end']}")
    text = full_text[match.start():end + len(case["end"])]
    return {"pmcid": case["pmcid"], "filename": matches[0].name, "text": text, "expected": case["expected"]}


def run(model_name, originals, label_set):
    cases = [source_case(originals, case) for case in CASES]
    labels = LABEL_SETS[label_set]
    started = time.perf_counter()
    model = GLiNER.from_pretrained(model_name)
    load_seconds = time.perf_counter() - started
    rows = []
    for case in cases:
        started = time.perf_counter()
        entities, relations = model.inference(
            texts=[case["text"]],
            labels=labels,
            relations=RELATION_LABELS,
            threshold=0.3,
            relation_threshold=0.5,
            return_relations=True,
            flat_ner=False,
        )
        rows.append({**case, "seconds": round(time.perf_counter() - started, 3), "entities": entities[0], "relations": relations[0]})
    return {
        "model": model_name,
        "labelSet": label_set,
        "loadSeconds": round(load_seconds, 3),
        "entityLabels": labels,
        "relationLabels": RELATION_LABELS,
        "thresholds": {"entity": 0.3, "relation": 0.5},
        "hardware": "local CPU unless GLiNER selects an available accelerator",
        "cases": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="knowledgator/gliner-relex-base-v1.0")
    parser.add_argument("--label-set", choices=tuple(LABEL_SETS), default="broad")
    parser.add_argument("--originals", type=Path, default=Path("data/originals"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.model, args.originals, args.label_set)
    output = args.output or Path(f"docs/relex-benchmark-{args.label_set}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"model": result["model"], "loadSeconds": result["loadSeconds"], "cases": [{"pmcid": case["pmcid"], "seconds": case["seconds"], "entities": len(case["entities"]), "relations": len(case["relations"])} for case in result["cases"]]}, indent=2))
