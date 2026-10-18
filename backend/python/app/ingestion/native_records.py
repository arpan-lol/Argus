import json
import re
import uuid


_STIX_ID = re.compile(r"^(?P<type>[a-z][a-z0-9-]*)--(?P<uuid>[0-9a-fA-F-]{36})$")
_JSON_STRING_FIELD = re.compile(r'"(?P<key>[^"\\]+)"\s*:\s*(?P<value>"(?:\\.|[^"\\])*")')


def _skip_value(text, start):
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        raise ValueError("Unexpected end of JSON value")
    if text[start] == '"':
        index = start + 1
        escaped = False
        while index < len(text):
            char = text[index]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                return index + 1
            index += 1
        raise ValueError("Unterminated JSON string")
    if text[start] in "[{":
        stack = ["]" if text[start] == "[" else "}"]
        index = start + 1
        quoted = False
        escaped = False
        while index < len(text):
            char = text[index]
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                stack.append("]" if char == "[" else "}")
            elif char in "]}":
                if not stack or char != stack.pop():
                    raise ValueError("Mismatched JSON container")
                if not stack:
                    return index + 1
            index += 1
        raise ValueError("Unterminated JSON container")
    index = start
    while index < len(text) and not text[index].isspace() and text[index] not in ",]}":
        index += 1
    return index


def _root_field_span(text, wanted):
    index = 0
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text) or text[index] != "{":
        return None
    index += 1
    decoder = json.JSONDecoder()
    while index < len(text):
        while index < len(text) and (text[index].isspace() or text[index] == ","):
            index += 1
        if index >= len(text) or text[index] == "}":
            return None
        key, key_end = decoder.raw_decode(text, index)
        index = key_end
        while index < len(text) and (text[index].isspace() or text[index] == ":"):
            index += 1
        value_start = index
        value_end = _skip_value(text, value_start)
        if key == wanted:
            return value_start, value_end
        index = value_end
    return None


def _is_stix_id(value):
    match = _STIX_ID.fullmatch(value or "")
    if not match:
        return None
    try:
        uuid.UUID(match.group("uuid"))
    except ValueError:
        return None
    return match.group("type")


def _looks_like_stix(value):
    if not isinstance(value, dict):
        return False
    if value.get("type") == "bundle":
        return True
    return value.get("spec_version") in {"2.0", "2.1"} and ("type" in value or "id" in value)


def _record(value, raw):
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise ValueError("STIX bundle objects must be JSON objects with a type")
    stix_type = value["type"]
    if not re.fullmatch(r"[a-z][a-z0-9-]*", stix_type):
        raise ValueError("STIX object type is malformed")
    identifier_type = _is_stix_id(value.get("id"))
    if identifier_type != stix_type:
        raise ValueError(f"STIX object id must be a valid {stix_type}--UUID identifier")
    if value.get("spec_version", "2.1") not in {"2.0", "2.1"}:
        raise ValueError("Only STIX 2.0 and 2.1 records are supported")
    return {"id": value["id"], "type": stix_type, "object": value, "text": raw}


def parse_native_stix(raw, max_text_chars, max_records=10000):
    try:
        text = raw.decode("utf-8-sig")
        value = json.loads(text)
    except (UnicodeError, json.JSONDecodeError):
        return None
    if not _looks_like_stix(value):
        return None
    if value.get("type") == "bundle":
        bundle_id = value.get("id")
        if _is_stix_id(bundle_id) != "bundle":
            raise ValueError("STIX bundle id is malformed")
        array = _root_field_span(text, "objects")
        if array is None or text[array[0]:array[0] + 1] != "[":
            raise ValueError("STIX bundle requires an objects array")
        records = []
        index = array[0] + 1
        seen = set()
        while index < array[1] - 1:
            while index < array[1] and (text[index].isspace() or text[index] == ","):
                index += 1
            if index >= array[1] - 1:
                break
            end = _skip_value(text, index)
            raw_record = text[index:end]
            record = _record(json.loads(raw_record), raw_record)
            if record["id"] in seen:
                raise ValueError(f"Duplicate STIX object id {record['id']}")
            seen.add(record["id"])
            records.append(record)
            index = end
    else:
        record = _record(value, text)
        records = [record]
    if not records:
        raise ValueError("STIX bundle contains no objects")
    if len(records) > max_records:
        raise ValueError("STIX bundle exceeds configured native record count limit")
    blocks = []
    warnings = []
    identifiers = {record["id"] for record in records}
    for record in records:
        obj = record["object"]
        if record["type"] == "relationship":
            for key in ("source_ref", "target_ref"):
                ref = obj.get(key)
                if _is_stix_id(ref) is None:
                    warnings.append({"recordId": record["id"], "kind": "malformed_reference", "field": key, "value": ref})
                elif ref not in identifiers:
                    warnings.append({"recordId": record["id"], "kind": "dangling_bundle_reference", "field": key, "value": ref})
        blocks.append({"ordinal": len(blocks), "kind": "record", "role": "stix_object", "text": record["text"], "location": {"structuralPath": f"objects/{len(blocks)}", "nativeId": record["id"], "nativeType": record["type"]}, "structured": {"nativeRecord": obj, "nativeRecordId": record["id"], "nativeRecordType": record["type"]}})
    total = sum(len(block["text"]) for block in blocks)
    if total > max_text_chars:
        raise ValueError("STIX source records exceed configured extracted-text character limit")
    return {"blocks": blocks, "metadata": {"format": ".json", "parser": "stix_native_json", "nativeFormat": "STIX 2.x JSON", "nativeRecordCount": len(blocks), "warnings": warnings, "danglingReferenceCount": sum(warning["kind"] == "dangling_bundle_reference" for warning in warnings)}}


def string_fields(text):
    values = []
    for match in _JSON_STRING_FIELD.finditer(text):
        try:
            decoded = json.loads(match.group("value"))
        except json.JSONDecodeError:
            continue
        values.append({"key": match.group("key"), "value": decoded, "start": match.start("value"), "end": match.end("value"), "quote": text[match.start("value"):match.end("value")]})
    return values


def native_type(identifier, known_objects):
    known = known_objects.get(identifier)
    if known:
        return "stix_" + known["type"]
    prefix = _is_stix_id(identifier)
    return "stix_" + prefix if prefix else "stix_reference"


def extract_native_chunk(chunk, document, known_objects, all_chunks):
    from .extraction import source_span

    entities = []
    relationships = []
    warnings = []
    unpublished_relationships = 0

    def owners_for_field(block, field):
        start = block["startOffset"] + field["start"]
        end = block["startOffset"] + field["end"]
        return [candidate for candidate in all_chunks if candidate["startOffset"] <= start and end <= candidate["endOffset"]]

    def block_owner(block):
        owners = [candidate for candidate in all_chunks if candidate["startOffset"] <= block["startOffset"] < candidate["endOffset"]]
        return min(owners, key=lambda candidate: candidate["ordinal"]) if owners else None

    for block in document["blocks"]:
        structured = block.get("structured") or {}
        obj = structured.get("nativeRecord")
        if not obj or block["startOffset"] >= chunk["endOffset"] or block["endOffset"] <= chunk["startOffset"]:
            continue
        raw = document["text"][block["startOffset"]:block["endOffset"]]
        fields = string_fields(raw)
        by_key = {}
        for field in fields:
            by_key.setdefault(field["key"], []).append(field)

        def field_value(key, expected=None):
            return next((field for field in by_key.get(key, []) if expected is None or field["value"] == expected), None)

        def append_entity(identifier, name, entity_type, description, field, source_record=None):
            if field is None or not isinstance(name, str) or not name.strip():
                return None
            source_record = obj if source_record is None else source_record
            start = block["startOffset"] + field["start"] - chunk["startOffset"]
            end = block["startOffset"] + field["end"] - chunk["startOffset"]
            if start < 0 or end > len(chunk["text"]) or chunk["text"][start:end] != field["quote"]:
                return None
            key = "native_" + str(len(entities))
            span = source_span(chunk, start, end)
            revoked = source_record.get("revoked") is True
            deprecated = source_record.get("x_mitre_deprecated") is True or source_record.get("x_deprecated") is True
            state = "revoked" if revoked else "deprecated" if deprecated else "active"
            entities.append({"key": key, "name": name, "entity_type": entity_type, "description": description or "", "quote": chunk["text"][start:end], "sourceSpan": span, "sourceSpans": [span], "sourceSpanStatus": "exact", "extractionMethod": "stix_native", "llmVerified": False, "nativeResolverKey": identifier, "nativeFormat": "stix", "nativeState": state, "revoked": revoked, "deprecated": deprecated, "sourceContext": {"nativeFormat": "stix", "revoked": revoked, "deprecated": deprecated, "nativeState": state}})
            return key

        if obj.get("type") != "relationship":
            identifier = obj["id"]
            name = obj.get("name") or obj.get("id")
            name_field = field_value("name", name) if obj.get("name") else None
            id_field = field_value("id", identifier)
            name_owners = owners_for_field(block, name_field) if name_field else []
            field = name_field if name_owners else id_field
            candidates = name_owners if name_owners else owners_for_field(block, id_field) if id_field else []
            if candidates and chunk["id"] == min(candidates, key=lambda candidate: candidate["ordinal"])["id"]:
                append_entity(identifier, name, "stix_" + obj["type"], obj.get("description"), field)
            continue

        source_ref = obj.get("source_ref")
        target_ref = obj.get("target_ref")
        relationship_type = obj.get("relationship_type")
        if not all(isinstance(value, str) for value in (source_ref, target_ref, relationship_type)) or _is_stix_id(source_ref) is None or _is_stix_id(target_ref) is None:
            owner = block_owner(block)
            if owner and chunk["id"] == owner["id"]:
                warnings.append({"recordId": obj.get("id"), "kind": "malformed_relationship_fields"})
                unpublished_relationships += 1
            continue
        source_object = known_objects.get(source_ref, {})
        target_object = known_objects.get(target_ref, {})
        source_field = field_value("source_ref", source_ref)
        target_field = field_value("target_ref", target_ref)
        type_field = field_value("relationship_type", relationship_type)
        if not source_field or not target_field or not type_field:
            owner = block_owner(block)
            if owner and chunk["id"] == owner["id"]:
                warnings.append({"recordId": obj.get("id"), "kind": "relationship_fields_not_found"})
                unpublished_relationships += 1
            continue
        field_owners = [owners_for_field(block, field) for field in (source_field, target_field, type_field)]
        common = {candidate["id"]: candidate for candidate in field_owners[0]}
        for owners in field_owners[1:]:
            common = {identifier: candidate for identifier, candidate in common.items() if any(owner["id"] == identifier for owner in owners)}
        if not common:
            owner = block_owner(block)
            if owner and chunk["id"] == owner["id"]:
                warnings.append({"recordId": obj.get("id"), "kind": "relationship_fields_split_across_chunks"})
                unpublished_relationships += 1
            continue
        relation_owner = min(common.values(), key=lambda candidate: candidate["ordinal"])
        if chunk["id"] != relation_owner["id"]:
            continue
        subject = append_entity(source_ref, source_object.get("name") or source_ref, native_type(source_ref, known_objects), source_object.get("description"), source_field, source_object)
        target = append_entity(target_ref, target_object.get("name") or target_ref, native_type(target_ref, known_objects), target_object.get("description"), target_field, target_object)
        if not subject or not target:
            warnings.append({"recordId": obj.get("id"), "kind": "relationship_endpoint_offset_mismatch"})
            unpublished_relationships += 1
            continue
        first = min(source_field["start"], target_field["start"], type_field["start"])
        last = max(source_field["end"], target_field["end"], type_field["end"])
        start = block["startOffset"] + first - chunk["startOffset"]
        end = block["startOffset"] + last - chunk["startOffset"]
        if start < 0 or end > len(chunk["text"]) or end <= start:
            warnings.append({"recordId": obj.get("id"), "kind": "relationship_quote_offset_mismatch"})
            unpublished_relationships += 1
            continue
        quote = chunk["text"][start:end]
        span = source_span(chunk, start, end)
        dangling = source_ref not in known_objects or target_ref not in known_objects
        revoked = obj.get("revoked") is True
        deprecated = obj.get("x_mitre_deprecated") is True or obj.get("x_deprecated") is True
        endpoint_revoked = source_object.get("revoked") is True or target_object.get("revoked") is True
        endpoint_deprecated = source_object.get("x_mitre_deprecated") is True or source_object.get("x_deprecated") is True or target_object.get("x_mitre_deprecated") is True or target_object.get("x_deprecated") is True
        state = "revoked" if revoked else "deprecated" if deprecated else "active"
        traversal_status = "revoked" if revoked or endpoint_revoked else "deprecated" if deprecated or endpoint_deprecated else "source_structured"
        relationships.append({"subject": subject, "predicate": relationship_type, "object": target, "quote": quote, "conditions": [], "polarity": "affirmed", "polarityStatus": "source_structured", "qualifierStatus": "source_structured", "traversalStatus": traversal_status, "confidence": None, "sourceSpan": span, "sourceSpans": [span], "sourceSpanStatus": "exact", "extractionMethod": "stix_native", "llmVerified": False, "referenceStatus": "dangling_bundle_reference" if dangling else "resolved_in_bundle", "revoked": revoked, "deprecated": deprecated, "endpointRevoked": endpoint_revoked, "endpointDeprecated": endpoint_deprecated, "nativeState": state, "sourceContext": {"nativeFormat": "stix", "revoked": revoked, "deprecated": deprecated, "endpointRevoked": endpoint_revoked, "endpointDeprecated": endpoint_deprecated, "nativeState": state, "traversalStatus": traversal_status}})
    return {"entities": entities, "relationships": relationships, "warnings": warnings, "unpublishedRelationships": unpublished_relationships}
