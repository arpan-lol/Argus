_CONTRACTS = {
    "code_repository": {
        "calls": ({"function"}, {"function"}),
        "inherits_from": ({"class"}, {"class"}),
        "implements": ({"class", "component"}, {"class", "component"}),
        "imports": ({"module"}, {"module", "technology"}),
        "defines": ({"module", "class"}, {"class", "function", "configuration", "component"}),
        "tests": ({"function", "class", "component"}, {"function", "class", "component"}),
    },
    "research_papers": {
        "uses_method": ({"study"}, {"method"}),
        "evaluates": ({"study", "method"}, {"material", "dataset", "application"}),
        "measures": ({"study", "method"}, {"measurement", "material"}),
        "compares_with": ({"study", "method", "material", "dataset"}, {"study", "method", "material", "dataset"}),
        "reports": ({"study"}, {"measurement", "dataset", "material", "application"}),
        "cites": ({"study"}, {"study"}),
    },
    "scientific_documents": {
        "adsorbs": ({"material"}, {"chemical", "pollutant"}),
        "degrades": ({"material", "chemical", "process"}, {"chemical", "pollutant"}),
        "detects": ({"material", "instrument"}, {"chemical", "pollutant"}),
        "synthesized_using": ({"material", "chemical"}, {"process"}),
        "has_property": ({"material", "chemical"}, {"property"}),
        "reacts_with": ({"chemical", "pollutant"}, {"chemical", "pollutant"}),
    },
    "medical_documents": {
        "treats": ({"drug", "procedure"}, {"disease", "symptom"}),
        "causes": ({"drug", "procedure", "disease", "organism"}, {"disease", "symptom"}),
        "associated_with": ({"disease", "drug", "procedure", "symptom", "test", "organism"}, {"disease", "drug", "procedure", "symptom", "test", "organism"}),
        "diagnoses": ({"test"}, {"disease"}),
        "contraindicated_for": ({"drug", "procedure"}, {"disease", "symptom"}),
        "has_symptom": ({"disease"}, {"symptom"}),
    },
    "cybersecurity": {
        "exploits": ({"threat_actor", "technique"}, {"vulnerability"}),
        "affects": ({"vulnerability"}, {"asset"}),
        "targets": ({"threat_actor", "technique"}, {"asset", "vulnerability"}),
        "mitigates": ({"control"}, {"threat_actor", "technique", "vulnerability"}),
        "communicates_with": ({"asset", "indicator"}, {"asset", "indicator"}),
        "indicates": ({"indicator"}, {"vulnerability", "technique", "threat_actor"}),
    },
}


def relation_constraints(categories):
    constraints = {}
    for category in categories:
        for predicate, (subjects, objects) in _CONTRACTS.get(category, {}).items():
            prior_subjects, prior_objects = constraints.get(predicate, (set(), set()))
            constraints[predicate] = (prior_subjects | subjects, prior_objects | objects)
    return constraints


def endpoint_types_allowed(predicate, subject_type, object_type, constraints):
    contract = constraints.get(predicate.strip().lower())
    if contract is None:
        return True
    subjects, objects = contract
    return subject_type.strip().lower() in subjects and object_type.strip().lower() in objects
