import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import requests
from app.search import official_search,manual_candidates


class Response:
    def __init__(self,data=None,status=200,raw=None):
        self.status_code=status;self.body=raw if raw is not None else json.dumps(data or {}).encode()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def iter_content(self,size):yield self.body


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.settings={'ANALYST_SEARCH_PROVIDER':'tavily','ANALYST_SEARCH_ENABLED':'1','TAVILY_API_KEY':'test-search-token',
                       'ANALYST_SEARCH_BUDGET_FILE':str(Path(self.temp.name)/'budget.json')}

    def test_tavily_contract_deduplication_and_no_secret_in_result(self):
        session=Mock();session.request.return_value=Response({'results':[
            {'url':'https://rival.example/services','title':'Rival','content':'Public services'},
            {'url':'https://www.rival.example/','title':'Duplicate'},
            {'url':'https://own.example/','title':'Own'},
            {'url':'https://127.0.0.1/','title':'Private'},
            {'url':'https://another.example/','title':'test-search-token'}],'usage':{'credits':1}})
        result=official_search('relocation',own_url='https://own.example/',session=session,settings=self.settings)
        self.assertEqual(result['status'],'ok');self.assertEqual(len(result['candidates']),2)
        self.assertNotIn('test-search-token',json.dumps(result));self.assertEqual(result['reported_credits'],1)
        self.assertEqual(session.request.call_count,1)
        args,kwargs=session.request.call_args
        self.assertEqual(args[0],'POST');self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(kwargs['json']['search_depth'],'basic');self.assertFalse(kwargs['json']['auto_parameters'])
        self.assertEqual(kwargs['headers']['Authorization'],'Bearer test-search-token')

    def test_errors_stop_without_retry_or_error_body_leak(self):
        for status,expected in [(401,'authentication_failed'),(403,'access_denied'),(429,'rate_limited'),(432,'quota_exhausted'),(503,'provider_unavailable'),(302,'redirect_refused')]:
            session=Mock();session.request.return_value=Response(status=status,raw=b'test-search-token')
            result=official_search('query',session=session,settings=self.settings)
            self.assertEqual(result['status'],expected);self.assertEqual(session.request.call_count,1)
            self.assertNotIn('test-search-token',json.dumps(result));self.assertEqual(result['candidates'],[])
        for exception,expected in [(requests.Timeout('test-search-token'),'timeout'),(requests.ConnectionError('test-search-token'),'network_error')]:
            session=Mock();session.request.side_effect=exception
            self.assertEqual(official_search('query',session=session,settings=self.settings)['status'],expected)
            self.assertEqual(session.request.call_count,1)

    def test_unconfigured_and_budget_exhausted_make_no_request(self):
        session=Mock()
        self.assertEqual(official_search('q',session=session,settings={})['status'],'not_configured')
        env={**self.settings,'ANALYST_SEARCH_MONTHLY_LIMIT':'0'}
        self.assertEqual(official_search('q',session=session,settings=env)['status'],'budget_exhausted')
        session.request.assert_not_called()

    def test_brave_and_malformed_responses(self):
        env={**self.settings,'ANALYST_SEARCH_PROVIDER':'brave','BRAVE_SEARCH_API_KEY':'test-brave-token'}
        session=Mock();session.request.return_value=Response({'web':{'results':[{'url':'https://rival.example/','title':'Rival'}]}})
        value=official_search('q',session=session,settings=env)
        self.assertEqual(value['status'],'ok');self.assertEqual(session.request.call_args.args[0],'GET')
        self.assertEqual(session.request.call_args.kwargs['headers']['X-Subscription-Token'],'test-brave-token')
        for raw in [b'not json',b'[]',b'{"results": "bad"}']:
            session=Mock();session.request.return_value=Response(raw=raw)
            self.assertEqual(official_search('q',session=session,settings=self.settings)['status'],'invalid_response')

    def test_manual_results_preserve_human_provenance_and_filter_private_urls(self):
        values=manual_candidates('Company https://rival.example/\nDuplicate https://rival.example/services\nhttps://127.0.0.1/','q')
        self.assertEqual(len(values),1);self.assertEqual(values[0]['label'],'Company')
        self.assertEqual(values[0]['added_by'],'user_provided_search_result')


if __name__=='__main__':unittest.main()
