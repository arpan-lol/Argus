import asyncio
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest import TestCase, mock

from pydantic import ValidationError

from app.investigation.runtime import collect_sources, validate_sources
from app.retrieval.contracts import ARTICLE_TOOLS, RankEntities, RecentSourceUpdates, SourceAuthors
from app.retrieval.mcp_server import call_tool, list_tools
from app.retrieval.research import pagerank, rank_entities, recent_source_updates, source_authors
from app.retrieval.routes import execute


class Session:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.manifest = {'job-1': {'job_id': 'job-1', 'source_id': 'doc-1', 'revision': 'revision-1', 'processing_version': 'version-1', 'published_at': now - timedelta(hours=1)}}
        self.warnings = []
        self.truncations = []
        self.sql = mock.Mock(return_value=[{'title': 'Synthetic fixture', 'metadata': {}, 'authors': ['Fixture Author']}])
        self.cypher = mock.Mock()
        self.chunks = mock.Mock(return_value={'chunk-1': {'id': 'chunk-1', 'job_id': 'job-1', 'document_id': 'doc-1', 'document_title': 'Synthetic fixture', 'payload': {'text': 'a b c', 'startOffset': 0, 'endOffset': 5}}})
        self.limits = {'fanout': 20, 'frontier': 40}

    def citation(self, row, start=None, end=None):
        return {'chunkId': 'chunk-1', 'jobId': 'job-1', 'documentId': 'doc-1', 'documentTitle': 'Synthetic fixture', 'sectionTitle': 'Test', 'startOffset': 0 if start is None else start, 'endOffset': 5 if end is None else end, 'revisionId': 'revision-1', 'processingVersion': 'version-1'}

    def excerpt(self, row):
        return {**self.citation(row), 'text': 'a b c'}

    def entity(self, identifier):
        return {'id': identifier, 'name': identifier, 'mention': 'a', 'citation': self.citation({})} if identifier in ('a', 'b', 'c') else None

    def truncate(self, reason):
        self.truncations.append(reason)


def edge(identifier, left, right):
    return {'id': identifier, 'subject': {'id': left}, 'object': {'id': right}}


class ResearchToolsTest(TestCase):
    def test_unknown_chunks_are_input_errors_instead_of_empty_searches(self):
        session = mock.Mock(jobs=['job-1'])
        session.finish.side_effect = lambda payload, outcome=None: {'outcome': outcome, **payload}
        payload = {'items': [], 'unknownChunkIds': ['CASE-A', 'CASE-B']}
        with mock.patch('app.retrieval.routes.Session', return_value=session), mock.patch('app.retrieval.tools.read_chunks', return_value=payload):
            result = execute('read_chunks', {'chunk_ids': ['CASE-A', 'CASE-B']})
        self.assertEqual(result['outcome'], 'unknown_chunk')
        self.assertTrue(result['inputError'])
        self.assertIn('search_sources', result['recovery'])

    def test_partial_chunk_lookup_preserves_valid_passages(self):
        session = mock.Mock(jobs=['job-1'])
        session.finish.side_effect = lambda payload, outcome=None: {'outcome': outcome, **payload}
        payload = {'items': [{'chunkId': 'chunk-1', 'text': 'valid source'}], 'unknownChunkIds': ['CASE-A']}
        with mock.patch('app.retrieval.routes.Session', return_value=session), mock.patch('app.retrieval.tools.read_chunks', return_value=payload):
            result = execute('read_chunks', {'chunk_ids': ['chunk-1', 'CASE-A']})
        self.assertEqual(result['outcome'], 'partial')
        self.assertTrue(result['inputError'])
        self.assertEqual(result['items'][0]['text'], 'valid source')

    def test_article_mapping_has_five_research_tools_with_recall_disabled(self):
        self.assertEqual(len(ARTICLE_TOOLS), 6)
        self.assertEqual(sum(item['available'] for item in ARTICLE_TOOLS), 5)
        with mock.patch('app.retrieval.routes.Session') as session:
            result = execute('recall', {})
        self.assertEqual(result['outcome'], 'capability_disabled')
        session.assert_not_called()

    def test_schema_bounds_reject_extra_args_and_excessive_limits(self):
        for schema, args in [(RankEntities, {'depth': 4}), (RankEntities, {'limit': 21}), (RecentSourceUpdates, {'hours': 169}), (SourceAuthors, {'document_id': 'doc', 'cypher': 'MATCH (n) RETURN n'})]:
            with self.subTest(args=args), self.assertRaises(ValidationError):
                schema.model_validate(args)

    def test_authors_are_source_metadata_without_contact_inference(self):
        session = Session()
        result = source_authors(session, SourceAuthors(document_id='doc-1'))
        self.assertEqual(result['items'][0]['author'], 'Fixture Author')
        citation = result['items'][0]['citation']
        self.assertEqual(citation['sourceKind'], 'metadata')
        self.assertNotIn('chunkId', citation)
        sources = collect_sources(result, {})
        self.assertEqual(sources['S1']['text'], 'Fixture Author')
        self.assertEqual(sources['S1']['metadataIndex'], 0)

    def test_unknown_document_stops_before_metadata_queries(self):
        session = Session()
        result = source_authors(session, SourceAuthors(document_id='unknown'))
        self.assertEqual(result['unknownDocumentIds'], ['unknown'])
        session.sql.assert_not_called()
        result = recent_source_updates(session, RecentSourceUpdates(document_id='unknown'))
        self.assertEqual(result['unknownDocumentIds'], ['unknown'])
        session.sql.assert_not_called()

    def test_missing_author_metadata_is_not_anonymous_authorship(self):
        session = Session()
        session.sql.return_value[0]['authors'] = []
        result = source_authors(session, SourceAuthors(document_id='doc-1'))
        self.assertEqual(result['items'], [])
        self.assertEqual(result['metadataStatus'], 'not_recorded')

    def test_indexing_events_are_separate_from_article_year(self):
        session = Session()
        session.sql.return_value = [{'document_id': 'doc-1', 'id': 'chunk-1', 'title': 'Synthetic fixture', 'year': '1933'}]
        result = recent_source_updates(session, RecentSourceUpdates(hours=2))
        item = result['items'][0]
        self.assertEqual(item['articleYear'], '1933')
        self.assertNotIn('1933', item['indexedAt'])
        sources = collect_sources(result, {})
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources['S2']['metadataField'], 'indexedAt')
        self.assertEqual(sources['S2']['text'], item['indexedAt'])
        session.manifest['job-1']['published_at'] -= timedelta(days=8)
        self.assertEqual(recent_source_updates(session, RecentSourceUpdates(hours=168))['items'], [])

    def test_pagerank_handles_dangling_nodes_and_deduplicates_edges(self):
        edges = [edge('one', 'a', 'b'), edge('two', 'b', 'c'), edge('three', 'c', 'b')]
        scores, stats = pagerank(edges)
        duplicate_scores, duplicate_stats = pagerank([*edges, edge('duplicate', 'a', 'b')])
        self.assertGreater(scores['b'], scores['a'])
        self.assertAlmostEqual(sum(scores.values()), 1)
        self.assertEqual(scores, duplicate_scores)
        self.assertEqual(stats['edges'], duplicate_stats['edges'])
        dangling, _ = pagerank([edge('one', 'a', 'b')])
        self.assertAlmostEqual(sum(dangling.values()), 1)
        self.assertGreater(dangling['b'], dangling['a'])
        self.assertEqual(pagerank([])[0], {})

    def test_ranking_projection_caps_nodes_honestly(self):
        scores, stats = pagerank([edge(str(i), 'root', str(i)) for i in range(10)], node_limit=4)
        self.assertEqual(len(scores), 4)
        self.assertTrue(stats['nodeLimitReached'])
        self.assertAlmostEqual(sum(scores.values()), 1)

    def test_rank_only_uses_source_validated_rows(self):
        session = Session()
        row = lambda key, left, right: [key, 'job-1', 'test_relation', 'affirmed', '[]', 'a b c', 0, 5, 'chunk-1', left, left, right, right]
        session.cypher.return_value = [row('one', 'a', 'b'), row('two', 'b', 'c'), row('three', 'c', 'b')]
        result = rank_entities(session, RankEntities(limit=3))
        self.assertEqual(result['items'][0]['id'], 'b')
        self.assertEqual(result['projection']['edges'], 3)
        self.assertTrue(all(item['supportingAssertions'] for item in result['items']))
        session.cypher.return_value[0][5] = 'forged'
        result = rank_entities(session, RankEntities(limit=3))
        self.assertEqual(result['projection']['assertionCount'], 2)
        self.assertTrue(session.warnings)

    def test_unknown_ranking_root_has_no_assertion_walk(self):
        session = Session()
        result = rank_entities(session, RankEntities(entity_id='unknown'))
        self.assertEqual(result['unknownEntityIds'], ['unknown'])
        session.cypher.assert_not_called()

    def test_metadata_citations_reject_forged_or_stale_values(self):
        session = Session()
        sources = collect_sources(source_authors(session, SourceAuthors(document_id='doc-1')), {})
        db = mock.Mock()
        db.execute.return_value.fetchone.return_value = {'authors': ['Fixture Author'], 'indexed_at': datetime.now(timezone.utc)}
        @contextmanager
        def connection():
            yield db
        with mock.patch('app.investigation.runtime.connection', connection), mock.patch('app.investigation.runtime.semantic_graph_name', return_value='fixture'):
            self.assertEqual(validate_sources(sources, ['S1'], {})[0]['text'], 'Fixture Author')
            sources['S1']['text'] = 'Invented Author'
            with self.assertRaisesRegex(ValueError, 'immutable'):
                validate_sources(sources, ['S1'], {})
            db.execute.return_value.fetchone.return_value = None
            with self.assertRaisesRegex(ValueError, 'publication changed'):
                validate_sources(sources, ['S1'], {})

    def test_metadata_citation_cannot_choose_arbitrary_fields(self):
        session = Session()
        sources = collect_sources(source_authors(session, SourceAuthors(document_id='doc-1')), {})
        sources['S1']['metadataField'] = 'secret'
        with mock.patch('app.investigation.runtime.connection') as connection:
            with self.assertRaisesRegex(ValueError, 'Unsupported metadata'):
                validate_sources(sources, ['S1'], {})

    def test_mcp_catalog_is_typed_and_excludes_memory_and_raw_queries(self):
        tools = asyncio.run(list_tools())
        names = {tool.name for tool in tools}
        self.assertEqual(len(names), 9)
        self.assertIn('rank_entities', names)
        self.assertNotIn('recall', names)
        self.assertTrue(all(tool.annotations.readOnlyHint for tool in tools))
        result = asyncio.run(call_tool('rank_entities', {'limit': 21}))
        self.assertTrue(result.isError)
