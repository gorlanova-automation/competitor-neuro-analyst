"""Offline audit of saved evidence. Standard library only; never calls an API."""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def sha(data):
    return hashlib.sha256(data).hexdigest()

def audit(root):
    root=Path(root)
    run=root/'runs/20261022T111451Z_0f8116'
    errors=[]; sources=[]
    for run_path in sorted((root/'runs').iterdir()):
        if not (run_path/'sources.json').exists():
            continue
        for source in read(run_path/'sources.json'):
            row={'run':run_path.name,**source}
            for path_key,hash_key in [('raw_path','sha256_raw'),('text_path','sha256_text')]:
                if source.get(path_key):
                    path=run_path/source[path_key].replace('\\','/')
                    # sha256_text was computed on normalized Python text before
                    # Windows write_text expanded LF to CRLF. Raw hashes use bytes.
                    actual=sha(path.read_text(encoding='utf-8').encode()) if path_key=='text_path' and path.is_file() else sha(path.read_bytes()) if path.is_file() else None
                    if actual!=source[hash_key]:
                        errors.append({'check':'source_hash','run':run_path.name,'source_id':source['source_id'],'file':source[path_key]})
            sources.append(row)
    chunks=read(run/'chunks.json')
    chunk_map={c['chunk_id']:c for c in chunks}
    for chunk in chunks:
        source=next(s for s in read(run/'sources.json') if s['source_id']==chunk['source_id'])
        text=(run/source['text_path'].replace('\\','/')).read_text(encoding='utf-8')
        if text[chunk['start']:chunk['end']]!=chunk['text']:
            errors.append({'check':'chunk_offset','chunk_id':chunk['chunk_id']})
    rates={'openai/gpt-6-luna':(30,150),'google/gemini-3.5-flash-lite':(91,758),'anthropic/claude-haiku-4-5':(295,1474)}
    cards=[]
    for folder in sorted((run/'experiments').iterdir()):
        meta=read(folder/'experiment.json')
        if sha(meta['prompt'].encode())!=meta['prompt_sha256']:
            errors.append({'check':'prompt_hash','experiment':folder.name})
        requests=[]; responses=[]
        for path in sorted(folder.glob('*_request.json')):
            request=read(path); chunk_id=path.name.removesuffix('_request.json')
            content=json.loads(request['messages'][1]['content'])
            if content['text']!=chunk_map[chunk_id]['text'] or request['messages'][0]['content']!=meta['prompt']:
                errors.append({'check':'request_corpus_or_prompt','experiment':folder.name,'chunk_id':chunk_id})
            requests.append({'chunk_id':chunk_id,'text_sha256':sha(content['text'].encode()),'request_sha256':sha(path.read_bytes())})
        for path in sorted(folder.glob('*_response.json')):
            response=read(path)
            responses.append({'file':path.name,'finish_reason':response.get('finish_reason'),'model_returned':response.get('model'),'usage':response.get('usage')})
        facts=read(folder/'facts.json')
        for fact in facts:
            chunk=chunk_map[fact['chunk_id']]
            if fact['evidence'] not in chunk['text'] or fact['evidence_start']!=chunk['start']+chunk['text'].find(fact['evidence']):
                errors.append({'check':'fact_quote_or_offset','experiment':folder.name,'fact_id':fact['fact_id']})
        complete=len(responses)==meta['chunks_attempted'] and all(r['usage'] and all(k in r['usage'] for k in ('prompt_tokens','completion_tokens')) for r in responses)
        inputs=sum((r['usage'] or {}).get('prompt_tokens',0) for r in responses)
        outputs=sum((r['usage'] or {}).get('completion_tokens',0) for r in responses)
        rate=rates[meta['model']]
        elapsed=(datetime.fromisoformat(meta['completed_at'])-datetime.fromisoformat(meta['started_at'])).total_seconds()
        version=read(root/'code_versions/index.json').get(folder.name,{})
        cards.append({'experiment':folder.name,'goal':'Compare prompts' if folder.name in ('20261022T111947Z_adab53','20261022T112126Z_2421a6') else 'Refine prompt and validator' if folder.name=='20261022T113037Z_be7ea6' else 'Compare models on evidence_v2','model':meta['model'],'settings':meta['settings'],'schema':meta['schema'],'prompt':meta['prompt'],'prompt_sha256':meta['prompt_sha256'],'code_version':version,'runtime_collector_sha256':meta.get('collector_sha256'),'corpus_sha256':sha((run/'chunks.json').read_bytes()),'runtime_corpus_sha256':meta.get('chunks_sha256'),'started_at':meta['started_at'],'completed_at':meta['completed_at'],'elapsed_pipeline_seconds':round(elapsed,3),'per_request_latency_seconds':None,'inputs':requests,'responses':responses,'facts_accepted':len(facts),'quarantine':read(folder/'quarantine.json'),'failures':read(folder/'failures.json'),'reference_result':read(folder/'reference_comparison.json')['summary'],'field_counts':dict(Counter(f['field'] for f in facts)),'usage':{'prompt_tokens':inputs,'completion_tokens':outputs,'complete':complete},'cost':{'tariff_estimate_rub':(inputs*rate[0]+outputs*rate[1])/1000000 if complete else None,'actual_billed_rub':None,'rate_date':'2026-10-22','rates_rub_per_million':{'input':rate[0],'output':rate[1]},'note':'Published base rates, not an invoice; includes saved tokens of incomplete responses.'},'semantic_review':'not_complete'})
    input_sets=[[(r['chunk_id'],r['text_sha256']) for r in card['inputs']] for card in cards]
    same_inputs=all(s==input_sets[0] for s in input_sets)
    if not same_inputs:
        errors.append({'check':'different_experiment_inputs'})
    result={'audit_version':1,'mode':'offline_no_network_no_api_key','source_rows':len(sources),'source_statuses':dict(Counter(s['status'] for s in sources)),'chunks_in_colab_corpus':len(chunks),'experiments':cards,'same_inputs_across_experiments':same_inputs,'integrity_errors':errors,'checks_passed':not errors,'limitations':['Exact citations and hashes do not establish semantic accuracy.','Only two companies and two price-control chunks were sent to models.','v3 changes both prompt and validator; their effects are confounded.','Code hashes for early runs are reconstructed from saved runtime snapshots, not logged at execution.','Actual billing and individual request latency were not recorded.']}
    output=root/'research'; output.mkdir(exist_ok=True)
    (output/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with (output/'experiment_register.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f); writer.writerow(['experiment','model','prompt_sha256','matched_prices','reference_total','accepted','quarantine','failed_calls','elapsed_pipeline_seconds','tariff_estimate_rub','actual_billed_rub'])
        for c in cards:
            writer.writerow([c['experiment'],c['model'],c['prompt_sha256'],c['reference_result']['matched_by_rules'],c['reference_result']['reference_in_tested_chunks'],c['facts_accepted'],len(c['quarantine']),len(c['failures']),c['elapsed_pipeline_seconds'],c['cost']['tariff_estimate_rub'],'not_recorded'])
    lines=['# Паспорта реально выполненных экспериментов','', 'Источник — сохранённые запросы, ответы и метаданные. Этот отчёт пересчитан офлайн без API. Полные настройки и схема также находятся в research/audit.json.','',f'Одинаковые входные тексты: {same_inputs}. Ошибок целостности: {len(errors)}.','']
    for c in cards:
        conclusions={
            '20261022T111947Z_adab53':'Базовый промпт сохранил 8/8 контрольных цен; отдельные цитаты цен содержат только сумму и не доказывают связь с услугой. Нужна более строгая привязка.',
            '20261022T112126Z_2421a6':'8/8 цен при меньшем расходе, чем v1; потеряны отдельные service/geography. Обнаружена запись, где короткий заголовок не доказывает перечисление типов виз. Дешевизна не оправдывает эти дефекты.',
            '20261022T112655Z_fabfd2':'Gemini часто возвращает сумму у field=service; 58 записей не прошли контракт. 0/8 после валидатора не означает, что модель не увидела цены. Нужен адаптированный промпт.',
            '20261022T112655Z_3a2e17':'Ответ по первой странице завершился length при 4096 токенах, второй завершился stop. Требуется поддерживаемый явный лимит вывода и проверка точности цитат; общего вывода о качестве Claude нет.',
            '20261022T113037Z_be7ea6':'Сохранены 8/8 цен, восстановлены отдельные поля, исправлен наблюдавшийся дефект цитаты о типах виз. Расход выше v2. Промпт и валидатор изменены одновременно, полная смысловая оценка не выполнена.'}
        c['conclusion']=conclusions[c['experiment']]
        lines += ['## '+c['experiment'],'','Цель: '+c['goal']+'. Модель: '+c['model']+'.','',f"UTC: {c['started_at']} → {c['completed_at']}. Время обработки опыта: {c['elapsed_pipeline_seconds']} с; индивидуальная задержка запросов не записана.",'','Версия кода: '+json.dumps(c['code_version'],ensure_ascii=False)+'.','', 'Настройки: `'+json.dumps(c['settings'],ensure_ascii=False)+'`.','',f"Контроль: {c['reference_result']['matched_by_rules']}/8; принято {c['facts_accepted']}, карантин {len(c['quarantine'])}, ошибок {len(c['failures'])}. Полная смысловая точность не размечена.",'',f"Токены: {c['usage']['prompt_tokens']} вход / {c['usage']['completion_tokens']} выход. Тарифная оценка {c['cost']['tariff_estimate_rub']} RUB, фактическое списание неизвестно.",'','Ошибки: `'+json.dumps(c['failures'],ensure_ascii=False)+'`.','', 'Полный системный промпт (SHA256 '+c['prompt_sha256']+'):','','```text',c['prompt'],'```','', 'Полный пользовательский промпт для каждого фрагмента сохранён в соответствующем *_request.json; текст и хэш сверены с корпусом.','']
        lines += ['Вывод: '+c['conclusion'],'']
    lines += ['## Выводы','','Luna v2 сохранила 8/8 контрольных цен и уменьшила вывод/тарифную оценку относительно v1, но потеряла отдельные service/geography и допустила неполное доказательство перечисления виз. Gemini не выполнила контракт amount/field; Claude имела обрезанный ответ length. Это дефекты текущей конфигурации, не общий рейтинг моделей. v3 исправляет наблюдавшийся пример и сохраняет 8/8 цен, однако стоит дороже v2, а валидатор изменён одновременно. Для данного пилота Luna выбрана предварительно; окончательное качество по всем полям не измерено.']
    (output/'experiment_cards.md').write_text('\n'.join(lines),encoding='utf-8')
    (output/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('root')
    r=audit(p.parse_args().root)
    print(json.dumps({k:r[k] for k in ('mode','source_rows','source_statuses','chunks_in_colab_corpus','same_inputs_across_experiments','integrity_errors','checks_passed')},ensure_ascii=False,indent=2))
