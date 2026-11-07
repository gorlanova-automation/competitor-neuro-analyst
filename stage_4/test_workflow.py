import hashlib
import json
import tempfile
import unittest
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

    def test_search_failure_preserves_manual_path(self):
        identifier=self.confirmed()
        with patch('stage_4.workflow.fetch',return_value={'url':'https://html.duckduckgo.com/','status':'challenge_page'}):
            state=self.run_action(project_id=identifier,action='search')
        self.assertEqual(state['search']['candidates'],[])
        self.assertTrue(state['competitors_confirmed'])

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


if __name__=='__main__':unittest.main()
