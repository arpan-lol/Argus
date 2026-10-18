import re


_NEGATION = re.compile(r"\b(?:not|no|never|neither|without|doesn't|didn't|isn't|aren't|wasn't|weren't|cannot|can't|won't|wouldn't|shouldn't|fails? to|unable to|instead of|rather than)\b", re.I)
_SPECULATION = re.compile(r"\b(?:may|might|could|possibly|potentially|appears? to|seems? to|suggests?|hypothes(?:is|ized|ized)|likely|unlikely)\b", re.I)
_MODALITY = re.compile(r"\b(?:must|shall|required to|needs? to|should|ought to|may|might|can|could|will|would|prohibited|permitted|allowed)\b", re.I)
_CONDITION = re.compile(r"\b(?:if|when|whenever|unless|provided that|assuming|in case|under the condition)\b", re.I)
_EXCEPTION = re.compile(r"\b(?:except(?: for)?|other than|subject to|notwithstanding|save for|excluding|with the exception of)\b", re.I)
_EXPERIENCER = re.compile(r"\b(?:family history|mother|father|sibling|relative|caregiver|patient reports?|patient denies?|history of)\b", re.I)
_TEMPORALITY = re.compile(r"\b(?:currently|previously|formerly|prior to|past history|no longer|resolved|at age \d+|during pregnancy|postpartum|before treatment|after treatment|onset|recurrence)\b", re.I)
_REFERENCE_ROLE = re.compile(r"^\s*(?:references|bibliography|works cited|further reading)\s*:?\s*$|\bcited in\b", re.I | re.M)
_ILLUSTRATION = re.compile(r"\b(?:for example|e\.g\.|i\.e\.|example|illustrative|hypothetical|toy example)\b", re.I)
_INDEFINITE_PRONOUNS = frozenset("anybody anyone anything everybody everyone everything somebody someone something nobody no-one none".split())
_IDENTIFIER = re.compile(r"\b(?:10\.\d{4,9}/[-._;()/:A-Z0-9]+|CVE-\d{4}-\d{4,}|CWE-\d+|(?:attack-pattern|campaign|course-of-action|group|identity|indicator|intrusion-set|malware|marking-definition|note|observed-data|relationship|report|sighting|threat-actor|tool|vulnerability)--[0-9a-f-]{36})\b", re.I)
_CLOSED_CLASS = frozenset("a an the this that these those i me my we us our you your he him his she her it its they them their who whom which what and or but nor so yet for as at by from in into of off on onto out over per through to under up with within without about above after against along among around before behind below beneath beside between beyond during except inside near outside past since than till toward towards via if unless because while where when how why not no all any each either enough every few many more most much neither one other several some both same such then there here only very just also own once again ever never still already being been am is are was were be become have has had do does did can could may might must shall should will would " .split())
_NUMBER_WITH_UNIT = re.compile(r"(?<![\w])(?P<number>[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?)(?P<unit>\s*(?:%|°\s?[CFK]|[A-Za-zµμΩ]+(?:[./·][A-Za-zµμΩ0-9]+)*(?:\^-?\d+)?|[A-Za-z0-9]+)?)")


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
    if (value.casefold() in _CLOSED_CLASS or value.casefold() in _INDEFINITE_PRONOUNS) and not (len(value) > 1 and value.isupper()):
        return False
    if not source_text:
        return False
    return True


def source_context(text):
    negation = _NEGATION.search(text)
    speculation = _SPECULATION.search(text)
    modality = _MODALITY.search(text)
    conditions = [match.group(0) for match in _CONDITION.finditer(text)]
    alternatives = bool(re.search(r"\b(?:instead of|rather than)\b", text, re.I))
    exception = _EXCEPTION.search(text)
    experiencer = _EXPERIENCER.search(text)
    temporality = _TEMPORALITY.search(text)
    measurements = []
    identifiers = [match.span() for match in _IDENTIFIER.finditer(text)]
    for match in _NUMBER_WITH_UNIT.finditer(text):
        if any(start <= match.start() < end for start, end in identifiers):
            continue
        raw_unit = match.group("unit")
        unit = raw_unit.strip() or None
        end = match.end() if unit else match.start("number") + len(match.group("number"))
        measurements.append({"value": match.group("number"), "unitCandidate": unit, "quote": text[match.start():end], "startOffset": match.start(), "endOffset": end})
    signals = []
    if negation:
        signals.append("negation_or_alternative_cue")
    if speculation:
        signals.append("speculation_cue")
    if modality:
        signals.append("modality_cue")
    if conditions:
        signals.append("condition_cue")
    if exception:
        signals.append("exception_cue")
    if experiencer:
        signals.append("experiencer_cue")
    if temporality:
        signals.append("temporality_cue")
    return {
        "polarity": "unclassified",
        "polarityStatus": "source_cues_detected_unclassified",
        "qualifierStatus": "needs_context_review" if signals else "unverified_no_context_cue",
        "traversalStatus": "needs_context_review" if signals else "unverified_no_context_cue",
        "sourceContextSignals": signals,
        "negationCue": negation.group(0) if negation else None,
        "speculationCue": speculation.group(0) if speculation else None,
        "modalityCue": modality.group(0) if modality else None,
        "exceptionCue": exception.group(0) if exception else None,
        "experiencerCue": experiencer.group(0) if experiencer else None,
        "temporalityCue": temporality.group(0) if temporality else None,
        "sourceMeasurements": measurements,
        "measurementStatus": "unclassified_context_only" if measurements else "none_detected",
        "conditions": [{"name": "source_condition_cue", "value": cue, "unit": None} for cue in conditions],
        "alternativeCue": alternatives,
    }


def sentence_context(text, left, right):
    boundaries = list(re.finditer(r"[.!?;](?:[ \t]+|\n+)|\n+", text))
    start = max((match.end() for match in boundaries if match.end() <= left), default=0)
    end = next((match.start() + 1 for match in boundaries if match.start() >= right), len(text))
    return start, end, text[start:end]


def relation_scope(text, left, right, context):
    between = text[left:right]
    signals = []
    if re.search(r"[.!?;](?:[ \t]+|\n+)|\n+", between):
        signals.append("cross_sentence_or_line")
    if len(between.split()) > 64:
        signals.append("long_entity_gap")
    if _REFERENCE_ROLE.search(context):
        signals.append("reference_or_bibliography_role")
    if _ILLUSTRATION.search(context):
        signals.append("illustrative_or_hypothetical_context")
    return {
        "relationScopeStatus": "needs_context_review" if signals else "same_sentence_scope_unverified",
        "relationScopeSignals": signals,
        "traversalStatus": "needs_context_review" if signals else "unverified_no_context_cue",
    }
