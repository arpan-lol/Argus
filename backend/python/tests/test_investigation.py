import copy
import json
import os
from contextlib import contextmanager
from unittest import TestCase, mock

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from openai import OpenAI

from app.investigation.runtime import Investigation, RunBudgetReached, collect_sources, validate_sources


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


def report(purpose="conversation", citations=None):
    return {"purpose": purpose, "paragraphs": [{"text": "A bounded answer", "citations": citations or []}], "comparison": [], "gaps": []}


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
        self.assertIsNone(model.call_args.args[1])
        self.assertEqual(self.ledger.budget["reportedTokens"], 42)

    def test_empty_project_answers_in_one_small_structured_call(self):
        self.row["configuration"]["coverage"] = {"publishedDocuments": 0, "legacyDocuments": 6013}
        self.row["configuration"]["workspaceDescription"] = "Materials research"
        model = mock.Mock(return_value=({"role": "assistant", "content": json.dumps(report())}, {"total_tokens": 120}))
        tool = mock.Mock()
        state = self.runtime(model, tool).graph(InMemorySaver()).invoke(initial(), {"configurable": {"thread_id": "empty-project"}})
        self.assertEqual(state["report"]["purpose"], "conversation")
        self.assertEqual(model.call_count, 1)
        messages, definitions = model.call_args.args
        self.assertIsNone(definitions)
        self.assertIn("Materials research", messages[0]["content"])
        self.assertNotIn("rank_entities", json.dumps(messages))
        tool.assert_not_called()

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
        self.assertIn("finish_report", names)

    def test_source_references_deduplicate(self):
        sources = collect_sources({"items": [source(), source()]}, {})
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources["S1"]["key"], ["job-1", "chunk-1", 20, 25])

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
            return httpx.Response(200, json={"id": "resp-1", "object": "response", "created_at": 1, "model": "gpt-5", "status": "completed", "output": [{"id": "fc-1", "type": "function_call", "call_id": "stable-call", "name": "finish_report", "arguments": json.dumps(report()), "status": "completed"}], "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}})
        def client(**kwargs):
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(transport)))
        runtime = self.runtime(mock.Mock())
        with mock.patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "test-key"}), mock.patch("app.investigation.runtime.OpenAI", side_effect=client):
            message, usage = runtime.invoke_model([{"role": "user", "content": "hello"}], runtime.definitions(initial()))
        body = json.loads(requests[0].content)
        self.assertFalse(body["store"])
        self.assertFalse(body["parallel_tool_calls"])
        self.assertEqual(requests[0].url.path, "/openai/v1/responses")
        self.assertFalse(requests[0].url.query)
        self.assertEqual(message["tool_calls"][0]["id"], "stable-call")
        self.assertEqual(message["response_items"][0]["call_id"], "stable-call")
        self.assertEqual(usage["total_tokens"], 30)
