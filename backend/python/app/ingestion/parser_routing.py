import importlib.util
import json
import re
from pathlib import Path

from .code_parser import CODE_SUFFIXES, python_structure
from .parsers import parse


TEXT_SUFFIXES = CODE_SUFFIXES | {".mdx", ".rst", ".log", ".jsonl", ".ndjson", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".example"}


def parse_source(path, config, filename=None):
    path = Path(path)
    filename = filename or path.name
    suffix = Path(filename).suffix.lower()
    categories = config.get("categories", ["general_documents"])
    if suffix in TEXT_SUFFIXES or Path(filename).name in {"LICENSE", "NOTICE", "Dockerfile", ".gitignore"}:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        if len(text) > config["maxExtractedTextCharacters"]:
            raise ValueError("Source text exceeds configured text limit")
        if not text.strip():
            raise ValueError("Source contains no readable text")
        code = suffix in CODE_SUFFIXES
        blocks = [{"ordinal": 0, "kind": "code" if code else "paragraph", "role": "code" if code else "content", "text": text, "location": {"structuralPath": filename, "language": suffix[1:]}, "structured": None}]
        parser = "python_ast" if suffix in {".py", ".pyi"} else "source_text" if code else "structured_text"
        if suffix == '.mdx':
            blocks = [{"ordinal": index, "kind": "heading" if paragraph.lstrip().startswith('#') else "paragraph", "role": "content", "text": paragraph, "location": {"structuralPath": filename + '/block/' + str(index)}, "structured": None} for index, paragraph in enumerate(re.split(r'\n\s*\n', text)) if paragraph.strip()]
            parser = 'mdx_text'
        if suffix in {".jsonl", ".ndjson"}:
            blocks = []
            for number, line in enumerate(text.splitlines(), 1):
                if line.strip():
                    json.loads(line)
                    blocks.append({"ordinal": len(blocks), "kind": "record", "role": "record", "text": line, "location": {"lineNumber": number}, "structured": None})
            parser = "json_lines"
        return {"blocks": blocks, "metadata": {"filename": filename, "format": suffix, "parser": parser, "parserRoute": {"categories": categories, "selected": parser}, "warnings": ["Code text retained; structural extraction is available for Python" ] if code and parser != "python_ast" else []}}
    layout = suffix == ".pdf" and bool(set(categories) & {"research_papers", "scientific_documents", "medical_documents", "construction"})
    available = importlib.util.find_spec("docling") is not None
    mode = config.get("layoutParser", "auto")
    if layout and mode != "text" and available:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        options = PdfPipelineOptions()
        options.do_ocr = False
        options.do_table_structure = True
        result = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}).convert(path)
        blocks = []
        total = 0
        for item, level in result.document.iterate_items():
            label = str(item.label.value)
            if label == "table":
                value = item.export_to_markdown(doc=result.document)
            else:
                value = getattr(item, "text", "")
            if not value.strip():
                continue
            total += len(value)
            if total > config["maxExtractedTextCharacters"]:
                raise ValueError("Layout parser exceeded configured text limit")
            blocks.append({"ordinal": len(blocks), "kind": "table" if label == "table" else "heading" if label in {"section_header", "title"} else "paragraph", "role": label, "text": value, "location": {"pageNumber": item.prov[0].page_no if item.prov else None}, "structured": None})
        if not blocks:
            raise ValueError("Layout parser produced no text; this file may require OCR")
        return {"blocks": blocks, "metadata": {"filename": filename, "format": suffix, "parser": "docling_layout", "parserRoute": {"categories": categories, "selected": "docling_layout"}, "warnings": ["OCR disabled; source page text and tables extracted by Docling"]}}
    result = parse(path, config["maxDecompressedBytes"], config["maxExtractedTextCharacters"], config["maxArchiveMembers"])
    result['metadata']['filename'] = filename
    result["metadata"]["parserRoute"] = {"categories": categories, "selected": result["metadata"]["parser"], "layoutAvailable": available}
    if layout and mode != "text" and not available:
        result["metadata"]["warnings"].append("Docling layout adapter is not installed; using the existing PDF text reader")
    return result


def attach_structure(document, filename):
    if document["metadata"]["parser"] == "python_ast":
        document["codeGraph"] = python_structure(document["text"], filename)
    return document
