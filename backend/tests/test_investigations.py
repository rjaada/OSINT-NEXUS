import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import investigations as engine
import routes_investigations as routes


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.evidence = [{'id': 'E1'}, {'id': 'E2'}]

    def test_citations_must_all_reference_retrieved_evidence(self):
        result = engine.validate_analysis(json.dumps({'findings': [
            {'text': 'invented', 'kind': 'reported', 'evidence_ids': ['E1', 'E999']},
            {'text': 'uncited', 'kind': 'reported', 'evidence_ids': []},
            {'text': 'supported', 'kind': 'inference', 'evidence_ids': ['E1']},
        ]}), self.evidence)
        self.assertEqual([f['text'] for f in result['findings']], ['supported'])

    def test_contradiction_needs_two_distinct_records(self):
        result = engine.validate_analysis(json.dumps({'contradictions': [
            {'text': 'invalid', 'evidence_ids': ['E1', 'E1']},
            {'text': 'conflict', 'evidence_ids': ['E1', 'E2']},
        ]}), self.evidence)
        self.assertEqual(len(result['contradictions']), 1)

    def test_malformed_model_output_retains_explicit_unknowns(self):
        for raw in ('not json', '[]', '{"findings":null}', None):
            result = engine.validate_analysis(raw, self.evidence)
            self.assertFalse(result['findings'])
            self.assertTrue(result['unknowns'])

    def test_retrieval_deduplicates_and_filters_unsafe_links(self):
        events = [{'id': 'one', 'description': 'Beirut report', 'url': 'javascript:alert(1)'},
                  {'id': 'one', 'description': 'Beirut report'}, {'id': 'two', 'description': 'Unrelated'}]
        result = engine.select_evidence(events, ['beirut'])
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]['url'])

    def test_unicode_terms_and_stopwords(self):
        self.assertEqual(engine.query_terms('What changed in بيروت?'), ['بيروت'])

    def test_empty_evidence_does_not_call_model(self):
        with patch('groq_client.chat') as chat:
            self.assertEqual(engine.analyze('What changed?', [])['status'], 'no_evidence')
            chat.assert_not_called()

    def test_local_json_uses_native_format_without_assistant_prefill(self):
        import groq_client
        from unittest.mock import Mock
        response = Mock()
        response.json.return_value = {'message': {'content': '{"findings": []}'}}
        messages = [{'role': 'user', 'content': 'Return JSON'}]
        with patch.object(groq_client, 'OLLAMA_MODEL', 'qwen3:8b'), patch.object(groq_client.httpx, 'post', return_value=response) as post:
            result = groq_client._ollama_chat(messages, json_mode=True, ollama_context=16384)
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['format'], 'json')
        self.assertFalse(payload['think'])
        self.assertEqual(payload['messages'], messages)
        self.assertEqual(payload['options']['num_ctx'], 16384)
        self.assertEqual(json.loads(result), {'findings': []})

    def test_busy_limit_is_released_after_error(self):
        with patch.object(routes, 'connection', side_effect=RuntimeError('db unavailable')):
            for _ in range(3):
                with self.assertRaises(RuntimeError):
                    routes.run_investigation(routes.InvestigationInput(question='What changed in Beirut?'), 'analyst')


class InvestigationRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(routes.router)
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_access_dependency_applies_to_all_routes(self):
        def deny():
            raise HTTPException(403, 'forbidden')
        self.app.dependency_overrides[routes._require_analyst_or_admin] = deny
        self.assertEqual(self.client.get('/api/v2/investigations').status_code, 403)
        self.assertEqual(self.client.get('/api/v2/investigations/' + str(uuid4())).status_code, 403)
        self.assertEqual(self.client.post('/api/v2/investigations', json={'question': 'What changed in Beirut?'}).status_code, 403)

    def test_detail_uses_authenticated_owner(self):
        self.app.dependency_overrides[routes._require_analyst_or_admin] = lambda: {'username': 'alice'}
        identifier = uuid4()
        with patch.object(routes, 'read_saved', return_value={'id': str(identifier)}) as read:
            response = self.client.get('/api/v2/investigations/' + str(identifier))
        self.assertEqual(response.status_code, 200)
        read.assert_called_once_with('alice', identifier)

    def test_create_requires_csrf(self):
        from types import SimpleNamespace
        self.app.dependency_overrides[routes._require_analyst_or_admin] = lambda: {'username': 'alice'}
        def deny(request):
            raise HTTPException(403, 'CSRF')
        with patch.dict('sys.modules', {'main': SimpleNamespace(enforce_csrf=deny)}), patch.object(routes, 'run_investigation') as run:
            response = self.client.post('/api/v2/investigations', json={'question': 'What changed in Beirut?'})
        self.assertEqual(response.status_code, 403)
        run.assert_not_called()
