"""Reproduce official corpus inventory counts; fetch three sample full texts."""

import hashlib
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
MOF = '("metal-organic framework"[Title/Abstract] OR "metal-organic frameworks"[Title/Abstract])'
QUERIES = {
    "pmc_oa": "open access[filter]",
    "pmc_ccby_or_cc0": '("cc by license"[filter] OR "cc0 license"[filter])',
    "mof_oa_title_abstract": MOF + " AND open access[filter]",
    "mof_ccby_title_abstract": MOF + ' AND "cc by license"[filter]',
    "lithium_ion_battery_oa_title_abstract": '("lithium-ion"[Title/Abstract] AND batter*[Title/Abstract]) AND open access[filter]',
    "catalysis_oa_title_abstract": "catalys*[Title/Abstract] AND open access[filter]",
}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "InspectableEvidenceCorpusAudit/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main():
    output = {
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "meaning": "Discovery inventory counts, not successfully downloaded or validated document counts.",
        "queries": {},
        "sample_fulltexts": [],
    }
    for key, query in QUERIES.items():
        parameters = {"db": "pmc", "term": query, "retmode": "json", "retmax": 9999 if key == "mof_ccby_title_abstract" else 3, "tool": "InspectableEvidenceCorpusAudit"}
        url = BASE + "esearch.fcgi?" + urllib.parse.urlencode(parameters)
        result = json.loads(fetch(url))["esearchresult"]
        output["queries"][key] = {
            "url": url,
            "query": query,
            "count": int(result["count"]),
            "translation": result.get("querytranslation"),
            "warning": result.get("warninglist"),
            "pmcids": ["PMC" + identifier for identifier in result["idlist"]],
        }
        print(key, result["count"], flush=True)
        time.sleep(0.5)

    for pmcid in output["queries"]["mof_ccby_title_abstract"]["pmcids"][:3]:
        url = BASE + "efetch.fcgi?" + urllib.parse.urlencode({"db": "pmc", "id": pmcid.removeprefix("PMC"), "tool": "InspectableEvidenceCorpusAudit"})
        sample = {"pmcid": pmcid, "url": url}
        try:
            raw = fetch(url)
            root = ET.fromstring(raw)
            title = root.find(".//article-title")
            license_element = root.find(".//license")
            sample.update({
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "title": "".join(title.itertext()) if title is not None else None,
                "body_paragraphs": len(root.findall(".//body//p")),
                "license": " ".join("".join(license_element.itertext()).split()) if license_element is not None else None,
            })
        except Exception as error:
            sample["error"] = str(error)
        output["sample_fulltexts"].append(sample)
        print("sample", pmcid, sample.get("bytes"), sample.get("error"), flush=True)
        time.sleep(0.5)

    url = "https://www.rfc-editor.org/rfc-index.xml"
    raw = fetch(url)
    root = ET.fromstring(raw)
    namespace = {"r": root.tag.split("}")[0].removeprefix("{")}
    entries = root.findall("r:rfc-entry", namespace)
    if not entries:
        raise ValueError("RFC inventory has no entries; inspect namespace or upstream format before reporting a count")
    output["rfc"] = {
        "url": url,
        "manifest_bytes": len(raw),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "documents": len(entries),
        "updates_edges": sum(len(entry.findall("r:updates/r:doc-id", namespace)) for entry in entries),
        "obsoletes_edges": sum(len(entry.findall("r:obsoletes/r:doc-id", namespace)) for entry in entries),
        "meaning": "RFC index entries and their explicit directed metadata links; not retrieved full-text files.",
    }
    path = Path(__file__).with_name("corpus-inventory.json")
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print("RFC", output["rfc"]["documents"], "Saved", path, flush=True)


if __name__ == "__main__":
    main()
