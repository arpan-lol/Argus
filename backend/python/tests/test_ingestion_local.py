import json
import zipfile

import pytest

from app.ingestion.archives import expand_archive, source_name
from app.ingestion.categories import seed_settings, validate_categories
from app.ingestion.code_parser import python_structure
from app.ingestion.local_extraction import convert_output
from app.ingestion.profiles import run_discovery, sampled_batches


def test_code_parser_builds_source_anchored_syntax_edges():
    text = '''"""Résumé module."""\nfrom pathlib import Path\n\nclass Graph(Path):\n    """Graph docs."""\n    def save(self, item):\n        return persist(item)\n\ndef persist(item):\n    return item\n'''
    graph = python_structure(text, "src/argus/graph.py")
    assert graph["module"] == "argus.graph"
    assert any(edge["predicate"] == "imports" and edge["quote"].startswith("from pathlib") for edge in graph["relationships"])
    assert any(edge["predicate"] == "inherits_from" and edge["resolution"] == "import_name" for edge in graph["relationships"])
    assert any(edge["predicate"] == "calls" and edge["object"].endswith("persist") and edge["resolution"] == "local_name" for edge in graph["relationships"])
    for item in graph["entities"] + graph["relationships"]:
        assert text[item["start"]:item["end"]] == item["quote"]
    persist = next(item for item in graph['entities'] if item['name'] == 'argus.graph.persist')
    assert len(persist['occurrences']) == 2
    assert all(text[item['start']:item['end']] == item['quote'] for item in persist['occurrences'])


def test_category_seeds_are_selected_and_bounded():
    settings = seed_settings(["code_repository"], entity_cap=5, relationship_cap=4)
    assert len(settings["entityTypes"]) <= 5
    assert len(settings["relationshipTypes"]) <= 4
    assert {"defines", "calls", "imports"}.intersection(settings["relationshipTypes"])
    assert validate_categories(["code_repository", "code_repository"]) == ["code_repository"]
    with pytest.raises(ValueError):
        validate_categories([])


def test_local_extraction_preserves_exact_entity_and_relation_spans():
    chunk = {"text": "GraphStore calls persist(node).", "startOffset": 100}
    result = convert_output(chunk, {
        "entities": [
            {"start": 0, "end": 10, "text": "GraphStore", "label": "class", "score": 0.91},
            {"start": 17, "end": 24, "text": "persist", "label": "function", "score": 0.87},
        ],
        "relationships": [{"head": {"start": 0, "end": 10}, "tail": {"start": 17, "end": 24}, "relation": "calls", "score": 0.8}],
    })
    assert [item["quote"] for item in result["entities"]] == ["GraphStore", "persist"]
    assert result["relationships"][0]["quote"] == "GraphStore calls persist(node)."
    assert result["relationships"][0]["polarity"] == "unclassified"
    assert result["entities"][0]["sourceSpan"]["startOffset"] == 100


def test_discovery_has_no_call_count_cap_and_finishes_inflight_response():
    class Ledger:
        def __init__(self):
            self.rows = []

        def reserve(self, tokens, payload):
            self.rows.append([len(self.rows) + 1, tokens, "reserved"])
            return self.rows[-1][0]

        def complete(self, sequence, status, payload):
            self.rows[sequence - 1][2] = status

    class Provider:
        def __init__(self, delay):
            self.delay = delay
            self.calls = 0
            self.now = 0

        def structured(self, schema, prompt, payload, start_before=None):
            assert self.now < start_before
            self.calls += 1
            self.now += self.delay
            return {"entityTypes": [], "relationshipTypes": [], "rationale": "existing labels fit"}

        @staticmethod
        def safe_error(error):
            return str(error)

    config = {"profileTokenEncoding": "o200k_base", "profileTokenBudget": 100000, "profileStartWindowSeconds": 30, "profileOutputTokens": 32, "profileEntityCap": 24, "profileRelationshipCap": 32}
    settings = {"entityTypes": ["class"], "relationshipTypes": ["defines"], "rationale": "defaults"}
    batches = [([{"sourceId": str(i), "text": "source"}], []) for i in range(20)]
    slow = Provider(31)
    run_discovery(settings.copy(), batches, "code repo", config, slow, Ledger(), 30, clock=lambda: slow.now)
    assert slow.calls == 1

    fast = Provider(0)
    ledger = Ledger()
    run_discovery(settings.copy(), batches[:8], "code repo", config, fast, ledger, 30, clock=lambda: fast.now)
    assert fast.calls == 8
    assert all(row[2] == "complete" for row in ledger.rows)


def test_discovery_does_not_dispatch_without_budget():
    from unittest.mock import Mock
    provider = Mock()
    ledger = Mock()
    ledger.reserve.return_value = None
    config = {'profileTokenEncoding': 'o200k_base', 'profileTokenBudget': 100, 'profileStartWindowSeconds': 30, 'profileOutputTokens': 64}
    result = run_discovery({'entityTypes': ['class'], 'relationshipTypes': ['calls']}, [([{'sourceId': 'one', 'text': 'source'}], [])], 'repo', config, provider, ledger, 30, clock=lambda: 0)
    assert result['sampling']['stopReason'] == 'token_budget'
    provider.structured.assert_not_called()


def test_provider_checks_dispatch_window_after_rate_wait():
    from unittest.mock import patch
    from app.ingestion.providers import Providers, CallWindowClosed
    provider = Providers({'provider': 'azure_openai', 'extractionModel': 'test', 'maxOutputTokens': 64, 'modelTimeoutSeconds': 120, 'promptVersion': 'test'})
    with patch('app.ingestion.ingestion_roles.validate_ingestion_llm'), patch.object(provider, 'llm_profile', return_value=('azure_openai', 'https://example.test/openai/v1', None)), patch.object(provider, 'credentials', return_value='synthetic'), patch.object(provider, 'wait_for_capacity', return_value=10), patch('app.ingestion.providers.time.time', return_value=31):
        with pytest.raises(CallWindowClosed):
            provider.structured(object, 'prompt', {}, start_before=30)


def test_sampled_batches_respect_token_boundaries(tmp_path):
    source_path = tmp_path / "example.py"
    source_path.write_text("\n".join(f"value_{index} = {index}" for index in range(100)), encoding="utf-8")
    import hashlib
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    config = {"profileTokenEncoding": "o200k_base", "profileTokenBudget": 24000, "profileBatchTokens": 256, "chunkTokens": 80, "maxExtractedTextCharacters": 10000, "maxDecompressedBytes": 10000, "maxArchiveMembers": 50, "maxUploadBytes": 10000, "categories": ["code_repository"], "layoutParser": "text"}
    batches = list(sampled_batches([{"originalPath": str(source_path), "revision": digest, "sourceId": "s1", "filename": "example.py"}], config))
    import tiktoken
    encoding = tiktoken.get_encoding(config["profileTokenEncoding"])
    assert batches
    assert all(sum(len(encoding.encode(item['text'], disallowed_special=())) for item in batch) <= 256 for batch, _ in batches)


def test_archive_rejects_path_traversal_and_reports_skips(tmp_path):
    with pytest.raises(ValueError):
        source_name("../outside.py")
    archive_path = tmp_path / "repo.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("repo/src/app.py", "print('ok')")
        archive.writestr("repo/.env", "secret")
        archive.writestr("repo/image.png", b"fake")
    temporary = []
    extracted, report = expand_archive(archive_path, "repo.zip", {"maxArchiveMembers": 10, "maxDecompressedBytes": 10000, "maxUploadBytes": 5000}, temporary)
    assert [name for _, name in extracted] == ["src/app.py"]
    assert len(report["skipped"]) == 2
    for path in temporary:
        path.unlink(missing_ok=True)


def test_embedding_inputs_are_checked_before_any_request():
    from app.ingestion.embedding_limits import input_tokens
    assert input_tokens(['one source']) > 0
    for inputs in [[], [''], ['source'] * 2049, ['hello ' * 9000]]:
        with pytest.raises(ValueError):
            input_tokens(inputs)
