import tempfile
import unittest
from fastapi.testclient import TestClient
from .main import create_app


class WorkflowApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.client=TestClient(create_app(self.temp.name))

    def test_start_confirm_collect_download_restart(self):
        uploads={url:{'text':'Product service consultation price 100 EUR. '*20} for url in ['https://own.example/','https://rival.example/']}
        response=self.client.post('/projects',json={'website_url':'https://own.example/','uploads':uploads})
        self.assertEqual(response.status_code,201);identifier=response.json()['id']
        self.assertEqual(self.client.post('/projects/'+identifier,json={'action':'collect'}).status_code,422)
        profile={'company_name':'Own','summary':'Software services','market_scope':'EU businesses','search_terms':'software'}
        self.assertEqual(self.client.post('/projects/'+identifier,json={'action':'confirm_profile','profile':profile}).status_code,200)
        self.assertEqual(self.client.post('/projects/'+identifier,json={'action':'confirm_competitors','competitor_urls':['https://rival.example/']}).status_code,200)
        state=self.client.post('/projects/'+identifier,json={'action':'collect','uploads':uploads,'max_pages':1}).json()
        self.assertEqual(state['status'],'report_ready')
        for format in ['html','json']:
            report=self.client.get('/projects/'+identifier+'/reports/'+state['report']['run_id']+'?format='+format)
            self.assertEqual(report.status_code,200)
        fresh=TestClient(create_app(self.temp.name))
        self.assertEqual(fresh.get('/projects/'+identifier).json()['report']['run_id'],state['report']['run_id'])

    def test_invalid_payload_origin_and_missing_history(self):
        self.assertEqual(self.client.post('/projects',json={'website_url':'https://127.0.0.1/'}).status_code,422)
        self.assertEqual(self.client.post('/projects',json={'website_url':'https://example.org/','secret':'no'}).status_code,422)
        self.assertEqual(self.client.post('/projects',json={},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/projects/00000000-0000-0000-0000-000000000000').status_code,404)
        self.assertEqual(self.client.get('/projects').json(),[])


if __name__=='__main__':unittest.main()
