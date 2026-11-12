import hashlib
import json
import tempfile
import unittest
import io
import sys
from types import ModuleType,SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from stage_4.workflow import run_project,WorkflowError,public_url,PublicSession


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.own='https://own.example/';self.rival='https://rival.example/'
        self.text='Услуги компании: консультация, сопровождение и документы. Цена пакета 100 EUR. Помогаем клиентам. '*8
        self.uploads={self.own:{'text':self.text,'title':'Own company'},self.rival:{'text':self.text+' Rival','title':'Rival'}}

    def run_action(self,**kwargs):return run_project(output_dir=self.root,**kwargs)

    def confirmed(self):
        state=self.run_action(website_url=self.own,uploads=self.uploads)
        identifier=state['id']
        self.run_action(project_id=identifier,action='confirm_profile',profile={'company_name':'Own',
            'summary':'Описание собственной компании','market_scope':'Португалия, русскоязычные клиенты','search_terms':'relocation services'})
        self.run_action(project_id=identifier,action='confirm_competitors',competitor_urls=[self.rival])
        return identifier

    def test_end_to_end_uploaded_sources_are_labelled_and_report_escaped(self):
        identifier=self.confirmed()
        state=self.run_action(project_id=identifier,action='collect',uploads=self.uploads,max_pages=1)
        self.assertEqual(state['status'],'report_ready');self.assertEqual(state['report']['companies'],2)
        folder=self.root/identifier/'runs'/state['report']['run_id']
        sources=json.loads((folder/'sources.json').read_text(encoding='utf-8'))
        self.assertEqual(sources[1]['sources'][0]['method'],'user_uploaded_text')
        result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
        self.assertTrue(result['companies'][1]['evidence'])
        for company in result['companies']:
            for fact in company['evidence']:
                source=next(s for c in sources for s in c['sources'] if s.get('sha256_text')==fact['source_sha256'])
                self.assertIn(fact['quote'],source['text'])
        self.uploads[self.rival]['text']+='<script>alert(1)</script>'
        second=self.run_action(project_id=identifier,action='collect',uploads=self.uploads,max_pages=1)
        self.assertNotEqual(state['report']['run_id'],second['report']['run_id'])
        self.assertTrue((folder/'report.html').is_file())

    def test_checkpoints_cannot_be_skipped_and_profile_change_invalidates_selection(self):
        state=self.run_action(website_url=self.own,uploads=self.uploads)
        with self.assertRaises(WorkflowError):self.run_action(project_id=state['id'],action='collect')
        identifier=self.confirmed()
        self.run_action(project_id=identifier,action='confirm_profile',profile={'company_name':'Own',
            'summary':'Changed','market_scope':'Spain','search_terms':'business'})
        with self.assertRaises(WorkflowError):self.run_action(project_id=identifier,action='collect')

    def test_missing_competitor_is_partial_not_absent_service(self):
        identifier=self.confirmed()
        with patch('stage_4.workflow.fetch',return_value={'url':self.rival,'status':'robots_disallowed','next_action':'manual_source_review_no_automated_fetch'}):
            state=self.run_action(project_id=identifier,action='collect',uploads={self.own:self.uploads[self.own]},max_pages=1)
        self.assertEqual(state['status'],'report_partial')
        self.assertEqual(state['report']['companies_without_content'],1)

    def test_uploaded_service_page_is_used_when_homepage_is_unavailable(self):
        from stage_4.workflow import collect_site,new_session
        url=self.rival+'services'
        with patch('stage_4.workflow.fetch',return_value={'url':self.rival,'status':'robots_disallowed'}):
            with new_session() as session:sources=collect_site(self.rival,session,{url:{'text':self.text}},1)
        self.assertEqual([source['status'] for source in sources],['robots_disallowed','ok'])
        self.assertEqual(sources[1]['method'],'user_uploaded_text')

    def test_private_urls_ids_and_same_company_rejected(self):
        for url in ['http://example.com','https://127.0.0.1/','https://192.168.0.1/','https://[::1]/','https://localhost/','https://x.local/','https://user:pass@example.com/','https://example.com:8443/']:
            with self.assertRaises(ValueError):public_url(url)
        with self.assertRaises(WorkflowError):self.run_action(action='read',project_id='../outside')
        identifier=self.confirmed()
        with self.assertRaises(WorkflowError):self.run_action(project_id=identifier,action='confirm_competitors',competitor_urls=[self.own])

    def test_changed_source_blocks_analysis(self):
        identifier=self.confirmed();path=self.root/identifier/'own_source.json'
        source=json.loads(path.read_text(encoding='utf-8'));source['text']='Changed';path.write_text(json.dumps(source))
        with self.assertRaises(WorkflowError):self.run_action(project_id=identifier,action='collect',uploads=self.uploads)

    def test_model_failure_keeps_previous_report_and_records_attempt(self):
        identifier=self.confirmed()
        before=self.run_action(project_id=identifier,action='collect',uploads=self.uploads,max_pages=1)
        with patch('stage_4.semantic.analyze',side_effect=WorkflowError('Rejected response')):
            with self.assertRaises(WorkflowError):self.run_action(project_id=identifier,action='analyze',api_key='test-only-key')
        after=self.run_action(project_id=identifier,action='read')
        self.assertEqual(after['report'],before['report'])
        self.assertEqual(after['last_model_attempt']['status'],'quarantined')
        self.assertNotIn('test-only-key',json.dumps(after))

    def test_search_failure_preserves_manual_path(self):
        identifier=self.confirmed()
        with patch.dict('os.environ',{'ANALYST_SEARCH_PROVIDER':'duckduckgo'}),patch('stage_4.workflow.fetch',return_value={'url':'https://html.duckduckgo.com/','status':'challenge_page'}):
            state=self.run_action(project_id=identifier,action='search')
        self.assertEqual(state['search']['candidates'],[])
        self.assertTrue(state['competitors_confirmed'])

    def test_search_queries_deduplicate_terms_and_empty_results_are_explicit(self):
        from stage_4.workflow import queries,discover
        text=queries({'company_name':'Test','search_terms':'relocation Portugal Spain','market_scope':'Portugal Spain'})[0]
        self.assertEqual(text.count('Portugal'),1)
        with patch.dict('os.environ',{'ANALYST_SEARCH_PROVIDER':'duckduckgo'}),patch('stage_4.workflow.fetch',return_value={'url':'https://html.duckduckgo.com/','status':'ok','text':'No results','links':[]}):
            search=discover({'company_name':'Test'})
        self.assertEqual(search['status'],'no_candidates')
        self.assertEqual(search['source']['text'],'No results')

    def test_all_eleven_agreed_competitors_fit_in_one_project(self):
        identifier=self.confirmed()
        urls=['https://rival'+str(i)+'.example/' for i in range(11)]
        state=self.run_action(project_id=identifier,action='confirm_competitors',competitor_urls=urls)
        self.assertEqual(len(state['competitors']),11)

    def test_publications_are_messages_not_social_links(self):
        from stage_4.workflow import sample_publications
        from unittest.mock import Mock
        page={'url':self.own,'status':'ok','links':[{'url':'https://t.me/public_channel','label':'Telegram'},{'url':'https://t.me/contact_bot','label':'Bot'}]}
        markup=b'<div class="tgme_widget_message" data-post="public_channel/123"><div class="tgme_widget_message_text">Public message about services.</div><time datetime="2026-11-07"></time></div>'
        with patch('stage_4.workflow.fetch',return_value={'status':'ok','html':markup}) as fetch:
            posts,feeds=sample_publications([page],Mock())
        self.assertEqual(fetch.call_count,1);self.assertEqual(len(posts),1)
        self.assertEqual(posts[0]['url'],'https://t.me/public_channel/123')
        self.assertEqual(posts[0]['sha256_text'],hashlib.sha256(posts[0]['text'].encode()).hexdigest())
        self.assertEqual(feeds[0]['posts'],1)

    def test_colab_secret_failure_still_returns_the_saved_report(self):
        from stage_4.colab_app import launch_colab
        from unittest.mock import Mock
        colab=ModuleType('google.colab')
        colab.files=SimpleNamespace(upload=lambda:{'page.txt':self.text.encode()})
        colab.userdata=SimpleNamespace(get=Mock(side_effect=TimeoutError('sensitive-error-text')))
        google=ModuleType('google');google.colab=colab
        ipython=ModuleType('IPython');display=ModuleType('IPython.display')
        display.display=Mock();display.HTML=lambda value:value;ipython.display=display
        answers=[self.own,'да','Own','Services','EU','services','да','нет',self.rival,'да','да','нет']
        captured=io.StringIO()
        source={'url':self.rival,'final_url':self.rival,'status':'ok','text':self.text,
                'sha256_text':hashlib.sha256(self.text.encode()).hexdigest(),'title':'Rival','links':[],
                'method':'injected_test','collected_at':'2026-11-07'}
        with patch.dict(sys.modules,{'google':google,'google.colab':colab,'IPython':ipython,'IPython.display':display}),patch('builtins.input',side_effect=answers),patch('stage_4.workflow.fetch',return_value=source),patch('sys.stdout',captured):
            state=launch_colab(output_dir=self.root)
        self.assertEqual(state['status'],'report_ready')
        self.assertTrue((self.root/state['id']/'runs'/state['report']['run_id']/'report.html').is_file())
        self.assertNotIn('sensitive-error-text',captured.getvalue())
        self.assertEqual(colab.userdata.get.call_count,1)


if __name__=='__main__':unittest.main()
