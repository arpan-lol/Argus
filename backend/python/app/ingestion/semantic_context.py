import re


_NEGATION = re.compile(r"\b(?:not|no|never|neither|without|doesn't|didn't|isn't|aren't|wasn't|weren't|cannot|can't|won't|wouldn't|shouldn't|fails? to|unable to|instead of|rather than)\b", re.I)
_SPECULATION = re.compile(r"\b(?:may|might|could|possibly|potentially|appears? to|seems? to|suggests?|hypothes(?:is|ized|ized)|likely|unlikely)\b", re.I)
_MODALITY = re.compile(r"\b(?:must|shall|required to|needs? to|should|ought to|may|might|can|could|will|would|prohibited|permitted|allowed)\b", re.I)
_CONDITION = re.compile(r"\b(?:if|when|whenever|unless|provided that|assuming|in case|under the condition)\b", re.I)
_IDENTIFIER = re.compile(r"\b(?:10\.\d{4,9}/[-._;()/:A-Z0-9]+|CVE-\d{4}-\d{4,}|CWE-\d+|(?:attack-pattern|campaign|course-of-action|group|identity|indicator|intrusion-set|malware|marking-definition|note|observed-data|relationship|report|sighting|threat-actor|tool|vulnerability)--[0-9a-f-]{36})\b", re.I)
_CLOSED_CLASS = frozenset("a an the this that these those i me my we us our you your he him his she her it its they them their who whom which what and or but nor so yet for as at by from in into of off on onto out over per through to under up with within without about above after against along among around before behind below beneath beside between beyond during except inside near outside past since than till toward towards via if unless because while where when how why not no all any each either enough every few many more most much neither one other several some both same such then there here only very just also own once again ever never still already being been am is are was were be become have has had do does did can could may might must shall should will would " .split())


def stable_identifier(name):
    match = _IDENTIFIER.search(name)
    return match.group(0).rstrip(".,;)") if match else None


def valid_entity_mention(name, label, source_text):
    if not isinstance(name, str) or not isinstance(label, str) or not name.strip() or not label.strip():
        return False
    value = name.strip()
    if stable_identifier(value):
        return True
    if not any(char.isalnum() for char in value):
        return False
    if not any(char.isalpha() for char in value) and len(value) < 3:
        return False
    if value.casefold() in _CLOSED_CLASS and not (len(value) > 1 and value.isupper()):
        return False
    if len(value.split()) == 1 and value.casefold() in _CLOSED_CLASS:
        return False
    if not source_text:
        return False
    return True


def source_context(text):
    normalized = " ".join(text.split())
    negation = _NEGATION.search(normalized)
    speculation = _SPECULATION.search(normalized)
    modality = _MODALITY.search(normalized)
    conditions = [match.group(0) for match in _CONDITION.finditer(normalized)]
    alternatives = bool(re.search(r"\b(?:instead of|rather than)\b", normalized, re.I))
    signals = []
    if negation:
        signals.append("negation_or_alternative_cue")
    if speculation:
        signals.append("speculation_cue")
    if modality:
        signals.append("modality_cue")
    if conditions:
        signals.append("condition_cue")
    return {
        "polarity": "unclassified",
        "polarityStatus": "source_cues_detected_unclassified",
        "qualifierStatus": "needs_context_review" if signals else "unverified_no_context_cue",
        "traversalStatus": "needs_context_review" if signals else "unverified_no_context_cue",
        "sourceContextSignals": signals,
        "negationCue": negation.group(0) if negation else None,
        "speculationCue": speculation.group(0) if speculation else None,
        "modalityCue": modality.group(0) if modality else None,
        "conditions": [{"name": "source_condition_cue", "value": cue, "unit": None} for cue in conditions],
        "alternativeCue": alternatives,
    }


def sentence_context(text, left, right):
    start = max(text.rfind(mark, 0, left) for mark in (".", "!", "?", ";", "\n")) + 1
    ends = [position for mark in (".", "!", "?", ";", "\n") if (position := text.find(mark, right)) >= 0]
    end = min(ends) + 1 if ends else len(text)
    return start, end, text[start:end]
