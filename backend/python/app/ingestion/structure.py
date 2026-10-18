from .config import fingerprint


def sections_for(document, job):
    title = document["metadata"].get("title") or job["filename"]
    headings = [block for block in document["blocks"] if block["kind"] == "heading"]
    boundaries = [(block["startOffset"], block["text"].strip(), block["location"]) for block in headings]
    if not boundaries or boundaries[0][0] > 0:
        boundaries.insert(0, (0, title, {}))
    sections = []
    for index, (start, label, location) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(document["text"])
        if end > start:
            sections.append({"id": "section:" + fingerprint([job["id"], start, end]), "documentId": job["source_id"], "title": label, "ordinal": len(sections) + 1, "startOffset": start, "endOffset": end, "locationKind": "source_heading" if location else "source", "sourceLocation": location, "sectionPath": location.get("sectionPath", [label]) if location else [label]})
    return sections


def chunk_sections(chunk, sections):
    related = [section for section in sections if section["startOffset"] < chunk["endOffset"] and section["endOffset"] > chunk["startOffset"]]
    if not related:
        raise ValueError("Chunk does not intersect a source section")
    primary = next((section for section in related if section["startOffset"] <= chunk["startOffset"] < section["endOffset"]), related[0])
    return primary, related
