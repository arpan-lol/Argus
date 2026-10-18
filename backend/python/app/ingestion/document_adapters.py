import email
import json
import re
import zipfile
from email import policy
from pathlib import Path

from defusedxml import ElementTree


def parse_document_adapter(path, config, filename):
    suffix = Path(filename).suffix.lower()
    if suffix not in {'.eml', '.pptx'}:
        return None
    blocks = []
    metadata = {'filename': filename, 'format': suffix, 'parser': 'mime_email' if suffix == '.eml' else 'ooxml_slides', 'warnings': [], 'parserRoute': {'categories': config.get('categories', []), 'selected': 'mime_email' if suffix == '.eml' else 'ooxml_slides'}}
    total = 0

    def add(text, kind, location, structured=None):
        nonlocal total
        if not text.strip():
            return
        total += len(text)
        if total > config['maxExtractedTextCharacters']:
            raise ValueError('Document adapter exceeded the configured text limit')
        blocks.append({'ordinal': len(blocks), 'text': text, 'kind': kind, 'role': location.get('role', 'content'), 'location': location, 'structured': structured})

    if suffix == '.eml':
        raw = Path(path).read_bytes()
        if len(raw) > config['maxDecompressedBytes']:
            raise ValueError('Email exceeds the configured input byte limit')
        message = email.message_from_bytes(raw, policy=policy.default)
        fields = {key: str(message.get(key, '')) for key in ('From', 'To', 'Cc', 'Date', 'Subject', 'Message-ID', 'In-Reply-To', 'References')}
        metadata.update({'title': fields['Subject'] or filename, 'messageHeaders': fields, 'attachments': []})
        add('\n'.join(key + ': ' + value for key, value in fields.items() if value), 'record', {'structuralPath': 'message/headers', 'role': 'message_metadata'}, {'headers': fields})
        body = message.get_body(preferencelist=('plain', 'html')) if message.is_multipart() else message
        for part in message.walk():
            if part.is_attachment() or part.get_filename():
                metadata['attachments'].append({'filename': part.get_filename(), 'mediaType': part.get_content_type(), 'status': 'not_extracted'})
        if body is not None:
            value = body.get_content()
            if not isinstance(value, str):
                raise ValueError('Email has no readable text body')
            if body.get_content_type() == 'text/html':
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(value, 'html.parser')
                for node in soup(['script', 'style']):
                    node.decompose()
                value = soup.get_text('\n', strip=True)
            for index, paragraph in enumerate(re.split(r'\n\s*\n', value)):
                quoted = paragraph.lstrip().startswith('>')
                add(paragraph, 'paragraph', {'structuralPath': 'message/body/' + str(index), 'role': 'quoted_reply' if quoted else 'message_body', 'messageId': fields['Message-ID'], 'author': fields['From'], 'date': fields['Date']})
        metadata['warnings'].append('Quoted replies retain their source text; reply attribution and commitments are not inferred automatically')
        if metadata['attachments']:
            metadata['warnings'].append('Email attachments are listed but not ingested; upload attachments separately')
        if not any(block['location'].get('role') in {'message_body', 'quoted_reply'} for block in blocks):
            raise ValueError('Email has no readable body; headers alone do not establish full content coverage')
    else:
        from .parsers import _table_text
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > config['maxArchiveMembers'] or sum(entry.file_size for entry in entries) > config['maxDecompressedBytes']:
                raise ValueError('Slide archive exceeds configured member or expanded-byte limits')
            slide_names = sorted((entry.filename for entry in entries if re.fullmatch(r'ppt/slides/slide\d+\.xml', entry.filename)), key=lambda value: int(re.search(r'slide(\d+)', value).group(1)))
            namespace = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main', 'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}
            for number, name in enumerate(slide_names, 1):
                root = ElementTree.fromstring(archive.read(name))
                for index, shape in enumerate(root.findall('.//p:sp', namespace)):
                    placeholder = shape.find('.//p:ph', namespace)
                    title = placeholder is not None and placeholder.get('type') in {'title', 'ctrTitle'}
                    for paragraph, element in enumerate(shape.findall('.//a:p', namespace)):
                        value = ''.join(node.text or '' for node in element.findall('.//a:t', namespace))
                        add(value, 'heading' if title else 'paragraph', {'pageNumber': number, 'slideNumber': number, 'structuralPath': f'{name}/shape/{index}/paragraph/{paragraph}', 'role': 'slide_title' if title else 'slide_text'})
                for index, table in enumerate(root.findall('.//a:tbl', namespace)):
                    rows = [[' '.join(node.text or '' for node in cell.findall('.//a:t', namespace)) for cell in row.findall('a:tc', namespace)] for row in table.findall('a:tr', namespace)]
                    value, structured = _table_text(rows)
                    add(value, 'table', {'pageNumber': number, 'slideNumber': number, 'structuralPath': f'{name}/table/{index}'}, structured)
            metadata['sourceCoverage'] = {'coverageLabel': 'available_slide_text', 'slides': len(slide_names), 'limitedSource': True, 'requiresAttention': False}
            metadata['warnings'].append('Native slide text and tables retained; diagrams, image text, speaker notes and visual reading order are not reconstructed')
    if not blocks:
        raise ValueError('Document contains no readable native text; OCR or another reader is required')
    return {'blocks': blocks, 'metadata': metadata}
