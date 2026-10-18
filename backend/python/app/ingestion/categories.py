import json
from itertools import zip_longest
from pathlib import Path


def category_catalog():
    return json.loads(Path(__file__).with_name("document_categories.json").read_text(encoding="utf-8"))


def validate_categories(values):
    valid = {item["id"] for item in category_catalog()}
    values = list(dict.fromkeys(values))
    if not values or any(value not in valid for value in values):
        raise ValueError("Select at least one supported document category")
    return values


def seed_settings(categories, entity_cap=24, relationship_cap=32):
    selected = [item for item in category_catalog() if item["id"] in categories]
    if not selected:
        selected = [item for item in category_catalog() if item["id"] == "general_documents"]
    def combine(key, maximum):
        values = {}
        for row in zip_longest(*(list(item[key].items()) for item in selected)):
            for value in row:
                if value and len(values) < maximum:
                    values.setdefault(*value)
        return values
    entities = combine("entities", entity_cap)
    relationships = combine("relationships", relationship_cap)
    return {"entityTypes": list(entities), "entityDescriptions": entities, "relationshipTypes": list(relationships), "relationshipDescriptions": relationships, "extractionInstructions": "Extract relationships stated in the source. Preserve negation, conditions and attribution.", "rationale": "Initial labels from the selected document categories", "profileOrigin": "category_defaults"}
