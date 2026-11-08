"""Exercise hosted API behavior without connecting to Neo4j or changing project data."""
import importlib.util
import json
import os
from pathlib import Path
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

os.environ.setdefault('NEO4J_PASSWORD', 'unused-test-password')
spec = importlib.util.spec_from_file_location('ethnotrace_deployment_server', Path(__file__).resolve().parents[1] / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class DeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_origins = server.CORS_ALLOWED_ORIGINS
        cls.old_context, cls.old_query = server.context, server.query
        server.CORS_ALLOWED_ORIGINS = frozenset({'https://frontend.example'})
        server.context = lambda: {'snapshot': 'test-snapshot'}
        server.query = lambda *args, **kwargs: [{'connected': 1}]
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        server.CORS_ALLOWED_ORIGINS = cls.old_origins
        server.context, server.query = cls.old_context, cls.old_query
        server.driver.close()

    def request(self, method, path, origin, body=None):
        connection = HTTPConnection('127.0.0.1', self.http.server_port, timeout=5)
        headers = {'Origin': origin}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        result = response.status, dict(response.getheaders()), data
        connection.close()
        return result

    def test_allowed_and_denied_origins(self):
        status, headers, _ = self.request('OPTIONS', '/api/reviews', 'https://frontend.example')
        self.assertEqual(status, 204)
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'https://frontend.example')
        status, headers, _ = self.request('OPTIONS', '/api/reviews', 'https://other.example')
        self.assertEqual(status, 403)
        self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_health_and_review_submissions_are_disabled(self):
        status, headers, body = self.request('GET', '/api/health', 'https://frontend.example')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'https://frontend.example')
        self.assertEqual(json.loads(body)['snapshot'], 'test-snapshot')
        payload = {'entry_id': 'a' * 64, 'target_type': 'entry', 'target_id': 'a' * 64,
                   'verdict': 'note', 'comment': 'Test only', 'reviewer': 'Test reviewer'}
        status, _, _ = self.request('POST', '/api/reviews', 'https://frontend.example', json.dumps(payload))
        self.assertEqual(status, 405)

    def test_demo_reviews_are_generated_without_submissions(self):
        old_entries, old_entry, old_studies, old_store = server.entries, server.entry, server.entry_studies, server._demo_store
        try:
            server._demo_store = None
            server.entries = lambda *args: {'items': [{'id': 'a' * 64, 'name': 'Example', 'book': 'culpeper'}]}
            server.entry = lambda *args: {'candidates': [{'decision': {'tier': 'A'}, 'hypothesis': {'id': 'h', 'accepted_name': 'Example plant'}}], 'claims': []}
            server.entry_studies = lambda *args: {'items': []}
            status, _, body = self.request('GET', '/api/reviews', 'https://frontend.example')
            self.assertEqual(status, 200)
            result = json.loads(body)
            self.assertTrue(result['reviews'])
            self.assertTrue(all(row['demo'] for row in result['reviews']))
        finally:
            server.entries, server.entry, server.entry_studies, server._demo_store = old_entries, old_entry, old_studies, old_store

    def test_health_reports_database_failure(self):
        old_query = server.query
        try:
            def unavailable(*args, **kwargs):
                raise RuntimeError('simulated database outage')
            server.query = unavailable
            status, _, _ = self.request('GET', '/api/health', 'https://frontend.example')
            self.assertEqual(status, 503)
        finally:
            server.query = old_query


if __name__ == '__main__':
    unittest.main()
