import copy
import unittest
from app.ai_analysis import DIMENSIONS,validate_profile,validate_synthesis,partial_profile
from stage_4.workflow import observations,WorkflowError


class SemanticProductTests(unittest.TestCase):
    def setUp(self):
        self.source={'source_id':'s0','text':'Полная консультация стоит 150 евро за час.','url':'https://own.example/','company_url':'https://own.example/','sha256_text':'hash','collected_at':'date','method':'test'}
        self.profile={'dimensions':{k:{'status':'insufficient','summary':'Нет данных.','refs':[]} for k in DIMENSIONS},'gaps':[]}
        self.profile['dimensions']['pricing']={'status':'observed','summary':'Консультация: 150 евро/час.','refs':[{'source_id':'s0','quote':'Полная консультация стоит 150 евро за час.'}]}

    def test_exact_quotes_are_required_and_enriched(self):
        result=validate_profile(self.profile,[self.source])
        self.assertEqual(result['dimensions']['pricing']['refs'][0]['url'],self.source['url'])
        wrong=copy.deepcopy(self.profile);wrong['dimensions']['pricing']['refs']=[{'source_id':'s0','quote':'Сопровождение стоит 150 евро.'}]
        with self.assertRaises(WorkflowError):validate_profile(wrong,[self.source])

    def test_insufficient_cell_can_omit_empty_refs_but_observed_cannot(self):
        self.profile['dimensions']['tone'].pop('refs')
        self.assertEqual(validate_profile(self.profile,[self.source])['dimensions']['tone']['refs'],[])
        self.profile['dimensions']['pricing']['refs']=[]
        with self.assertRaises(WorkflowError):validate_profile(self.profile,[self.source])

    def test_comparison_requires_same_category_and_distinct_companies(self):
        profiles=[{'id':i,'role':role,'dimensions':self.profile['dimensions']} for i,role in [('c0','own'),('c1','competitor')]]
        good={'comparisons':[{'category':'pricing','summary':'Разный состав услуг; суммы не ранжируем.','evidence_ids':['c0:pricing','c1:pricing']}],'recommendations':[],'gaps':[]}
        validate_synthesis(good,profiles)
        for ids in [['c0:pricing'],['c0:pricing','c1:tone'],['c0:pricing','invented:pricing']]:
            bad=copy.deepcopy(good);bad['comparisons'][0]['evidence_ids']=ids
            with self.assertRaises(WorkflowError):validate_synthesis(bad,profiles)

    def test_law_reference_is_not_an_editorial_publication(self):
        text='ВНЖ для детей через учебу по статье 91.2'
        rows=observations([{'status':'ok','text':text,'text_blocks':[text],'url':'https://own.example/','sha256_text':'x'}])
        self.assertFalse(any(r['category']=='editorial' for r in rows))

    def test_invalid_category_does_not_discard_independently_valid_cells(self):
        self.profile['dimensions']['tone']={'status':'observed','summary':'Придумано.','refs':[{'source_id':'s0','quote':'Этой цитаты нет в источнике.'}]}
        result,rejected=partial_profile(self.profile,[self.source])
        self.assertEqual(rejected,['tone'])
        self.assertEqual(result['dimensions']['pricing']['status'],'observed')
        self.assertEqual(result['dimensions']['tone']['status'],'insufficient')

    def test_telegram_candidates_remain_unconfirmed(self):
        from app.telegram_discovery import discover
        from unittest.mock import Mock
        search=Mock(return_value={'status':'ok','candidates':[{'url':'https://t.me/brand_news/123','label':'Brand'},
            {'url':'https://t.me/brand_news/124','label':'Duplicate'}, {'url':'https://t.me/other_channel','label':'Other'},
            {'url':'https://t.me/brand_bot','label':'Bot'},{'url':'https://evil.example/','label':'Not Telegram'}]})
        value=discover({'name':'Brand'},search)
        self.assertEqual(len(value['candidates']),2)
        self.assertTrue(all(c['confirmation_required'] for c in value['candidates']))
        self.assertIn('not_telegram_global_search',value['method'])
        self.assertFalse(search.call_args.kwargs['deduplicate_by_host'])
