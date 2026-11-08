import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.product import product_report


class ProductTests(unittest.TestCase):
    def test_shared_workspace_requires_auth_and_exact_host(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'ANALYST_PASSWORD':'test-only-password','ANALYST_ALLOWED_HOSTS':'analyst.example'}):
            with TestClient(create_app(folder)) as client:
                self.assertEqual(client.get('/api/research').status_code,401)
                self.assertEqual(client.get('/api/research',auth=('analyst','wrong')).status_code,401)
                self.assertEqual(client.get('/api/research',auth=('analyst','test-only-password')).status_code,200)
                self.assertEqual(client.get('/api/research',auth=('analyst','test-only-password'),headers={'Host':'unapproved.example'}).status_code,400)

    def test_job_workflow_keeps_names_provenance_and_report(self):
        with tempfile.TemporaryDirectory() as folder,TestClient(create_app(folder)) as client:
            def run(body,identifier=None):
                response=client.post('/api/research'+('/'+identifier if identifier else ''),json=body)
                self.assertEqual(response.status_code,202,response.text)
                for _ in range(600):
                    job=client.get('/api/jobs/'+response.json()['id']).json()
                    if job['status'] not in ('running','queued'):break
                    time.sleep(.05)
                self.assertEqual(job['status'],'succeeded',job)
                return client.get('/api/research/'+job['project_id']).json()
            text='Наш продукт помогает клиенту. Консультация бесплатная. Стоимость пакета 100 EUR. Есть статьи и услуги. '*8
            uploads={u:{'text':text} for u in ['https://own.example/','https://rival.example/']}
            state=run({'action':'start','website_url':'https://own.example/','uploads':uploads})
            profile={'company_name':'Своя','summary':'Консультации','market_scope':'Европа','search_terms':'консультации'}
            with patch('stage_4.workflow.discover',return_value={'status':'challenge','candidates':[]}):
                state=run({'action':'confirm_profile','profile':profile},state['id'])
            self.assertEqual(state['search']['status'],'challenge');self.assertEqual(state['suggestions'],[])
            state=run({'action':'confirm_competitors','competitors':[{'name':'Исправленное имя','url':'https://rival.example/'}]},state['id'])
            state=run({'action':'collect','uploads':uploads,'max_pages':1},state['id'])
            value=client.get('/api/research/'+state['id']+'/result').json()
            self.assertEqual(value['companies'][1]['name'],'Исправленное имя')
            self.assertEqual(value['companies'][1]['added_by'],'user_added')
            self.assertTrue(value['recommendations']);self.assertEqual(value['new_llm_calls'],0)
            self.assertTrue(all(e['quote'] in text for r in value['recommendations'] for e in r['evidence']))
            self.assertEqual(client.get('/api/jobs/not-a-uuid').status_code,422)

    def test_missing_content_does_not_become_a_competitor_weakness(self):
        company={'url':'https://own.example/','name':'Own','role':'own','dimensions':{},'evidence':[],'pages_ok':0,'gaps':[]}
        rival={**company,'role':'competitor','url':'https://rival.example/'}
        result=product_report({'companies':[company,rival],'run_id':'run','generated_at':'time','profile':{},'limits':[]},
                              {'profile':{'company_name':'Own'},'competitors':[{'url':rival['url'],'name':'Rival'}]})
        self.assertFalse(any(r['kind'] in ('keep','adapt') for r in result['recommendations']))
        self.assertTrue(all(r['status']=='Гипотеза для проверки' for r in result['recommendations']))
        self.assertTrue(all(not r['evidence'] for r in result['recommendations']))

    def test_unverified_absolute_promise_is_checked_instead_of_reinforced(self):
        quote='Сопровождение без риска отказа и с обещанием полного результата.'
        evidence={'category':'positioning','quote':quote,'url':'https://own.example/','source_sha256':'hash'}
        company={'url':'https://own.example/','name':'Own','role':'own','dimensions':{'positioning':1},'evidence':[evidence],'pages_ok':1}
        value=product_report({'companies':[company],'run_id':'run','generated_at':'time','profile':{},'limits':[]},
                             {'profile':{'company_name':'Own'},'competitors':[]})
        self.assertTrue(any(r['kind']=='check' and r['evidence'] for r in value['recommendations']))
        self.assertFalse(any(r['kind']=='keep' and r['evidence'][0]['quote']==quote for r in value['recommendations']))

    def test_restart_finishes_interrupted_job_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as folder:
            jobs=Path(folder)/'jobs';jobs.mkdir();identifier='00000000-0000-0000-0000-000000000001'
            (jobs/(identifier+'.json')).write_text(json.dumps({'id':identifier,'status':'running'}),encoding='utf-8')
            with TestClient(create_app(folder)) as client:
                value=client.get('/api/jobs/'+identifier).json()
                self.assertEqual(value['status'],'failed');self.assertIn('перезапущен',value['error'])


if __name__=='__main__':unittest.main()
