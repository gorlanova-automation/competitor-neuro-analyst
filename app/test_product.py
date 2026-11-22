import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from fastapi.testclient import TestClient
from app.main import create_app
from app.product import product_report


class ProductTests(unittest.TestCase):
    def test_colab_competitors_accept_domains_and_named_urls(self):
        from app.colab_product import parse_competitor_input
        rows=parse_competitor_input('avention.io, retensis.com, https://getreelyze.com')
        self.assertEqual([r['url'] for r in rows],['https://avention.io/','https://retensis.com/','https://getreelyze.com/'])
        self.assertEqual(parse_competitor_input('Example | https://example.com/')[0]['name'],'Example')
        mixed=parse_competitor_input('Opus Clip, Example | https://example.com/, Captions')
        self.assertEqual(mixed,[{'name':'Opus Clip','url':None},{'name':'Example','url':'https://example.com/'},{'name':'Captions','url':None}])
        for invalid in ('http://example.com/','localhost','https://127.0.0.1/'):
            with self.assertRaises(ValueError):parse_competitor_input(invalid)

    def test_colab_name_resolution_requires_choice_and_reuses_name(self):
        from app.colab_product import parse_competitor_input,resolve_competitor_names
        search=Mock(return_value={'status':'ok','candidates':[{'label':'Official Example','url':'https://example.com/'}]})
        answers=iter(['99','1'])
        with tempfile.TemporaryDirectory() as folder:
            rows=resolve_competitor_names(parse_competitor_input('Example, Example'),[],{},'test-key','https://own.example/',folder,
                prompt=lambda _:next(answers),notify=lambda _:None,search=search)
            self.assertEqual(rows,[{'name':'Example','url':'https://example.com/'}])
            self.assertEqual(search.call_count,1)
            record=json.loads(next((Path(folder)/'name_resolution').glob('*.json')).read_text(encoding='utf-8'))
            self.assertEqual(record['confirmed_url'],'https://example.com/')

    def test_colab_unresolved_name_can_be_skipped_or_supplied_manually(self):
        from app.colab_product import resolve_competitor_names
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(resolve_competitor_names([{'name':'Example','url':None}],[],{},None,'https://own.example/',folder,
                prompt=lambda _:'',notify=lambda _:None),[])
            result=resolve_competitor_names([{'name':'Example','url':None}],[],{},None,'https://own.example/',folder,
                prompt=lambda _:'example.com',notify=lambda _:None)
            self.assertEqual(result,[{'name':'Example','url':'https://example.com/'}])

    def test_colab_resumes_confirmed_profile_and_recovers_bad_input(self):
        import io
        import sys
        from types import ModuleType,SimpleNamespace
        from app.colab_product import launch
        from stage_4.workflow import run_project
        text='Public short video analysis service and editing recommendations. '*10
        with tempfile.TemporaryDirectory() as folder:
            state=run_project(output_dir=Path(folder)/'projects',website_url='https://own.example/',uploads={'https://own.example/':{'text':text}})
            state=run_project(output_dir=Path(folder)/'projects',project_id=state['id'],action='confirm_profile',
                              profile={'company_name':'Own','summary':'Video analysis','market_scope':'Creators','search_terms':'video analysis tools'})
            google=ModuleType('google');colab=ModuleType('google.colab')
            colab.files=SimpleNamespace(download=Mock())
            google.colab=colab
            answers=['https://own.example/','нет','да','нет','https://127.0.0.1/','rival.example, second.example','','да','']
            source={'url':'https://own.example/','status':'ok','text':text,'text_blocks':[text],
                    'title':'Test','links':[],'collected_at':'date','sha256_text':'test','method':'test'}
            # Reuse the stored source hash for the confirmed own snapshot.
            from stage_4.workflow import digest
            source['sha256_text']=digest(text)
            output=io.StringIO()
            with patch.dict(sys.modules,{'google':google,'google.colab':colab}),patch('builtins.input',side_effect=answers),patch('stage_4.workflow.fetch',return_value=source),patch('sys.stdout',output):
                result=launch(folder)
            self.assertEqual(result['id'],state['id'])
            self.assertEqual(len(result['competitors']),2)
            self.assertIn('Повторите ввод',output.getvalue())
            self.assertEqual(colab.files.download.call_count,1)

    def test_colab_export_creates_its_own_directory(self):
        from app.colab_product import export_result
        with tempfile.TemporaryDirectory() as folder:
            identifier='00000000-0000-0000-0000-000000000001'
            value={'profile':{'company_name':'Проверка'},'companies':[]}
            path=export_result(folder,identifier,value)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),value)
            self.assertEqual(path.parent.parent,Path(folder)/'exports')
            self.assertFalse((Path(folder)/'projects').exists())

    def test_official_candidate_edit_and_manual_browser_continuation(self):
        from app.test_search import Response
        with tempfile.TemporaryDirectory() as folder:
            settings={'ANALYST_SEARCH_PROVIDER':'tavily','ANALYST_SEARCH_ENABLED':'1','TAVILY_API_KEY':'test-search-token',
                      'ANALYST_SEARCH_BUDGET_FILE':str(Path(folder)/'budget.json')}
            transport=Mock();transport.request.return_value=Response({'results':[{'title':'API candidate','url':'https://rival.example/'}]})
            with patch.dict('os.environ',settings),patch('app.search.requests.Session',return_value=transport),TestClient(create_app(folder)) as client:
                def run(body,identifier=None):
                    response=client.post('/api/research'+('/'+identifier if identifier else ''),json=body)
                    self.assertEqual(response.status_code,202,response.text)
                    for _ in range(400):
                        job=client.get('/api/jobs/'+response.json()['id']).json()
                        if job['status'] not in ('running','queued'):break
                        time.sleep(.01)
                    self.assertEqual(job['status'],'succeeded',job)
                    return client.get('/api/research/'+job['project_id']).json()
                state=run({'action':'start','website_url':'https://own.example/','uploads':{'https://own.example/':{'text':'Public consulting service for international customers. '*10}}})
                state=run({'action':'confirm_profile','profile':{'company_name':'Own','summary':'Consulting','market_scope':'EU','search_terms':'consulting'}},state['id'])
                self.assertEqual(state['search']['status'],'ok');self.assertEqual(state['suggestions'][0]['name'],'API candidate')
                state=run({'action':'confirm_competitors','competitors':[{'name':'Edited name','url':'https://rival.example/'}]},state['id'])
                self.assertEqual(state['competitors'][0]['name'],'Edited name');self.assertEqual(state['competitors'][0]['added_by'],'script_search_confirmed')
                state=run({'action':'import_search','search_text':'Browser result https://manual.example/'},state['id'])
                state=run({'action':'confirm_competitors','competitors':[{'name':'Edited browser name','url':'https://manual.example/'}]},state['id'])
                self.assertEqual(state['competitors'][0]['added_by'],'user_added');self.assertEqual(transport.request.call_count,1)

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
            self.assertEqual(value['recommendations'],[]);self.assertEqual(value['new_llm_calls'],0)
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
        self.assertEqual(value['recommendations'],[])  # No advice before semantic analysis.
        self.assertFalse(any(r['kind']=='keep' and r['evidence'][0]['quote']==quote for r in value['recommendations']))

    def test_restart_finishes_interrupted_job_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as folder:
            jobs=Path(folder)/'jobs';jobs.mkdir();identifier='00000000-0000-0000-0000-000000000001'
            (jobs/(identifier+'.json')).write_text(json.dumps({'id':identifier,'status':'running'}),encoding='utf-8')
            with TestClient(create_app(folder)) as client:
                value=client.get('/api/jobs/'+identifier).json()
                self.assertEqual(value['status'],'failed');self.assertIn('перезапущен',value['error'])


if __name__=='__main__':unittest.main()
