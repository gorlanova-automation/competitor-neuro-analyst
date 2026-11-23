import copy
import unittest
from pathlib import Path
from unittest.mock import patch
from app.ai_analysis import DIMENSIONS,validate_profile,validate_synthesis,partial_profile,review_recommendations
from stage_4.workflow import observations,WorkflowError


class SemanticProductTests(unittest.TestCase):
    def test_repeated_long_menu_does_not_replace_actual_page_content(self):
        from app.ai_analysis import company_input
        menu='Shared menu of services and locations. '*180
        body_a='Unique catalogue description and methodology. '*25
        body_b='Unique expertise and delivery process. '*25
        common={'status':'ok','sha256_text':'hash','collected_at':'date','method':'test'}
        pages=[{**common,'url':'https://example.com/'+str(i),'text':menu+body,'text_blocks':[menu,body]} for i,body in enumerate((body_a,body_b))]
        sources=company_input({'url':'https://example.com/','role':'own','sources':pages},max_characters=6000)
        self.assertTrue(any(body_a[:120] in s['text'] for s in sources))
        self.assertTrue(any(body_b[:120] in s['text'] for s in sources))
        self.assertTrue(all(s['text'] in next(p['text'] for p in pages if p['url']==s['url']) for s in sources))

    def test_telegram_posts_do_not_crowd_out_the_service_catalogue(self):
        from app.ai_analysis import company_input
        base={'status':'ok','sha256_text':'hash','collected_at':'date','method':'test'}
        page={**base,'url':'https://example.com/','text':'s'*30000}
        posts=[{**base,'url':'https://t.me/example/'+str(i),'source_kind':'publication','text':'p'*3000} for i in range(20)]
        sources=company_input({'url':page['url'],'role':'own','sources':[page]+posts})
        self.assertEqual(len(sources[0]['text']),30000)
        self.assertLessEqual(sum(len(s['text']) for s in sources),45000)
        self.assertEqual(len({s['source_id'] for s in sources}),len(sources))

    def test_strengths_require_own_company_and_same_criterion_evidence(self):
        from app.assessment import assess
        cell={'status':'observed','summary':'Service package','refs':[{'quote':'A full service package','url':'https://example.com/','sha256_text':'hash'}]}
        profiles=[{'id':'c0','name':'Own','url':'https://own.example/','role':'own','dimensions':{'assortment':cell,'pricing':cell}},
                  {'id':'c1','name':'Rival','url':'https://rival.example/','role':'competitor','dimensions':{'assortment':cell,'pricing':cell}}]
        rows=[{'category':'assortment','verdict':'own_strength','summary':'Broader published package','evidence_ids':['c0:assortment','c1:assortment']},
              {'category':'pricing','verdict':'own_strength','summary':'Mixed criteria must be rejected','evidence_ids':['c0:assortment','c1:pricing']}]
        with patch('app.assessment.call_model',return_value=({'criteria':rows},{})):
            value,_=assess(profiles,'test-key',None)
        self.assertEqual(len(value['criteria']),1)
        self.assertEqual(len(value['criteria'][0]['evidence']),2)
        self.assertNotIn('всем',value['title'])

    def test_leading_conclusion_requires_every_studied_rival(self):
        from app.assessment import assess
        cell={'status':'observed','summary':'Published offer','refs':[{'quote':'Published offer details','url':'https://example.com/'}]}
        profiles=[{'id':'c'+str(i),'name':str(i),'url':'https://example.com/','role':'own' if i==0 else 'competitor','dimensions':{'assortment':cell,'pricing':cell}} for i in range(3)]
        rows=[{'category':category,'verdict':'own_strength','summary':'Observed advantage','evidence_ids':['c0:'+category,'c1:'+category]} for category in ('assortment','pricing')]
        with patch('app.assessment.call_model',return_value=({'criteria':rows},{})):
            value,_=assess(profiles,'test-key',None)
        self.assertNotIn('всем',value['title'])
        for row in rows:row['evidence_ids'].append('c2:'+row['category'])
        with patch('app.assessment.call_model',return_value=({'criteria':rows},{})):
            value,_=assess(profiles,'test-key',None)
        self.assertIn('всем сопоставленным',value['title'])

    def test_one_invalid_comparison_does_not_discard_other_comparisons(self):
        from app.ai_analysis import partial_synthesis
        cell={'status':'observed','summary':'Confirmed','refs':[]}
        profiles=[{'id':'c0','role':'own','dimensions':{'assortment':cell,'conversion':cell}},
                  {'id':'c1','role':'competitor','dimensions':{'assortment':cell,'conversion':cell}}]
        good={'category':'assortment','summary':'Different products','evidence_ids':['c0:assortment','c1:assortment']}
        bad={'category':'conversion','summary':'Mixed criteria','evidence_ids':['c0:assortment','c1:conversion']}
        result,rejected=partial_synthesis({'comparisons':[good,bad],'recommendations':[],'gaps':[]},profiles)
        self.assertEqual(result['comparisons'],[good])
        self.assertEqual(len(rejected),1)
        self.assertEqual(rejected[0]['index'],1)

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
        self.assertEqual(len(value['candidates']),1)
        self.assertTrue(all(c['confirmation_required'] for c in value['candidates']))
        self.assertIn('not_telegram_global_search',value['method'])
        self.assertFalse(search.call_args.kwargs['deduplicate_by_host'])

    def test_telegram_search_uses_site_brand_when_company_name_is_a_url(self):
        from app.telegram_discovery import search_name,relevant_candidates
        company={'name':'https://youtube.fghk.ru/landing/ru.html','url':'https://youtube.fghk.ru/','site_title':'SHIFT дай следующему ролику больше силы'}
        self.assertEqual(search_name(company),'SHIFT')
        rows=[{'url':'https://t.me/car_news','label':'Автомобили','snippet':'Канал машин'},
              {'url':'https://t.me/shift_video','label':'SHIFT','snippet':'Анализ видео'}]
        self.assertEqual(relevant_candidates(company,rows),[rows[1]])
