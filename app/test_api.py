import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from .main import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.client = TestClient(create_app(self.path))

    def test_portugal_report_and_provenance(self):
        response = self.client.post('/runs', json={})
        self.assertEqual(response.status_code, 201)
        row = response.json()
        self.assertEqual([row['summary'][k] for k in ('criteria', 'evidence', 'hypotheses')], [9, 30, 3])
        self.assertEqual(row['summary']['new_llm_calls'], 0)
        report = self.client.get(f"/runs/{row['id']}/report?format=json").json()
        self.assertEqual(len(report['evidence']), 30)
        self.assertTrue(all(f['url'] and f['evidence'] for f in report['evidence']))

    def test_restart_and_unique_outputs(self):
        first = self.client.post('/runs', json={}).json()
        second = self.client.post('/runs', json={'country': 'Spain'}).json()
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(second['summary']['evidence'], 0)
        fresh = TestClient(create_app(self.path))
        self.assertEqual(len(fresh.get('/runs').json()), 2)
        for row in (first, second):
            self.assertTrue((self.path / 'runs' / row['id'] / 'run.json').is_file())

    def test_invalid_requests_create_no_runs(self):
        for body in ({'country': 'France'}, {'competitors': ['unknown']},
                     {'competitors': ['migrun', 'migrun']}, {'live_llm_enabled': True}):
            self.assertEqual(self.client.post('/runs', json=body).status_code, 422)
        self.assertEqual(self.client.get('/runs').json(), [])

    def test_empty_competitors(self):
        row = self.client.post('/runs', json={'competitors': []}).json()
        report = self.client.get(f"/runs/{row['id']}/report?format=json").json()
        self.assertEqual(len(report['coverage']), 1)
        self.assertEqual(len(report['recommendations']), 1)

    def test_failure_is_recorded_without_raw_exception(self):
        with patch('app.main.analyst.run', side_effect=RuntimeError('secret-example')):
            response = self.client.post('/runs', json={})
        self.assertEqual(response.status_code, 500)
        history = self.client.get('/runs').json()
        self.assertEqual(history[0]['status'], 'failed')
        self.assertNotIn('secret-example', str(history) + response.text)
        self.assertEqual(self.client.get(f"/runs/{history[0]['id']}/report").status_code, 409)

    def test_origin_and_paths(self):
        self.assertEqual(self.client.post('/runs', json={}, headers={'Origin': 'https://example.com'}).status_code, 403)
        self.assertEqual(self.client.get('/runs/not-a-uuid/report').status_code, 422)
        self.assertEqual(self.client.get('/runs?limit=1000').status_code, 422)
        row = self.client.post('/runs', json={}).json()
        self.assertEqual(self.client.get(f"/runs/{row['id']}/report?format=../../config").status_code, 422)


if __name__ == '__main__':
    unittest.main()
