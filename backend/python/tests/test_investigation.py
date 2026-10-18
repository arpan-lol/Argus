import copy
import json
import os
from contextlib import contextmanager
from unittest import TestCase, mock

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from openai import OpenAI

from app.investigation.runtime import Investigation, RunBudgetReached, State, collect_sources, compact, deduplicate_tool_passages, validate_sources
from app.investigation import service
from app.retrieval.contracts import TOOLS


class Ledger:
    def __init__(self):
        self.budget = {}
        self.results = {}
        self.row = None

    def execute(self, query, params=()):
        if query.startswith("SELECT budget"):
            self.row = {"budget": copy.deepcopy(self.budget)}
        elif query.startswith("UPDATE chat_runs SET budget"):
            self.budget = copy.deepcopy(params[0].obj)
        elif query.startswith("SELECT payload FROM chat_tool_results"):
            self.row = {"payload": self.results[params]} if params in self.results else None
        elif query.startswith("INSERT INTO chat_tool_results"):
            self.results[params[:2]] = copy.deepcopy(params[2].obj)
        return self

    def fetchone(self):
        return self.row

    @contextmanager
    def connection(self):
        yield self


def initial():
    return {"messages": [], "pending": [], "sources": {}, "report": None, "tool_count": 0, "seen_calls": [], "draft": None}


def call(name, arguments, identifier="call-1"):
    return {"role": "assistant", "tool_calls": [{"id": identifier, "function": {"name": name, "arguments": json.dumps(arguments)}}]}


def report(purpose="conversation", citations=None, text="A bounded answer"):
    return {"purpose": purpose, "paragraphs": [{"text": text, "citations": citations or []}], "comparison": [], "gaps": []}


def source():
    return {"jobId": "job-1", "chunkId": "chunk-1", "revisionId": "revision-1", "processingVersion": "version-1", "documentId": "doc-1", "documentTitle": "Test publication", "sectionTitle": "Results", "startOffset": 20, "endOffset": 25, "text": "hello"}


class InvestigationTest(TestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.patch = mock.patch("app.investigation.runtime.connection", self.ledger.connection)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.events = []
        self.row = {"id": "test-run", "request": {"query": "hello", "history": [], "graph_expansion": False}, "configuration": {
            "provider": "google", "chatProvider": "azure_openai", "chatBaseUrl": "https://test.example/openai/v1", "chatApiVersion": None, "chatApi": "responses", "chatModel": "gpt-5", "chatPrices": None,
            "coverage": {"publishedDocuments": 1}, "chatLimits": {"modelCalls": 8, "toolCalls": 8, "totalTokens": 64000, "outputTokens": 2048, "contextTokens": 10000, "elapsedMs": 180000, "costUsd": .25}}}

    def runtime(self, model, tool=None):
        return Investigation(self.row, lambda *event: self.events.append(event), model_call=model, tool_call=tool)

    def test_greeting_finishes_without_retrieval(self):
        model = mock.Mock(return_value=({"role": "assistant", "content": json.dumps(report())}, {"total_tokens": 42}))
        tool = mock.Mock()
        state = self.runtime(model, tool).graph(InMemorySaver()).invoke(initial(), {"configurable": {"thread_id": "greeting"}})
        self.assertEqual(state["report"]["purpose"], "conversation")
        tool.assert_not_called()
        self.assertEqual(model.call_count, 1)
        self.assertNotIn("finish_report", [item["function"]["name"] for item in model.call_args.args[1]])
        self.assertEqual(self.ledger.budget["reportedTokens"], 42)

    def test_empty_project_still_enters_model_tool_loop(self):
        self.row["configuration"]["coverage"] = {"publishedDocuments": 0, "legacyDocuments": 6013}
        self.row["configuration"]["workspaceDescription"] = "Materials research"
        self.row["request"]["graph_expansion"] = True
        model = mock.Mock(return_value=({"role": "assistant", "content": json.dumps(report())}, {"total_tokens": 120}))
        tool = mock.Mock()
        state = self.runtime(model, tool).graph(InMemorySaver()).invoke(initial(), {"configurable": {"thread_id": "empty-project"}})
        self.assertEqual(state["report"]["purpose"], "conversation")
        self.assertEqual(model.call_count, 1)
        messages, definitions = model.call_args.args
        self.assertGreaterEqual(len(definitions), 10)
        self.assertIn("review_path", [item["function"]["name"] for item in definitions])
        self.assertIn("load_bearing", [item["function"]["name"] for item in definitions])
        self.assertIn("inspect_available_tools", [item["function"]["name"] for item in definitions])
        self.assertIn("Materials research", messages[0]["content"])
        self.assertEqual(messages[-1]["content"], "hello")
        tool.assert_not_called()

    def test_tool_inventory_and_followup_are_model_driven(self):
        self.row["configuration"]["coverage"] = {"publishedDocuments": 0, "legacyDocuments": 6013}
        self.row["request"]["graph_expansion"] = True
        self.row["request"].update(query="list only the read_ ones", history=[
            {"role": "user", "content": "tell me how many tools you have & also their names"},
            {"role": "assistant", "content": "Argus has nine tools, including read_chunks."},
        ])
        model = mock.Mock(side_effect=[
            (call("inspect_available_tools", {}, "catalog-followup"), {"total_tokens": 120}),
            ({"role": "assistant", "content": json.dumps(report(text="read_chunks"))}, {"total_tokens": 80}),
        ])
        state = self.runtime(model).graph(InMemorySaver()).invoke(initial(), {"configurable": {"thread_id": "inventory-followup"}})
        self.assertEqual(state["report"]["paragraphs"][0]["text"], "read_chunks")
        self.assertEqual(model.call_count, 2)
        messages, definitions = model.call_args.args
        self.assertIn("list only the read_ ones", json.dumps(messages))
        self.assertIn("Argus has nine tools", json.dumps(messages))
        self.assertIn("read_chunks", [item["function"]["name"] for item in definitions])
        self.assertEqual(self.ledger.budget["modelCalls"], 2)

    def test_tool_catalog_is_inspected_inside_agent_loop(self):
        self.row["configuration"]["coverage"] = {"publishedDocuments": 0}
        self.row["request"]["graph_expansion"] = True
        self.row["request"]["query"] = "list all tools"
        model = mock.Mock(side_effect=[
            (call("inspect_available_tools", {}, "catalog"), {"total_tokens": 120}),
            ({"role": "assistant", "content": json.dumps(report(text="There are nine retrieval tools."))}, {"total_tokens": 90}),
        ])
        tool = mock.Mock()
        state = self.runtime(model, tool).graph(InMemorySaver()).invoke(initial(), {"configurable": {"thread_id": "catalog-tool"}})
        self.assertEqual(state["report"]["purpose"], "conversation")
        self.assertEqual(state["tool_count"], 1)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(json.loads(model.call_args.args[0][-1]["content"])["retrievalToolCount"], len(TOOLS))
        self.assertIn("rank_entities", json.dumps(model.call_args.args[0]))
        tool.assert_not_called()

    def test_empty_project_can_run_retrieval_tool_before_finishing(self):
        self.row["configuration"]["coverage"] = {"publishedDocuments": 0, "legacyDocuments": 6013}
        self.row["request"]["query"] = "Find source passages about batteries"
        model = mock.Mock(side_effect=[
            (call("search_sources", {"query": "batteries"}), {"total_tokens": 120}),
            ({"role": "assistant", "content": json.dumps(report("insufficient_support", text="No published sources are available."))}, {"total_tokens": 90}),
        ])
        tool = mock.Mock(return_value={"outcome": "no_published_sources", "items": []})
        state = self.runtime(model, tool).graph(InMemorySaver()).invoke(initial(), {"configurable": {"thread_id": "empty-retrieval"}})
        self.assertEqual(state["report"]["purpose"], "insufficient_support")
        self.assertEqual(state["tool_count"], 1)
        self.assertEqual(model.call_count, 2)
        tool.assert_called_once_with("search_sources", {"query": "batteries"})

    def test_unknown_lookup_cannot_end_as_missing_source_support(self):
        self.row["request"]["query"] = "Compare the documented incidents CASE-A and CASE-B"
        model = mock.Mock(side_effect=[
            (call("read_chunks", {"chunk_ids": ["CASE-A", "CASE-B"]}, "wrong-ids"), None),
            ({"role": "assistant", "content": json.dumps(report("insufficient_support", text="No sources document these incidents."))}, None),
            (call("search_sources", {"query": "CASE-A CASE-B", "mode": "lexical"}, "discover"), None),
            ({"role": "assistant", "content": json.dumps(report("source_answer", ["S1"], text="The retrieved source documents both incidents."))}, None),
        ])
        tool = mock.Mock(side_effect=[
            {"outcome": "unknown_chunk", "items": [], "unknownChunkIds": ["CASE-A", "CASE-B"], "inputError": True, "recovery": "Discover chunk IDs with search_sources first."},
            {"outcome": "answered", "items": [source()]},
        ])
        state = self.runtime(model, tool).graph(InMemorySaver()).invoke(initial(), {"configurable": {"thread_id": "lookup-recovery"}})
        self.assertEqual(state["report"]["purpose"], "source_answer")
        self.assertEqual(state["tool_count"], 2)
        self.assertEqual(model.call_count, 4)
        repair_messages, repair_tools = model.call_args_list[2].args
        self.assertIn("search_sources", [item["function"]["name"] for item in repair_tools])
        self.assertIn("lookup", json.dumps(repair_messages).lower())

    def test_real_empty_search_can_finish_after_invalid_lookup(self):
        model = mock.Mock(side_effect=[
            (call("read_chunks", {"chunk_ids": ["human-label"]}, "invalid"), None),
            (call("search_sources", {"query": "human-label", "mode": "lexical"}, "search"), None),
            ({"role": "assistant", "content": json.dumps(report("insufficient_support", text="The bounded source search found no matches."))}, None),
        ])
        tool = mock.Mock(side_effect=[{"items": [], "unknownChunkIds": ["human-label"]}, {"outcome": "not_found", "items": []}])
        state = self.runtime(model, tool).graph(InMemorySaver()).invoke(initial(), {"configurable": {"thread_id": "empty-after-recovery"}})
        self.assertEqual(state["report"]["purpose"], "insufficient_support")
        self.assertEqual(tool.call_count, 2)

    def test_partial_lookup_does_not_discard_a_supported_answer(self):
        state = initial()
        state.update(tool_count=1, seen_calls=[json.dumps(["read_chunks", {"chunk_ids": ["chunk-1"]}], sort_keys=True)], sources={"S1": source()}, messages=[{"role": "tool", "tool_call_id": "partial", "content": json.dumps({"outcome": "partial", "items": [source()], "inputError": True, "unknownChunkIds": ["unavailable"]})}])
        result = self.runtime(mock.Mock()).check_report(report("source_answer", ["S1"]), state)
        self.assertEqual(result.purpose, "source_answer")
        with self.assertRaisesRegex(ValueError, "lookup"):
            self.runtime(mock.Mock()).check_report(report("insufficient_support"), state)

    def test_schema_errors_are_recoverable_without_running_bad_tool(self):
        model = mock.Mock(side_effect=[
            (call("search_sources", {"query": "valid query", "limit": 900}, "bad-limit"), None),
            (call("search_sources", {"query": "valid query", "limit": 5, "mode": "lexical"}, "valid-limit"), None),
            ({"role": "assistant", "content": json.dumps(report("source_answer", ["S1"]))}, None),
        ])
        tool = mock.Mock(return_value={"items": [source()]})
        state = self.runtime(model, tool).graph(InMemorySaver()).invoke(initial(), {"configurable": {"thread_id": "schema-recovery"}})
        self.assertEqual(state["report"]["purpose"], "source_answer")
        tool.assert_called_once_with("search_sources", {"query": "valid query", "limit": 5, "mode": "lexical"})
        self.assertEqual(state["tool_count"], 2)

    def test_validation_repair_can_use_tools_from_saved_synthesis_checkpoint(self):
        saver = InMemorySaver()
        legacy = StateGraph(State)
        legacy.add_node("plan", lambda state: state)
        def interrupted(state):
            raise RuntimeError("interrupted legacy synthesis")
        legacy.add_node("synthesize", interrupted)
        legacy.add_edge(START, "plan")
        legacy.add_edge("plan", "synthesize")
        legacy.add_edge("synthesize", END)
        options = {"configurable": {"thread_id": "legacy-synthesis"}}
        with self.assertRaisesRegex(RuntimeError, "interrupted legacy"):
            legacy.compile(checkpointer=saver).invoke(initial(), options)
        model = mock.Mock(side_effect=[
            (call("search_sources", {"query": "repair", "mode": "lexical"}, "repair"), None),
            ({"role": "assistant", "content": json.dumps(report("source_answer", ["S1"]))}, None),
        ])
        tool = mock.Mock(return_value={"items": [source()]})
        state = self.runtime(model, tool).graph(saver).invoke(None, options)
        self.assertEqual(state["report"]["purpose"], "source_answer")
        self.assertEqual(tool.call_count, 1)

    def test_invalid_tool_catalog_citation_gets_model_feedback(self):
        self.row["configuration"]["coverage"] = {"publishedDocuments": 0, "legacyDocuments": 6013}
        self.row["request"]["query"] = "list all tools"
        invalid = {**report(text="The tools are listed below"), "comparison": [{"subject": "search_sources", "finding": "Searches sources", "conditions": "", "citations": ["_system"]}]}
        model = mock.Mock(side_effect=[
            ({"role": "assistant", "content": json.dumps(invalid)}, {"total_tokens": 100}),
            (call("inspect_available_tools", {}, "catalog-repair-tool"), {"total_tokens": 90}),
            ({"role": "assistant", "content": json.dumps(report(text="search_sources and find_entities are tools"))}, {"total_tokens": 80}),
        ])
        state = self.runtime(model).graph(InMemorySaver()).invoke(initial(), {"configurable": {"thread_id": "catalog-repair"}})
        self.assertEqual(state["report"]["purpose"], "conversation")
        self.assertEqual(model.call_count, 3)
        self.assertIn("_system", json.dumps(model.call_args_list[1].args[0]))
        self.assertIn("search_sources", [item["function"]["name"] for item in model.call_args.args[1]])

    def test_checkpoint_resume_keeps_sources_tools_and_budget(self):
        self.row["request"]["query"] = "Find the published hello source"
        model = mock.Mock(side_effect=[(call("search_sources", {"query": "hello", "mode": "lexical"}), None), RuntimeError("interrupted")])
        tool = mock.Mock(return_value={"outcome": "answered", "items": [source()]})
        runtime = self.runtime(model, tool)
        saver = InMemorySaver()
        options = {"configurable": {"thread_id": "resume"}}
        graph = runtime.graph(saver)
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            graph.invoke(initial(), options)
        self.assertEqual(self.ledger.budget["modelCalls"], 2)
        runtime.model_call = mock.Mock(return_value=(call("finish_report", report("source_answer", ["S1"]), "finish"), None))
        state = graph.invoke(None, options)
        self.assertEqual(state["tool_count"], 1)
        self.assertEqual(state["sources"]["S1"]["text"], "hello")
        self.assertEqual(self.ledger.budget["modelCalls"], 3)
        self.assertEqual(tool.call_count, 1)

    def test_forged_or_unsupported_citations_rejected(self):
        runtime = self.runtime(mock.Mock())
        with self.assertRaises(ValueError):
            runtime.check_report(report("source_answer", ["S99"]), initial())
        with self.assertRaises(ValueError):
            runtime.check_report(report("source_answer"), initial())
        with self.assertRaises(ValueError):
            validate_sources({}, ["S99"], {})

    def test_native_record_ids_are_preserved_and_checked_against_cited_text(self):
        state = initial()
        state.update(tool_count=1, sources={"S1": {**source(), "text": "[CASE-014] Service Alpha recovered after a documented retry.\n[CASE-015] Service Alphabet is unrelated."}})
        candidate = report("source_answer", ["S1"])
        candidate["comparison"] = [{"subject": "Service Alpha", "finding": "Documented recovery", "conditions": "", "citations": ["S1"]}]
        result = self.runtime(mock.Mock()).check_report(candidate, state)
        self.assertIn("CASE-014", result.comparison[0].finding)
        self.assertNotIn("CASE-015", result.comparison[0].finding)
        self.assertEqual(result.comparison[0].citations, ["S1"])

    def test_native_records_cannot_silently_choose_between_source_occurrences(self):
        state = initial()
        state.update(tool_count=1, sources={"S1": {**source(), "text": "[CASE-014] Service Alpha recovered."}, "S2": {**source(), "jobId": "other-job", "text": "[CASE-015] Service Alpha failed."}})
        candidate = report("source_answer", ["S1"])
        candidate["comparison"] = [{"subject": "Service Alpha", "finding": "Documented recovery", "conditions": "", "citations": ["S1"]}]
        result = self.runtime(mock.Mock()).check_report(candidate, state)
        self.assertIn("CASE-014", result.comparison[0].finding)
        self.assertNotIn("CASE-015", result.comparison[0].finding)

    def test_tool_replay_uses_saved_receipt(self):
        state = initial()
        state["pending"] = call("search_sources", {"query": "hello"})["tool_calls"]
        self.ledger.results[("test-run", "call-1")] = {"items": [source()], "outcome": "answered"}
        tool = mock.Mock()
        result = self.runtime(mock.Mock(), tool).tools(state)
        tool.assert_not_called()
        self.assertEqual(result["tool_count"], 1)
        self.assertEqual(result["sources"]["S1"]["chunkId"], "chunk-1")

    def test_budgets_cannot_reset_on_resume(self):
        self.ledger.budget = {"modelCalls": 8, "reservedTokens": 100}
        with self.assertRaises(RunBudgetReached):
            self.runtime(mock.Mock()).reserve_model(10)
        self.assertEqual(self.ledger.budget["modelCalls"], 8)

    def test_duplicate_calls_are_bounded(self):
        arguments = {"query": "hello"}
        state = initial()
        state["pending"] = call("search_sources", arguments)["tool_calls"]
        state["seen_calls"] = [json.dumps(["search_sources", arguments], sort_keys=True)]
        tool = mock.Mock()
        result = self.runtime(mock.Mock(), tool).tools(state)
        tool.assert_not_called()
        self.assertEqual(result["tool_count"], 1)
        self.assertIn("duplicate_call", result["messages"][-1]["content"])

    def test_graph_tools_hidden_when_disabled(self):
        names = [item["function"]["name"] for item in self.runtime(mock.Mock()).definitions(initial())]
        self.assertNotIn("find_paths", names)
        self.assertNotIn("expand_connections", names)
        self.assertNotIn("finish_report", names)
        self.assertIn("search_sources", names)

    def test_source_references_deduplicate(self):
        sources = collect_sources({"items": [source(), source()]}, {})
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources["S1"]["key"], ["job-1", "chunk-1", 20, 25])

    def test_search_preserves_late_qualifying_passages_and_all_hit_identities(self):
        self.row["request"]["query"] = "Find all services hosted in WEST-3 that read DATA-ATLAS"
        text = "Unrelated operational notes.\n" * 900 + "[R066] Billing Export reads DATA-ATLAS.\n[R068] Billing Export is hosted in WEST-3."
        items = [{**source(), "chunkId": f"chunk-{index}", "text": text if index == 0 else f"Other source passage {index}.", "endOffset": 20 + (len(text) if index == 0 else len(f"Other source passage {index}.")), "textTruncated": False, "processing": {"glinerCoverage": {"windows": [{"startOffset": 0, "endOffset": 3000}] * 30}, "fallback": True, "llmVerified": False}} for index in range(9)]
        runtime = self.runtime(mock.Mock(), mock.Mock(return_value={"outcome": "answered", "items": items, "truncations": []}))
        state = initial()
        message = call("search_sources", {"query": self.row["request"]["query"], "mode": "lexical"})
        state.update(pending=message["tool_calls"], messages=[message])
        state = runtime.tools(state)
        packed = json.loads(state["messages"][-1]["content"])
        self.assertEqual(len(packed["items"]), 9)
        self.assertEqual({item["chunkId"] for item in packed["items"]}, {f"chunk-{index}" for index in range(9)})
        messages = runtime.messages(state, 7000)
        content = json.dumps(messages)
        self.assertIn("[R066] Billing Export reads DATA-ATLAS", content)
        self.assertIn("[R068] Billing Export is hosted in WEST-3", content)
        self.assertTrue(packed["items"][0]["processing"]["fallback"])
        excerpt = packed["items"][0]
        self.assertTrue(excerpt["textTruncated"])
        self.assertEqual(text[excerpt["contextExcerptStartOffset"] - 20:excerpt["contextExcerptEndOffset"] - 20], excerpt["text"])
        self.assertLessEqual(len(runtime.encoding.encode(state["messages"][-1]["content"])), 2000)
        event = next(payload for kind, payload in self.events if kind == "tool_end")
        self.assertEqual(event["modelContext"]["shownItems"], 9)
        self.assertTrue(event["modelContext"]["excerptedPassages"])

    def test_compaction_preserves_graph_direction_polarity_and_full_lists(self):
        payload = {"items": [{"predicate": "writes", "polarity": "negated", "subject": {"id": "producer"}, "object": {"id": "dataset"}, "conditions": [{"value": str(index)} for index in range(12)]} for _ in range(12)], "paths": [{"hops": list(range(12))}], "truncations": [str(index) for index in range(12)]}
        self.assertEqual(compact(payload), payload)

    def test_source_text_is_not_duplicated_in_model_context(self):
        self.row["request"]["query"] = "Find the relevant source"
        runtime = self.runtime(mock.Mock(), mock.Mock(return_value={"outcome": "answered", "items": [{**source(), "text": "source-only-sentinel"}]}))
        state = initial()
        message = call("search_sources", {"query": "relevant", "mode": "lexical"})
        state.update(pending=message["tool_calls"], messages=[message])
        state = runtime.tools(state)
        messages = runtime.messages(state, 7000)
        self.assertEqual(json.dumps(messages).count("source-only-sentinel"), 1)
        self.assertIn("S1", json.dumps(messages))

    def test_read_chunks_keeps_complete_text_that_fits_context_budget(self):
        text = "Source narrative. " * 120 + "A final, necessary qualification."
        runtime = self.runtime(mock.Mock(), mock.Mock(return_value={"outcome": "answered", "items": [{**source(), "text": text, "endOffset": 20 + len(text)}]}))
        state = initial()
        message = call("read_chunks", {"chunk_ids": ["chunk-1"]})
        state.update(pending=message["tool_calls"], messages=[message])
        state = runtime.tools(state)
        packed = json.loads(state["messages"][-1]["content"])
        self.assertEqual(packed["items"][0]["text"], text)

    def test_read_context_prioritizes_source_text_over_entity_id_inventory(self):
        text = "Source narrative and documented conditions. " * 45
        items = [{**source(), "chunkId": f"chunk-{index}", "text": text, "endOffset": 20 + len(text), "entities": [{"id": f"entity-{index}-{other}" + "abcdef0123456789" * 4, "name": f"Name {other}", "type": "Concept"} for other in range(40)]} for index in range(3)]
        runtime = self.runtime(mock.Mock(), mock.Mock(return_value={"tool": "read_chunks", "items": items}))
        state = initial()
        message = call("read_chunks", {"chunk_ids": [item["chunkId"] for item in items]})
        state.update(pending=message["tool_calls"], messages=[message])
        state = runtime.tools(state)
        packed = json.loads(state["messages"][-1]["content"])
        self.assertEqual([item["text"] for item in packed["items"]], [text] * 3)
        self.assertIn("find_entities", packed["entityLookup"])
        self.assertEqual(len(self.ledger.results["test-run", "call-1"]["items"][0]["entities"]), 40)

    def test_model_context_budget_reports_omitted_assertions(self):
        self.row["request"]["graph_expansion"] = True
        items = [{"id": f"assertion-{index}", "predicate": "reads", "polarity": "affirmed", "subject": {"id": "service"}, "object": {"id": "dataset"}, "quote": "A source-supported assertion. " * 100, "conditions": []} for index in range(50)]
        runtime = self.runtime(mock.Mock(), mock.Mock(return_value={"outcome": "answered", "items": items, "paths": [], "warnings": [], "truncations": []}))
        state = initial()
        message = call("inspect_assertions", {"entity_id": "dataset", "limit": 50})
        state.update(pending=message["tool_calls"], messages=[message])
        state = runtime.tools(state)
        content = state["messages"][-1]["content"]
        packed = json.loads(content)
        self.assertLessEqual(len(runtime.encoding.encode(content)), 3000)
        self.assertEqual(packed["contextCoverage"]["retrievedItems"], 50)
        self.assertEqual(packed["contextCoverage"]["shownItems"], len(packed["items"]))
        self.assertEqual(packed["contextCoverage"]["omittedItems"], 50 - len(packed["items"]))
        self.assertTrue(packed["truncations"])

    def test_source_reference_limit_is_explicit(self):
        payload = {"items": [{**source(), "chunkId": f"chunk-{index}"} for index in range(25)]}
        sources = collect_sources(payload, {})
        self.assertEqual(len(sources), 24)
        self.assertTrue(payload["items"][-1].get("citationUnavailable"))

    def test_repeated_passages_are_only_removed_when_original_is_visible(self):
        original = {"role": "tool", "tool_call_id": "first", "content": json.dumps({"items": [{"sourceReference": "S1", "text": "unique source passage"}]})}
        repeated = {**original, "tool_call_id": "second"}
        compacted = deduplicate_tool_passages([original, repeated])
        self.assertEqual(json.loads(compacted[0]["content"])["items"][0]["text"], "unique source passage")
        self.assertEqual(json.loads(compacted[1]["content"])["items"][0]["sameTextAs"], "S1")
        self.assertEqual(json.loads(deduplicate_tool_passages([repeated])[0]["content"])["items"][0]["text"], "unique source passage")
        self.assertIn("text", json.loads(original["content"])["items"][0])

    def test_clipped_context_turns_are_explicit_and_latest_result_is_required(self):
        runtime = self.runtime(mock.Mock())
        state = initial()
        first = call("search_sources", {"query": "first"}, "first")
        second = call("search_sources", {"query": "second"}, "second")
        state["messages"] = [first, {"role": "tool", "tool_call_id": "first", "content": "large old passage " * 4000}, second, {"role": "tool", "tool_call_id": "second", "content": json.dumps({"items": [{"sourceReference": "S1", "text": "latest support"}]})}]
        messages = runtime.messages(state, 2000)
        self.assertIn("omittedToolTurns", json.dumps(messages))
        self.assertIn("latest support", json.dumps(messages))
        self.assertNotIn("large old passage", json.dumps(messages))
        with self.assertRaisesRegex(RunBudgetReached, "latest tool result"):
            runtime.messages(state, 10)

    def test_citations_revalidate_publication_and_exact_offsets(self):
        sources = collect_sources({"items": [source()]}, {})
        self.ledger.row = {"payload": source()}
        with mock.patch("app.investigation.runtime.semantic_graph_name", return_value="test-graph"):
            self.assertEqual(validate_sources(sources, ["S1"], {})[0]["text"], "hello")
            sources["S1"]["text"] = "forged"
            with self.assertRaisesRegex(ValueError, "quotation"):
                validate_sources(sources, ["S1"], {})
            self.ledger.row = None
            with self.assertRaisesRegex(ValueError, "changed"):
                validate_sources(sources, ["S1"], {})

    def test_responses_protocol_preserves_function_call_ids(self):
        requests = []
        def transport(request):
            requests.append(request)
            return httpx.Response(200, json={"id": "resp-1", "object": "response", "created_at": 1, "model": "gpt-5", "status": "completed", "output": [{"id": "fc-1", "type": "function_call", "call_id": "stable-call", "name": "search_sources", "arguments": json.dumps({"query": "hello"}), "status": "completed"}], "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}})
        def client(**kwargs):
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(transport)))
        runtime = self.runtime(mock.Mock())
        with mock.patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "test-key"}), mock.patch("app.investigation.runtime.OpenAI", side_effect=client):
            message, usage = runtime.invoke_model([{"role": "user", "content": "hello"}], runtime.definitions(initial()))
        body = json.loads(requests[0].content)
        self.assertFalse(body["store"])
        self.assertFalse(body["parallel_tool_calls"])
        self.assertNotIn("temperature", body)
        self.assertEqual(body["tool_choice"], "auto")
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertNotIn('"title"', json.dumps(body["text"]["format"]["schema"]))
        self.assertNotIn('"title"', json.dumps(body["tools"]))
        self.assertNotIn("finish_report", [item["name"] for item in body["tools"]])
        self.assertEqual(requests[0].url.path, "/openai/v1/responses")
        self.assertFalse(requests[0].url.query)
        self.assertEqual(message["tool_calls"][0]["id"], "stable-call")
        self.assertEqual(message["response_items"][0]["call_id"], "stable-call")
        self.assertEqual(usage["total_tokens"], 30)

    def test_llm2_responses_request_omits_reasoning_options(self):
        self.row["configuration"]["chatModel"] = "gpt-4.1-mini"
        requests = []
        def transport(request):
            requests.append(request)
            return httpx.Response(200, json={"id": "resp-2", "object": "response", "created_at": 1, "model": "gpt-4.1-mini", "status": "completed", "output": [{"id": "fc-2", "type": "function_call", "call_id": "llm2-call", "name": "search_sources", "arguments": json.dumps({"query": "hello"}), "status": "completed"}], "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}})
        def client(**kwargs):
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(transport)))
        runtime = self.runtime(mock.Mock())
        with mock.patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "test-key"}), mock.patch("app.investigation.runtime.OpenAI", side_effect=client):
            runtime.invoke_model([{"role": "user", "content": "hello"}], runtime.definitions(initial()))
        body = json.loads(requests[0].content)
        self.assertEqual(body["model"], "gpt-4.1-mini")
        self.assertNotIn("reasoning", body)
        self.assertNotIn("include", body)
        self.assertEqual(body["temperature"], 0)
        self.assertFalse(body["store"])

    def test_chat_configuration_uses_llm1_for_investigation(self):
        class Rows:
            def execute(self, *args):
                return self
            def fetchone(self):
                return {"n": 0}
        @contextmanager
        def database():
            yield Rows()
        primary = {"model": "gpt-5", "baseUrl": "https://primary.example/openai/v1", "api": "responses", "credentialEnv": "LLM1_DEPLOYMENT_KEY"}
        with mock.patch("app.investigation.service.processing_config", return_value={"provider": "azure_openai", "extractionModel": "gpt-4.1-mini"}), mock.patch("app.investigation.service.deployment", side_effect=lambda role: primary if role == "LLM1" else None), mock.patch("app.investigation.service.semantic_graph_name", return_value="test-graph"), mock.patch("app.investigation.service.connection", database):
            config = service.configuration()
        self.assertEqual(config["chatModel"], "gpt-5")
        self.assertEqual(config["chatCredentialEnv"], "LLM1_DEPLOYMENT_KEY")
        self.assertEqual(config["chatApi"], "responses")
