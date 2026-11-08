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
        tone=[{**e,'category':'tone'} for e in item['evidence'] if re.search(r'\bмы\b|\bвы\b|\bваш|\byou\b|\bwe\b',e['quote'],re.I)][:4]
        item['evidence']+=tone;item['dimensions']={**original['dimensions'],'tone':len(tone)}
        item['name']=state['profile']['company_name'] if item['role']=='own' else names.get(item['url']) or item['name']
        item['gaps']=[label+': недостаточно данных' for key,label in LABELS.items() if not item['dimensions'].get(key)]
        item['gaps'].append('Визуал: требуется просмотр реальных снимков')
        companies.append(item)
    own=next(c for c in companies if c['role']=='own');rivals=[c for c in companies if c['role']!='own']
    actions=[]
    def add(kind,title,action,evidence,check):
        actions.append({'kind':kind,'title':title,'action':action,'evidence':evidence,
                        'status':'Гипотеза для проверки','success_check':check})
    def proof(c,key):
        return [{**e,'company':c['name'],'company_url':c['url']} for e in c['evidence'] if e['category']==key][:1]
    absolute=next((e for e in own['evidence'] if re.search(r'без риска отказа|100\s*%\s*одобр|guaranteed approval|no risk',e['quote'],re.I)),None)
    if absolute:
        add('check','Проверить абсолютное обещание в собственной подаче',
            'В своей цитате есть обещание результата без риска или полного одобрения. Проверьте подтверждения и условия. Если доказательств нет, замените абсолютное обещание описанием процесса, границ ответственности и факторов решения; проверьте формулировку у ответственного специалиста.',
            [{**absolute,'company':own['name'],'company_url':own['url']}],
            'Формулировка подтверждена источниками и не создаёт ожидания гарантированного решения третьей стороны.')
    for key,label in LABELS.items():
        ours=proof(own,key);others=[(c,proof(c,key)) for c in rivals if proof(c,key)]
        if ours and not re.search(r'без риска отказа|100\s*%\s*одобр|guaranteed approval|no risk',ours[0]['quote'],re.I):
            add('keep','Сохранить и сделать заметнее: '+label.lower(),
                'Проверьте, что предложение из цитаты актуально, понятно клиенту и заметно на пути к обращению. Сохраните подтверждённую формулировку и протестируйте её размещение.',ours,
                'Пять потенциальных клиентов находят и правильно пересказывают предложение без подсказки.')
        if others:
            rival,evidence=others[0]
            action={
                'assortment':'Сопоставьте предложение из цитаты со своей линейкой: состав, аудитория, результат, ограничения. Если есть спрос и компетенции, подготовьте отдельную карточку или пакет; не копируйте обещания без проверки.',
                'pricing':'Проверьте формат объяснения цены: что входит, что оплачивается отдельно, срок и условия. Протестируйте такой же уровень прозрачности на своей странице; суммы разных пакетов не ранжируйте.',
                'positioning':'Разберите аргумент из цитаты. Подберите собственное проверяемое доказательство — кейс, процесс или подтверждённый опыт — и протестируйте его в первом экране.',
                'conversion':'Разберите путь обращения в цитате: первый шаг, ожидаемый результат и срок ответа. Протестируйте понятный аналог на своей странице и измерьте долю завершённых обращений.',
                'editorial':'Используйте тему или формат материала как повод для интервью с аудиторией. Подготовьте собственный практический материал, проверьте актуальность и добавьте следующий шаг к обращению.',
                'tone':'Разберите обращение и обещание в цитате: кто говорит, какую задачу клиента называет, что обещает. Перепишите собственный текст в подходящем аудитории тоне и проверьте понимание; не переносите чужие гарантии.'}[key]
            add('adapt','Что можно адаптировать у '+rival['name']+': '+label.lower(),action,evidence+ours,
                'Сначала подтвердить смысл цитаты и потребность аудитории; затем сравнить тестовую версию с текущей.')
        if not ours:
            add('check','Проверить свою подачу: '+label.lower(),
                'В собранной выборке своей компании нет достаточного основания для оценки. Проверьте нужную страницу и добавьте её текст. Только после проверки решайте, требуется ли исправление.',[],
                'Есть актуальный источник и подтверждение того, что клиент понимает предложение.')
    missing=[c['name'] for c in companies if not c['dimensions'].get('pricing')]
    if missing:
        add('market','Возможность отстройки: понятность условий',
            'Проведите одинаковую проверку состава, срока, итоговой цены и исключений у всех компаний. Если подтвердится общая непрозрачность, протестируйте полное объяснение своих условий. Сейчас недостаток цитат не доказывает слабость рынка.',[],
            'Сопоставимые пакеты проверены по источникам; клиенты верно понимают итоговые условия.')
    return {'run_id':result['run_id'],'generated_at':result['generated_at'],'profile':result['profile'],
            'companies':companies,'dimensions':LABELS,'recommendations':actions,'limits':result['limits'],
            'method':'Сравнение сохранённых цитат и правила подготовки проверяемых действий; без нового LLM-вызова.',
            'new_llm_calls':0}


class Competitor(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=200)
    url:str=Field(min_length=8,max_length=2000)


class Command(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:str=Field(pattern='^(start|confirm_profile|confirm_competitors|collect)$')
    website_url:str=Field(default='',max_length=2000)
    profile:dict[str,str]|None=None
    competitors:list[Competitor]|None=Field(default=None,max_length=20)
    uploads:dict[str,dict[str,str]]|None=None
    max_pages:int=Field(default=4,ge=1,le=8)


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
                state=run_project(action=body.action,website_url=body.website_url,profile=body.profile,
                    competitor_urls=[c.url for c in body.competitors] if body.competitors is not None else None,
                    uploads=body.uploads,max_pages=body.max_pages,project_id=str(identifier) if identifier else None,
                    output_dir=storage/'projects',progress=progress)
                job['project_id']=state['id']
                if body.action=='confirm_profile':
                    progress('Ищем кандидатов по подтверждённому профилю')
                    state=run_project(action='search',project_id=state['id'],output_dir=storage/'projects')
                    state['suggestions']=suggest(state)+[{'name':c['label'],'url':c['url'],'origin':'Новый поисковый кандидат'} for c in state.get('search',{}).get('candidates',[])]
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
        sources=json.loads((file.parent/'sources.json').read_text(encoding='utf-8'))
        return product_report(json.loads(file.read_text(encoding='utf-8')),state,sources)
    api.include_router(router)
