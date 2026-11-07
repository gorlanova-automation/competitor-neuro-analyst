"""Combine full historical experiment cards with actual application checks."""
import json
from pathlib import Path


def build(project_root='.'):
    root=Path(project_root);audit=json.loads((root/'stage_2/research/audit.json').read_text(encoding='utf-8'))
    validation=json.loads((root/'stage_4/results/validation.json').read_text(encoding='utf-8'))
    value={'version':'stage_4','model_experiments':audit['experiments'],
        'application_experiments':[
            {'id':'saved_immigration','method':'run_saved_demo; provided saved HTTP texts, not fresh collection',
             'parameters':{'case':'immigration','max_pages':1,'companies':2,'model_enabled':False},
             'result':{'status':'report_ready','lexical_signals':41,'new_llm_calls':0},
             'interpretation':'Сохранённые тексты дают проверяемые цитаты; это не оценка смысловой точности.'},
            {'id':'saved_shift','method':'run_saved_demo; provided saved texts, other industry',
             'parameters':{'case':'shift','max_pages':1,'companies':2,'model_enabled':False},
             'result':{'status':'report_ready','lexical_signals':20,'new_llm_calls':0},
             'interpretation':'Проверено отделение другой отрасли от настроек релокации. Подтверждения демонстрационные.'},
            {'id':'live_browser_workflow_20261107','method':'Assistant operated local browser UI; Python fetched websites',
             'parameters':{'own':'https://immigration-relocator.com/','competitors':['https://okno.agency','https://monolite.pt/'],'max_pages':1,'model_enabled':False},
             'result':{'companies_with_content':3,'lexical_signals':56,'new_llm_calls':0},
             'interpretation':'Сквозной HTTP-сбор и отчёт проверены. Эти сигналы не являются 56 проверенными смысловыми выводами.'},
            {'id':'regression_suite','parameters':{'paid_calls':False,'failure_scenarios':'DNS, TLS, timeout, robots, login, challenge, oversized response, forged quote, invalid checkpoints'},
             'result':validation,'interpretation':'Технические проверки не доказывают полноту базы или семантическую точность.'}],
        'overall_conclusion':'Для извлечения в прежнем размеченном пилоте рабочий выбор Luna с atomic_coverage_v3: 8/8 контрольных цен. Это не победа на всех задачах. В приложении HTTP/хэши/проверки выполняет код, ограниченный смысловой анализ — отдельный модельный вызов. Полная точность ассортимента, маркетинговых выводов и визуала пока не измерена.',
        'model_choice_sources':['https://developers.openai.com/api/docs/models/gpt-6-luna','https://developers.openai.com/api/docs/guides/structured-outputs'],
        'remaining_evaluation':'Нужна независимая смысловая разметка предложений/тона, одинаковые входы для повторных опытов Claude и Gemini и проверка визуала по реальным изображениям.',
        'billing_note':'Исторические тарифные оценки не равны фактическим списаниям. В локальных технических проверках новых LLM-вызовов нет.'}
    live=root/'stage_4/results/live_colab_20261107/runs'
    value['live_model_experiments']=[]
    for run_id in ['60593216-4409-499e-8911-5c8ca5dad8b3','74e981d6-a806-46d9-b441-bfce60478ed0']:
        folder=live/run_id/'model'
        card={'id':run_id,'transport':'proxyapi_live','actual_billed_amount':None,
              'artifacts':str(folder.relative_to(root)).replace('\\','/')}
        for name in ['request','response','failure','execution','analysis']:
            file=folder/(name+'.json')
            if file.exists():card[name]=json.loads(file.read_text(encoding='utf-8'))
        value['live_model_experiments'].append(card)
    value['live_comparison']={'new_llm_calls':2,
        'default_reasoning':'2500 completion tokens spent on reasoning; empty content, finish_reason=length; quarantined.',
        'reasoning_none':'1190 completion tokens; 9 findings and 3 hypotheses. Quotes passed literal checks; semantic review found overclaims.',
        'quality_review':'Assistant QA retained/revised 6 findings, rejected 3, revised 3 hypotheses. Not acceptance by Elena; no semantic accuracy percentage measured.',
        'interpretation':'These runs changed reasoning settings and prompt, so they are not a controlled single-variable comparison. No invoice amount available.'}
    value['billing_note']+=' В реальном Colab выполнены два новых модельных запроса; неуспешный тоже расходовал токены. Сумма списаний не получена.'
    (root/'stage_4/experiments.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    cards=(root/'stage_2/research/experiment_cards.md').read_text(encoding='utf-8')
    text='# Эксперименты итогового приложения\n\nИсторические варианты приведены полностью. Новые технические прогоны отделены от вызовов моделей. Машиночитаемые настройки: experiments.json.\n\n'+cards
    for index,experiment in enumerate(value['application_experiments'],6):
        text+='\n\n## Вариант '+str(index)+' — '+experiment['id']+'\n\n```json\n'+json.dumps(experiment,ensure_ascii=False,indent=2)+'\n```\n'
    text+='\n## Реальные модельные запросы этапа 4\n\nПолные системные сообщения, входы, настройки и ответы сохранены в experiments.json и в results/live_colab_20261107.\n\n```json\n'+json.dumps(value['live_comparison'],ensure_ascii=False,indent=2)+'\n```\n'
    text+='\n## Общий вывод\n\n'+value['overall_conclusion']+'\n\n'+value['remaining_evaluation']+'\n\n'+value['billing_note']+'\n'
    (root/'stage_4/experiments.md').write_text(text,encoding='utf-8')
    print('Written full experiment descriptions:',len(audit['experiments']),'model +',len(value['application_experiments']),'application')


if __name__=='__main__':build()
