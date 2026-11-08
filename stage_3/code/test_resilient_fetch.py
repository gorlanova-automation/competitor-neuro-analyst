import unittest
from unittest.mock import Mock,patch
import tempfile
from pathlib import Path
import requests
from resilient_fetch import request,fetch


class Response:
    def __init__(self,status=200,body=b'<html><title>Site</title><p>'+b'public service '*30+b'</p></html>',url='https://example.org/',headers=None):
        self.status_code=status;self.body=body;self.url=url
        self.headers=headers or {'Content-Type':'text/html'};self.encoding='utf-8'
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def iter_content(self,size):yield self.body


class FetchTests(unittest.TestCase):
    def test_content_blocks_exclude_navigation_and_preserve_exact_quotes(self):
        paragraph='We offer company registration with clear conditions and consultation for international clients.'
        navigation='Services pricing contact home navigation menu repeated words for the site.'
        body=('<html><nav><p>'+navigation+'</p></nav><main><p>'+paragraph+'</p><p>'+paragraph+'</p></main></html>').encode()
        session=Mock();session.get.side_effect=[Response(404),Response(body=body)]
        source=fetch(session,'https://example.org/',{})
        self.assertEqual(source['text_blocks'],[paragraph])
        self.assertIn(paragraph,source['text'])
        from stage_4.workflow import observations
        rows=observations([source])
        self.assertTrue(rows)
        self.assertTrue(all(r['quote']==paragraph for r in rows))

    def test_new_runs_cannot_overwrite_previous_sources(self):
        from market_research import create_run_directory
        with tempfile.TemporaryDirectory() as folder:
            first=create_run_directory(folder)
            (first/'evidence.json').write_text('original')
            second=create_run_directory(folder)
            self.assertNotEqual(first,second)
            self.assertEqual((first/'evidence.json').read_text(),'original')

    def test_recovery_queue_retains_cause_without_counting_success(self):
        from market_research import recovery_queue
        queue=recovery_queue([{'company_id':'test','sources':[
            {'url':'https://example.org/','status':'ok'},
            {'url':'https://example.org/blog','status':'robots_unavailable',
             'failure_kind':'timeout','next_action':'browser_review','attempts':[{'attempt':1}]}]}])
        self.assertEqual(len(queue),1)
        self.assertEqual(queue[0]['cause'],'timeout')
        self.assertEqual(queue[0]['next_action'],'browser_review')

    def test_transient_timeout_is_retried_and_success_audited(self):
        s=Mock();s.get.side_effect=[requests.Timeout(),Response()]
        response,log=request(s,'https://example.org/',sleep=lambda _:None)
        self.assertTrue(response);self.assertEqual([a['outcome'] for a in log['attempts']],['timeout','received'])

    def test_dns_and_tls_are_not_blindly_retried(self):
        for exc,status in [(requests.ConnectionError('getaddrinfo failed 11001'),'dns_error'),(requests.exceptions.SSLError(),'tls_error')]:
            s=Mock();s.get.side_effect=exc
            response,log=request(s,'https://example.org/',sleep=lambda _:None)
            self.assertIsNone(response);self.assertEqual(log['status'],status);self.assertEqual(s.get.call_count,1)

    def test_rate_limit_long_delay_is_deferred(self):
        s=Mock();s.get.return_value=Response(429,headers={'Retry-After':'300'})
        response,log=request(s,'https://example.org/',sleep=lambda _:self.fail('Must not wait/retry'))
        self.assertEqual(log['status'],'rate_limited');self.assertEqual(s.get.call_count,1)

    def test_robots_denial_does_not_fetch_content(self):
        s=Mock();s.get.return_value=Response(body=b'User-agent: *\nDisallow: /')
        row=fetch(s,'https://example.org/',{})
        self.assertEqual(row['status'],'robots_disallowed');self.assertEqual(s.get.call_count,1)

    def test_robots_html_challenge_does_not_mean_permission(self):
        s=Mock();s.get.return_value=Response(body=b'<html>checking your browser</html>')
        row=fetch(s,'https://example.org/',{})
        self.assertEqual(row['status'],'robots_unavailable')
        self.assertEqual(row['failure_kind'],'robots_invalid_response')
        self.assertEqual(s.get.call_count,1)

    def test_robots_network_failure_is_distinct_from_denial(self):
        s=Mock();s.get.side_effect=requests.ConnectionError('getaddrinfo failed')
        row=fetch(s,'https://example.org/',{})
        self.assertEqual(row['status'],'robots_unavailable');self.assertEqual(row['failure_kind'],'dns_error')

    def test_challenge_is_not_research_success(self):
        s=Mock();s.get.side_effect=[Response(404),Response(body=b'<title>Just a moment</title><p>Verify you are human</p>')]
        self.assertEqual(fetch(s,'https://example.org/',{})['status'],'challenge_page')

    def test_search_engine_challenge_is_not_empty_success(self):
        s=Mock();s.get.side_effect=[Response(404),Response(body=b'<title>DuckDuckGo</title><p>Unfortunately, bots use DuckDuckGo too. Please complete the following challenge. Select all squares containing a duck.</p>')]
        self.assertEqual(fetch(s,'https://example.org/',{})['status'],'challenge_page')

    def test_login_redirect_is_not_a_public_feed(self):
        s=Mock();s.get.side_effect=[Response(404),Response(url='https://example.org/accounts/login/')]
        self.assertEqual(fetch(s,'https://example.org/',{})['status'],'login_required')

    def test_size_limit_stops_collection(self):
        s=Mock();s.get.return_value=Response(body=b'x'*101)
        response,log=request(s,'https://example.org/',limit=100)
        self.assertIsNone(response);self.assertEqual(log['status'],'size_limit')

    def test_failed_seed_does_not_hide_next_confirmed_seed(self):
        from market_research import collect_company
        good={'status':'ok','url':'https://example.org/services','final_url':'https://example.org/services',
              'text':'service catalogue','links':[],'sha256_text':'test','collected_at':'2026-11-05'}
        with tempfile.TemporaryDirectory() as folder,patch('market_research.fetch',side_effect=[{'status':'timeout'},good]) as get:
            row=collect_company({'id':'test','name':'Test','seed_urls':['https://example.org/','https://example.org/services']},1,Path(folder))
        self.assertEqual(row['pages_ok'],1);self.assertEqual(get.call_count,2)

    def test_dns_www_uses_same_apex_without_changing_brand(self):
        from market_research import collect_company
        good={'status':'ok','url':'https://example.org/','final_url':'https://example.org/',
              'text':'service catalogue','links':[],'sha256_text':'test','collected_at':'2026-11-05'}
        with tempfile.TemporaryDirectory() as folder,patch('market_research.fetch',side_effect=[{'status':'robots_unavailable','failure_kind':'dns_error'},good]) as get:
            row=collect_company({'id':'test','name':'Test','seed_urls':['https://www.example.org/']},1,Path(folder))
        self.assertEqual(row['pages_ok'],1)
        self.assertEqual(get.call_args_list[1].args[1],'https://example.org/')
