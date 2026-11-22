import copy
import unittest
from pathlib import Path
from unittest.mock import patch
from app.ai_analysis import DIMENSIONS,validate_profile,validate_synthesis,partial_profile,review_recommendations
from stage_4.workflow import observations,WorkflowError


class SemanticProductTests(unittest.TestCase):
    def test_search_channel_is_collected_only_with_name_and_profile_backlink(self):
        from app.telegram_discovery import collect_verified_candidates
        report={'companies':[{'name':'Brand','url':'https://brand.example/','telegram_discovery':{
            'candidates':[{'url':'https://t.me/brand_news','confirmation_required':True},
                          {'url':'https://t.me/unrelated_news','confirmation_required':True}]}}]}
        raw=[{'url':'https://brand.example/','sources':[]}]
        good={'status':'ok','html':'<div class="tgme_channel_info_header_title">Brand News</div><div class="tgme_channel_info_description"><a href="https://brand.example/">Site</a></div>','sha256_text':'hash'}
        wrong={'status':'ok','html':'<div class="tgme_channel_info_description"><a href="https://brand.example.evil.test/">Site</a></div>'}
        with patch('stage_4.workflow.fetch',side_effect=[good,wrong]),patch('stage_4.workflow.sample_publications',return_value=([{'url':'https://t.me/brand_news/1'}],[])) as sample:
            collect_verified_candidates(report,raw,None)
        self.assertEqual(sample.call_count,1)
        self.assertEqual(len(raw[0]['sources']),1)
        candidates=report['companies'][0]['telegram_discovery']['candidates']
        self.assertFalse(candidates[0]['confirmation_required'])
        self.assertTrue(candidates[1]['confirmation_required'])

    def test_recommendation_review_matches_ids_and_requires_complete_coverage(self):
        rows = [{'evidence_ids': ['c0:pricing']} for _ in range(2)]
        cells = {'c0:pricing': ({'name': 'Own', 'role': 'own'}, {
            'summary': 'Консультация', 'refs': [], 'status': 'observed',
        })}
        rejected = {'id': 'r0', 'decision': 'reject', 'reason': 'Услуги различаются.'}
        approved = {'id': 'r1', 'decision': 'approve', 'reason': 'Предложен измеримый тест.'}
        with patch('app.ai_analysis.call_model') as model:
            model.return_value = {'verdicts': [approved, rejected]}, None
            verdicts, _ = review_recommendations(rows, cells, '', Path('unused'))
            self.assertEqual(verdicts, [rejected, approved])
            for invalid in ([approved], [approved, approved], [approved, {**rejected, 'id': 'r2'}]):
                model.return_value = {'verdicts': invalid}, None
                with self.assertRaises(WorkflowError):
                    review_recommendations(rows, cells, '', Path('unused'))

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

    def test_action_plan_requires_steps_deliverable_and_decision_rule(self):
        profiles=[{'id':i,'role':role,'dimensions':self.profile['dimensions']} for i,role in [('c0','own'),('c1','competitor')]]
        row={'kind':'adapt','title':'Проверить формат','action':'Провести тест','reason':'Различие форматов',
             'success_check':'Доля оплаченных заказов','evidence_ids':['c0:pricing','c1:pricing'],
             'priority':'средний','timeframe':'4 недели','owner_role':'Маркетолог',
             'deliverable':'Тестовая страница','steps':['Зафиксировать базу','Запустить тест','Оценить результат'],
             'decision_rule':'Продолжить при заранее согласованном улучшении'}
        value={'comparisons':[],'recommendations':[row],'gaps':[]}
        validate_synthesis(value,profiles)
        for key in ('deliverable','steps','decision_rule'):
            invalid=copy.deepcopy(value)
            invalid['recommendations'][0].pop(key)
            with self.assertRaises(WorkflowError):validate_synthesis(invalid,profiles)

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
