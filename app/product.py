"""User-facing research service. Reuses the source collector; no paid model calls."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from stage_4.workflow import run_project, save, timestamp, WorkflowError, public_url

LABELS={'assortment':'Ассортимент','pricing':'Цены и условия','positioning':'Позиционирование',
        'conversion':'Обращение и продажа','editorial':'Материалы и публикации','tone':'Тон и обращение'}


def host(url):return (urlsplit(url).hostname or '').removeprefix('www.')


def product_report(result,state,raw_sources=None):
    """Actions are grounded experiments, not invented judgements about businesses."""
    names={c['url']:c.get('name') for c in state['competitors']}
    companies=[]
    for original in result['companies']:
        item={**original}
        def score(e):
            quote=e['quote'];key=e['category']
            relevant={'assortment':r'предлага|сопровождаем|оказываем|offer|provide|solution',
                      'positioning':r'эксперт|опыт|работаем|основан|expert|experience|since',
                      'conversion':r'свяж|запиш|оставьте|начните|book|contact|start',
                      'editorial':r'материал|обновляем|практическ|стать|article|guide',
                      'pricing':r'\d.*[€$]|[€$].*\d'}.get(key,'')
            return (e.get('method')=='content_block_requires_review',bool(re.search(relevant,quote,re.I)),80<=len(quote)<=360)
        item['evidence']=sorted(original['evidence'],key=score,reverse=True)
        item['sections']=[];seen=set()
        for raw in raw_sources or []:
            if raw['url']!=item['url']:continue
            for source in raw['sources']:
                if source['status']!='ok':continue
                for heading in source.get('headings',[]):
                    if 8<=len(heading)<=140 and heading.casefold() not in seen:
                        seen.add(heading.casefold());item['sections'].append({'title':heading,'url':source.get('final_url',source['url'])})
        item['dimensions']={**original['dimensions'],'tone':0}
        item['name']=state['profile']['company_name'] if item['role']=='own' else names.get(item['url']) or item['name']
        item['gaps']=[label+': недостаточно данных' for key,label in LABELS.items() if not item['dimensions'].get(key)]
        item['gaps'].append('Визуал: требуется просмотр реальных снимков')
        companies.append(item)
    actions=[]  # Recommendations require semantic comparison, not keyword presence.
    return {'run_id':result['run_id'],'generated_at':result['generated_at'],'profile':result['profile'],
            'companies':companies,'dimensions':LABELS,'recommendations':actions,'limits':result['limits'],
            'method':'База источников и лексическая выборка. Смысловой анализ ИИ ещё не выполнен.',
            'new_llm_calls':0}


class Competitor(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=200)
    url:str=Field(min_length=8,max_length=2000)


class Command(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:str=Field(pattern='^(start|confirm_profile|confirm_competitors|collect|search|import_search|analyze|discover_telegram|confirm_telegram)$')
    website_url:str=Field(default='',max_length=2000)
    profile:dict[str,str]|None=None
    competitors:list[Competitor]|None=Field(default=None,max_length=20)
    uploads:dict[str,dict[str,str]]|None=None
    max_pages:int=Field(default=4,ge=1,le=8)
    search_text:str=Field(default='',max_length=100000)
    telegram_channels:dict[str,str]|None=Field(default=None,max_length=20)


def install(api,storage,project_root):
    router=APIRouter(prefix='/api');pool=ThreadPoolExecutor(max_workers=2)
    api.state.product_pool=pool
    jobs=storage/'jobs';jobs.mkdir(exist_ok=True);guard=Lock();job_io=Lock();active=set()
    def job_save(file,value):
        with job_io:save(file,value)
    # An interrupted process must not leave an eternal progress indicator.
    for file in jobs.glob('*.json'):
        value=json.loads(file.read_text(encoding='utf-8'))
        if value['status'] in ('queued','running'):
            value.update(status='failed',error='Сервер перезапущен. Предыдущие результаты сохранены; повторите действие.')
            save(file,value)

    def read(identifier):
        path=storage/'projects'/str(identifier)/'state.json'
        if not path.is_file():raise HTTPException(404,'Исследование не найдено.')
        return json.loads(path.read_text(encoding='utf-8'))

    def suggest(state):
        # Known user-agreed research is relevant only for the matching own domain.
        catalog=json.loads((project_root/'stage_3/input/companies.json').read_text(encoding='utf-8'))
        if host(state['url'])!=host(catalog[0]['seed_urls'][0]):return []
        return [{'name':c['name'],'url':c['seed_urls'][0],'origin':'Согласованный список прежнего исследования'} for c in catalog[1:]]

    def submit(body,identifier=None):
        key=str(identifier) if identifier else str(uuid4())
        with guard:
            if key in active:raise HTTPException(409,'Для этого исследования уже выполняется задание.')
            if len(active)>=4:raise HTTPException(429,'Сейчас выполняются другие исследования. Повторите чуть позже.')
            active.add(key)
        job_id=str(uuid4());file=jobs/(job_id+'.json')
        job={'id':job_id,'project_id':str(identifier) if identifier else None,'status':'queued','step':'Подготовка','created_at':timestamp()}
        job_save(file,job)
        def work():
            def progress(message):
                job.update(step=message,updated_at=timestamp());job_save(file,job)
            try:
                job['status']='running';progress('Получаем профиль' if body.action=='start' else 'Обновляем исследование')
                if body.action in ('discover_telegram','confirm_telegram'):
                    import os
                    from stage_4.workflow import new_session,sample_publications,compare,render_report
                    state=read(identifier)
                    if not state.get('report'):raise WorkflowError('Сначала соберите материалы сайтов.')
                    directory=storage/'projects'/state['id']/'runs'/state['report']['run_id']
                    raw=json.loads((directory/'sources.json').read_text(encoding='utf-8'))
                    if body.action=='discover_telegram':
                        from .telegram_discovery import enrich
                        base=json.loads((directory/'result.json').read_text(encoding='utf-8'))
                        prepared=product_report(base,state,raw)
                        value=enrich(prepared,directory/'telegram_search'/str(uuid4()),os.environ.get('PROXYAPI_KEY'))
                        save(directory/'telegram_candidates.json',value)
                    else:
                        if not body.telegram_channels:raise WorkflowError('Подтвердите компанию и Telegram-канал.')
                        for company_url,channel_url in body.telegram_channels.items():
                            company=next((c for c in raw if host(c['url'])==host(public_url(company_url))),None)
                            parts=urlsplit(channel_url);username=parts.path.strip('/')
                            if not company or parts.scheme!='https' or parts.hostname!='t.me' or parts.query or parts.fragment or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{3,}',username) or username.lower().endswith('bot'):raise WorkflowError('Нужен подтверждённый публичный канал https://t.me/имя и компания из исследования.')
                            with new_session() as session:
                                posts,feeds=sample_publications([{'status':'ok','url':company['url'],'links':[{'url':channel_url}],
                                    'channel_discovery':'user_confirmed_not_site_link'}],session)
                            existing={s['url'] for s in company['sources']}
                            company['sources'] += [p for p in posts if p['url'] not in existing]
                            company.setdefault('publication_samples',[]).extend(feeds)
                        run_id=str(uuid4());directory=storage/'projects'/state['id']/'runs'/run_id;directory.mkdir()
                        base=compare(raw,state['profile']);base['run_id']=run_id
                        save(directory/'sources.json',raw);save(directory/'result.json',base)
                        (directory/'report.html').write_text(render_report(base),encoding='utf-8')
                        state['report']={**state['report'],'run_id':run_id};state['report'].pop('ai_status',None)
                elif body.action=='analyze':
                    import os
                    from .ai_analysis import analyze_product
                    state=read(identifier)
                    if not state.get('report'):raise WorkflowError('Сначала соберите материалы.')
                    directory=storage/'projects'/state['id']/'runs'/state['report']['run_id']
                    base=json.loads((directory/'result.json').read_text(encoding='utf-8'))
                    raw=json.loads((directory/'sources.json').read_text(encoding='utf-8'))
                    prepared=product_report(base,state,raw)
                    analysis_dir=directory/'ai_runs'/str(uuid4())
                    value=analyze_product(prepared,raw,os.environ.get('PROXYAPI_KEY'),analysis_dir,progress=progress)
                    save(directory/'product_analysis.json',value)
                    state['report']['ai_status']=value['ai_analysis']['status']
                elif body.action=='import_search':
                    from .search import manual_candidates
                    from stage_4.workflow import queries
                    state=read(identifier)
                    if not state['profile_confirmed']:raise WorkflowError('Сначала подтвердите профиль.')
                    query=queries(state['profile'])[0];candidates=manual_candidates(body.search_text,query)
                    candidates=[c for c in candidates if host(c['url'])!=host(state['url'])]
                    if not candidates:raise WorkflowError('Вставьте хотя бы один публичный HTTPS-адрес из просмотренной выдачи.')
                    search={'query':query,'provider':'manual_browser','status':'ok','candidates':candidates,
                            'collected_at':timestamp(),'api_attempts':0,'provenance':'Пользователь предоставил адреса после просмотра браузера. Не автоматическая выдача API.'}
                    directory=storage/'projects'/state['id']/'search_runs';directory.mkdir(exist_ok=True)
                    search['search_run_id']=str(uuid4());save(directory/(search['search_run_id']+'.json'),search)
                    save(storage/'projects'/state['id']/'search.json',search)
                    state['search']=search
                    state['updated_at']=timestamp();state['events'].append({'action':'import_search','at':state['updated_at']})
                else:
                    state=run_project(action=body.action,website_url=body.website_url,profile=body.profile,
                        competitor_urls=[c.url for c in body.competitors] if body.competitors is not None else None,
                        uploads=body.uploads,max_pages=body.max_pages,project_id=str(identifier) if identifier else None,
                        output_dir=storage/'projects',progress=progress)
                job['project_id']=state['id']
                if body.action=='confirm_profile':
                    progress('Ищем кандидатов по подтверждённому профилю')
                    state=run_project(action='search',project_id=state['id'],output_dir=storage/'projects')
                if body.action in ('confirm_profile','search','import_search'):
                    state['suggestions']=[{'name':c['label'],'url':c['url'],'origin':'Результат из браузера, добавлен пользователем' if c.get('added_by')=='user_provided_search_result' else ('Кандидат официального поиска: '+c['provider'] if c.get('provider') in ('tavily','brave') else 'Кандидат веб-поиска'),'snippet':c.get('snippet','')} for c in state.get('search',{}).get('candidates',[])]+suggest(state)
                    state['competitors_confirmed']=False
                if body.action=='confirm_competitors':
                    names={public_url(c.url.strip()):c.name.strip() for c in body.competitors}
                    for c in state['competitors']:c['name']=names[c['url']]
                save(storage/'projects'/state['id']/'state.json',state)
                job.update(status='succeeded',step='Готово')
            except WorkflowError as error:job.update(status='failed',error=str(error))
            except Exception:job.update(status='failed',error='Не удалось завершить действие. История сохранена; проверьте адрес и повторите.')
            finally:
                job['updated_at']=timestamp();job_save(file,job)
                with guard:active.discard(key)
        def completed(future):
            if future.cancelled() or future.exception():
                job.update(status='failed',error='Задание остановлено при перезапуске.' if future.cancelled() else 'Ошибка сохранения задания: '+type(future.exception()).__name__)
                job_save(file,job)
                with guard:active.discard(key)
        pool.submit(work).add_done_callback(completed)
        return job

    @router.post('/research',status_code=202)
    def start(body:Command):
        if body.action!='start':raise HTTPException(422,'Сначала укажите сайт.')
        return submit(body)

    @router.post('/research/{identifier}',status_code=202)
    def advance(identifier:UUID,body:Command):
        read(identifier)
        if body.action=='start':raise HTTPException(422,'Новый сайт создаётся отдельно.')
        return submit(body,identifier)

    @router.get('/jobs/{identifier}')
    def job(identifier:UUID):
        file=jobs/(str(identifier)+'.json')
        if not file.is_file():raise HTTPException(404,'Задание не найдено.')
        with job_io:return json.loads(file.read_text(encoding='utf-8'))

    @router.get('/research')
    def history():
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((storage/'projects').glob('*/state.json'),key=lambda p:p.stat().st_mtime,reverse=True)]

    @router.get('/research/{identifier}')
    def detail(identifier:UUID):return read(identifier)

    @router.get('/research/{identifier}/result')
    def report(identifier:UUID):
        state=read(identifier)
        if not state.get('report'):raise HTTPException(409,'Результат ещё не готов.')
        file=storage/'projects'/str(identifier)/'runs'/state['report']['run_id']/'result.json'
        analyzed=file.parent/'product_analysis.json'
        if analyzed.is_file():return json.loads(analyzed.read_text(encoding='utf-8'))
        candidates=file.parent/'telegram_candidates.json'
        if candidates.is_file():return json.loads(candidates.read_text(encoding='utf-8'))
        sources=json.loads((file.parent/'sources.json').read_text(encoding='utf-8'))
        return product_report(json.loads(file.read_text(encoding='utf-8')),state,sources)
    api.include_router(router)
