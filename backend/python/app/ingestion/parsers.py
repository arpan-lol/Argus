import csv
import gzip
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from defusedxml import ElementTree


SUPPORTED = {".txt", ".md", ".markdown", ".xml", ".jats", ".html", ".htm", ".pdf", ".docx", ".csv", ".tsv", ".xlsx", ".json"}


def parse(path, max_decompressed_bytes=209715200, max_text_chars=20971520, max_archive_members=10000):
    path = Path(path)
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    if suffix == ".gz":
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            raw = stream.read(max_decompressed_bytes + 1)
        if len(raw) > max_decompressed_bytes:
            raise ValueError(f"Decompressed document exceeds configured {max_decompressed_bytes} byte limit")
        suffix = Path(path.stem).suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"Unsupported format {suffix or '(no extension)'}. Supported: {', '.join(sorted(SUPPORTED))}. OCR and legacy Office binaries are not enabled.")
    if suffix in {".docx", ".xlsx"}:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) > max_archive_members or sum(member.file_size for member in members) > max_decompressed_bytes:
                raise ValueError("Office archive exceeds configured member or expanded-byte processing limits")
    blocks = []
    text_characters = 0
    metadata = {"filename": path.name, "format": suffix, "parser": "source-blocks-3", "warnings": []}

    def add(text, kind="paragraph", location=None, structured=None):
        nonlocal text_characters
        if text and text.strip():
            text_characters += len(text)
            if text_characters > max_text_chars:
                raise ValueError(f"Parsed text exceeds configured {max_text_chars} character processing limit")
            location = location or {}
            blocks.append({"ordinal": len(blocks), "kind": kind, "role": location.get("role", "table" if kind == "table" else "content"), "text": text, "location": location, "structured": structured})

    if suffix in {".xml", ".jats"}:
        root = ElementTree.fromstring(raw)
        if sum(1 for node in root.iter() if node.tag.split("}")[-1] == "article") > 1:
            raise ValueError("This XML file contains multiple articles. Supply one article per source file so revisions and source locations remain unambiguous.")
        article = root if root.tag.split("}")[-1] == "article" else next((n for n in root.iter() if n.tag.split("}")[-1] == "article"), root)
        metadata["sourceDocumentType"] = article.get("article-type", "unspecified")
        body = next((node for node in article if node.tag.split("}")[-1] == "body"), None)
        metadata["authors"] = []
        for node in article.iter():
            tag = node.tag.split("}")[-1]
            if tag == "license":
                metadata["license"] = " ".join("".join(node.itertext()).split())
                metadata["licenseUrl"] = next((value for key, value in node.attrib.items() if key.endswith("href")), None)
            elif tag == "contrib" and node.get("contrib-type", "author") == "author":
                metadata["authors"].append(" ".join(" ".join(node.itertext()).split()))
            elif tag == "pub-date":
                values = {part.tag.split("}")[-1]: "".join(part.itertext()).strip() for part in node}
                metadata.setdefault("publicationDates", []).append({"type": node.get("pub-type") or node.get("publication-format"), **values})
                if "year" in values:
                    metadata.setdefault("year", values["year"])
        title = next((n for n in article.iter() if n.tag.split("}")[-1] == "article-title"), None)
        if title is not None:
            metadata["title"] = "".join(title.itertext()).strip()
        for node in article.iter():
            tag = node.tag.split("}")[-1]
            if tag == "article-id" and node.get("pub-id-type") in {"pmc", "pmcid", "doi"}:
                metadata[node.get("pub-id-type")] = "".join(node.itertext()).strip()
        if metadata.get("pmc") or metadata.get("pmcid"):
            ident = metadata.get("pmcid") or metadata["pmc"]
            metadata["sourceUrl"] = f"https://pmc.ncbi.nlm.nih.gov/articles/{ident if ident.startswith('PMC') else 'PMC' + ident}/"
        containers = {"p", "title", "article-title", "table", "disp-formula", "list-item", "caption", "mixed-citation", "element-citation", "preformat"}
        roles = {"front": "front_matter", "body": "body", "back": "back_matter", "abstract": "abstract", "trans-abstract": "abstract", "ref-list": "references", "ref": "references", "table": "table", "caption": "caption"}

        def non_whitespace(text):
            return "".join(text.split())

        def walk(node, ancestry, role="content", region="content", section_path=()):
            tag = node.tag.split("}")[-1]
            structural = f"{ancestry}/{tag}"
            role = roles.get(tag, role)
            if tag in {"front", "body", "back"}:
                region = tag
            if tag == "sec":
                heading = next((child for child in node if child.tag.split("}")[-1] == "title"), None)
                section_path = (*section_path, {"title": "".join(heading.itertext()).strip() if heading is not None else "", "structuralPath": structural, "sourceId": node.get("id")})
            location = {"structuralPath": structural, "element": tag, "role": role, "sourceRegion": region, "sectionPath": list(section_path)}
            if node.get("id"):
                location["sourceId"] = node.get("id")
            nested_blocks = any(child.tag.split("}")[-1] in containers for child in node.iter() if child is not node)
            if tag == "table" or (tag in containers and not nested_blocks):
                if tag == "table":
                    rows = [["".join(cell.itertext()).strip() for cell in row if cell.tag.split("}")[-1] in {"td", "th"}] for row in node.iter() if row.tag.split("}")[-1] == "tr"]
                    source_text = "".join(node.itertext())
                    row_text = "\n".join("\t".join(row) for row in rows)
                    retained = row_text if non_whitespace(row_text) == non_whitespace(source_text) else source_text
                    add(retained, "table", location, {"rows": rows, "textRendering": "rows" if retained == row_text else "source_text"})
                else:
                    kind = "citation" if tag in {"mixed-citation", "element-citation"} else "heading" if tag in {"title", "article-title"} else "preformatted" if tag == "preformat" else "caption" if tag == "caption" else "paragraph"
                    add("".join(node.itertext()), kind, location)
                return
            kind = "citation" if role == "references" else "caption" if role == "caption" else "paragraph"
            add(node.text, kind, {**location, "textPosition": "text"})
            for ordinal, child in enumerate(node):
                walk(child, f"{structural}[{ordinal}]", role, region, section_path)
                add(child.tail, kind, {**location, "textPosition": "tail", "afterChild": ordinal})
        walk(article, "")
        body_text = "".join(body.itertext()) if body is not None else ""
        body_available = non_whitespace(body_text)
        body_retained = non_whitespace("".join(block["text"] for block in blocks if block["location"].get("sourceRegion") == "body"))
        complete = body is not None and body_available == body_retained
        reasons = []
        if body is None:
            reasons.append("No JATS body is present; available front matter, abstract and back matter do not establish complete article body coverage.")
        elif not body_available:
            reasons.append("The JATS body contains no readable text; images or external content may require a different reader.")
        elif not complete:
            reasons.append("Retained body text differs from the original ordered body text; processing requires attention before extraction.")
        metadata["sourceCoverage"] = {
            "bodyPresent": body is not None,
            "bodyTextCharacters": len(body_text.strip()),
            "bodyAvailableNonWhitespaceCharacters": len(body_available),
            "bodyRetainedNonWhitespaceCharacters": len(body_retained),
            "bodyMissingNonWhitespaceCharacters": max(0, len(body_available) - len(body_retained)),
            "bodyCoverageComplete": complete and bool(body_available),
            "bodyAvailableTextSha256": hashlib.sha256(body_available.encode("utf-8")).hexdigest(),
            "bodyRetainedTextSha256": hashlib.sha256(body_retained.encode("utf-8")).hexdigest(),
            "accounting": "exact_ordered_non_whitespace_characters",
            "scope": "available_jats_text",
            "requiresAttention": bool(reasons),
            "attentionReasons": reasons,
        }
        metadata["warnings"].extend(reasons)
    elif suffix == ".pdf":
        from pypdf import PdfReader
        for index, page in enumerate(PdfReader(io.BytesIO(raw)).pages):
            text = page.extract_text() or ""
            add(text, location={"pageNumber": index + 1})
            if not text.strip():
                metadata["warnings"].append(f"Page {index + 1} has no extractable text; OCR is not configured")
        metadata["warnings"].append("PDF text reading order is parser-derived; coordinates and table structure are not reconstructed")
    elif suffix == ".docx":
        from docx import Document
        document = Document(io.BytesIO(raw))
        from docx.oxml.ns import qn
        from docx.text.paragraph import Paragraph
        from docx.table import Table
        for index, element in enumerate(document.element.body):
            if element.tag == qn("w:p"):
                paragraph = Paragraph(element, document)
                add(paragraph.text, "heading" if paragraph.style.name.startswith("Heading") else "paragraph", {"structuralPath": f"body/{index}"})
            elif element.tag == qn("w:tbl"):
                rows = [[cell.text for cell in row.cells] for row in Table(element, document).rows]
                add("\n".join("\t".join(row) for row in rows), "table", {"structuralPath": f"body/{index}"}, {"rows": rows})
    elif suffix == ".xlsx":
        from openpyxl import load_workbook
        from openpyxl.utils import get_column_letter
        for sheet in load_workbook(io.BytesIO(raw), read_only=True, data_only=False):
            for index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                cells = ["" if cell is None else str(cell) for cell in row]
                add("\t".join(cells), "table", {"sheetName": sheet.title, "cellRange": f"A{index}:{get_column_letter(sheet.max_column)}{index}"}, {"cells": cells})
    elif suffix in {".csv", ".tsv"}:
        for index, row in enumerate(csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter="\t" if suffix == ".tsv" else ",")):
            add("\t".join(row), "table", {"structuralPath": f"row/{index + 1}"}, {"cells": row})
    elif suffix in {".html", ".htm"}:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw, "html.parser")
        for element in soup(["script", "style", "nav"]):
            element.decompose()
        metadata["title"] = soup.title.get_text() if soup.title else path.stem
        for index, element in enumerate(soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "pre", "table", "li"])):
            if element.find_parent(["table", "li", "pre"]):
                continue
            add(element.get_text(" ", strip=True), "heading" if re.fullmatch("h[1-6]", element.name) else "paragraph", {"structuralPath": f"{element.name}/{index}"})
    else:
        text = raw.decode("utf-8-sig")
        if suffix == ".json":
            json.loads(text)
        for index, paragraph in enumerate(re.split(r"\n\s*\n", text)):
            add(paragraph, "heading" if suffix in {".md", ".markdown"} and paragraph.lstrip().startswith("#") else "paragraph", {"structuralPath": f"block/{index}"})
    if not blocks:
        raise ValueError("Parser produced no readable text. This document may require OCR or a different parser.")
    return {"blocks": blocks, "metadata": metadata}


def normalize(parsed):
    blocks = []
    parts = []
    cursor = 0
    for block in parsed["blocks"]:
        text = block["text"].replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            continue
        if parts:
            cursor += 2
        blocks.append({**block, "text": text, "startOffset": cursor, "endOffset": cursor + len(text), "offsetUnit": "unicode_code_point", "fidelity": "derived"})
        parts.append(text)
        cursor += len(text)
    return {"text": "\n\n".join(parts), "blocks": blocks, "metadata": parsed["metadata"], "normalization": "Newlines normalized; block edges stripped; two-newline block separator. Locations refer to original structural/page positions; offsets refer to normalized text, not raw bytes."}
