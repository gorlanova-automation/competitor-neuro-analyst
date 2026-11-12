"""One public entry point for CLI, Colab and the local web application.

No paid calls. Source quotes and lexical observations are separate from claims
about effectiveness. All network access is public HTTPS with bounded collection.
"""
import hashlib
import html
import ipaddress
import json
import re
import socket
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit, urldefrag,urlunsplit
from uuid import UUID, uuid4

import requests
from bs4 import BeautifulSoup

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'stage_3/code'))
from resilient_fetch import fetch, UA


class WorkflowError(ValueError):pass


def timestamp():return datetime.now(timezone.utc).isoformat()
def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
def save(path,data):
    temporary=path.with_suffix('.tmp')
    temporary.write_bytes((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    temporary.replace(path)


def public_url(url,resolve=False):
    """Reject private destinations, including every redirect, for user URLs."""
    parts=urlsplit(url)
    if (parts.scheme!='https' or not parts.hostname or parts.username or parts.password
            or parts.port not in (None,443) or parts.hostname.lower() in ('localhost','localhost.localdomain')
            or parts.hostname.lower().endswith(('.localhost','.local','.internal'))):
        raise WorkflowError('Нужен публичный HTTPS-адрес без логина и нестандартного порта.')
    try:addresses=[ipaddress.ip_address(parts.hostname)]
    except ValueError:
        addresses=[ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(parts.hostname,443,type=socket.SOCK_STREAM)] if resolve else []
    if any(not address.is_global for address in addresses):raise WorkflowError('Локальные и служебные адреса не загружаются.')
    return urlunsplit(('https',parts.netloc.lower(),parts.path or '/',parts.query,''))


class PublicSession(requests.Session):
    def get(self,url,**kwargs):
        kwargs.pop('allow_redirects',None)
        for _ in range(6):
            try:public_url(url,resolve=True)
            except socket.gaierror as exc:raise requests.ConnectionError('name resolution failed') from exc
            except WorkflowError as exc:raise requests.ConnectionError('destination blocked') from exc
            response=super().get(url,allow_redirects=False,**kwargs)
            if response.status_code not in (301,302,303,307,308):return response
            location=response.headers.get('Location')
            response.close()
            if not location:raise requests.ConnectionError('redirect without location')
            url=urljoin(url,location)
        raise requests.TooManyRedirects('redirect limit')


def new_session():
    session=PublicSession();session.headers['User-Agent']=UA
    return session


def draft(source):
    title=source.get('title') or urlsplit(source['url']).hostname
    return {'company_name':re.split(r'[|·—]',title)[0].strip(),
            'summary':source.get('description') or source['text'][:350],
            'offering':source.get('headings',[])[:12],
            'market_scope':'','search_terms':' '.join(source.get('headings',[])[:2])[:180] or source.get('description') or title,
            'source_sha256':source['sha256_text'],'method':'metadata_draft_requires_confirmation'}


def queries(profile):
    terms=profile.get('search_terms') or profile['company_name']
    scope=profile.get('market_scope','')
    words=re.findall(r'[\w-]+',terms+' '+scope,flags=re.UNICODE)
    unique=[];seen=set()
    for word in words:
        if word.casefold() not in seen:unique.append(word);seen.add(word.casefold())
    base=' '.join(unique[:14])
    return [base+' компании',base+' альтернативы',base+' услуги цены']


def capture_source(url,session,policies,uploads):
    url=public_url(url)
    if url in uploads:
        upload=uploads[url];text=upload.get('text','').strip()
        if not 200<=len(text)<=1_000_000:raise WorkflowError('Загруженный текст должен содержать от 200 до 1 000 000 символов.')
        return {'url':url,'final_url':url,'status':'ok','text':text,'sha256_text':digest(text),
                'title':upload.get('title') or urlsplit(url).hostname,'description':upload.get('description',''),
                'headings':[],'links':[],'collected_at':timestamp(),'method':'user_uploaded_text',
                'provenance_note':'Текст предоставлен пользователем; HTTP-сбор этого содержимого не выполнялся.'}
    return fetch(session,url,policies)


def discover(profile):
    """Optional public search; a failed engine never becomes invented candidates."""
    query=queries(profile)[0]
    if os.environ.get('ANALYST_SEARCH_PROVIDER','tavily')!='duckduckgo':
        from app.search import official_search
        return official_search(query)
    with new_session() as session:
        source=fetch(session,'https://html.duckduckgo.com/html/?q='+quote(query),{})
    candidates=[];seen=set()
    if source['status']=='ok':
        for link in source.get('links',[]):
            parts=urlsplit(link['url']);target=parse_qs(parts.query).get('uddg',[link['url']])[0]
            if 'duckduckgo.com' in (urlsplit(target).hostname or ''):continue
            try:target=public_url(target)
            except ValueError:continue
            if target not in seen:
                seen.add(target);candidates.append({'url':target,'label':link['label'],'added_by':'script_search','query':query})
            if len(candidates)==10:break
    status=source['status'] if source['status']!='ok' or candidates else 'no_candidates'
    return {'query':query,'engine_url':source['url'],'status':status,'candidates':candidates,'source':source,
            'collected_at':timestamp(),'limits':'Результаты поиска — кандидаты, их соответствие нише подтверждает пользователь.'}


def collect_site(url,session,uploads,max_pages=4):
    policies={};queue=[url]+[u for u in uploads if u!=url and urlsplit(u).hostname==urlsplit(url).hostname];seen=set();sources=[]
    while queue and len(sources)<max_pages*3 and sum(p['status']=='ok' for p in sources)<max_pages:
        target=queue.pop(0)
        if target in seen:continue
        seen.add(target)
        try:source=capture_source(target,session,policies,uploads)
        except (requests.RequestException,ValueError):
            source={'url':target,'status':'collection_failed','next_action':'Проверьте адрес или загрузите текст страницы.','collected_at':timestamp()}
        sources.append(source)
        if source['status']!='ok':
            if source.get('failure_kind')=='dns_error' and urlsplit(target).netloc.startswith('www.'):
                queue.append(target.replace('https://www.','https://',1))
            continue
        for link in source.get('links',[]):
            candidate=link['url']
            if urlsplit(candidate).hostname!=urlsplit(source.get('final_url',target)).hostname:continue
            if re.search(r'privacy|cookie|terms|login|\.pdf',candidate,re.I):continue
            if re.search(r'service|услуг|pricing|цены|тариф|product|продукт|about|blog|стать|news',candidate+' '+link['label'],re.I):
                if candidate not in seen and candidate not in queue:queue.append(candidate)
    return sources


def observations(sources):
    rows=[]
    patterns={
        'assortment':r'услуг|предлага|сопровожд|продукт|service|product|solution|offer',
        'pricing':r'€|\$|₽|\bEUR\b|\bUSD\b|цена|стоимость|pricing|price|тариф',
        'positioning':r'помога|помож|эксперт|опыт|гарант|expert|experience|help|guarantee',
        'conversion':r'консультац|заявк|свяж|запис|consultation|contact|book|trial|demo',
        'editorial':r'блог|стать|новост|blog|article|news|guide|руководств',
    }
    for source in sources:
        if source['status']!='ok':continue
        for category,pattern in patterns.items():
            blocks=[b for b in source.get('text_blocks',[]) if re.search(pattern,b,re.I) and b in source['text']]
            if blocks:
                for excerpt in blocks[:8]:
                    rows.append({'category':category,'quote':excerpt,'url':source.get('final_url',source['url']),
                                 'source_sha256':source['sha256_text'],'source_method':source.get('method'),
                                 'collected_at':source.get('collected_at'),'method':'content_block_requires_review'})
                continue
            if source.get('text_blocks'):continue
            matches=list(re.finditer(pattern,source['text'],re.I))[:5]
            for match in matches:
                excerpt=source['text'][max(0,match.start()-60):min(len(source['text']),match.end()+180)]
                rows.append({'category':category,'quote':excerpt,'url':source.get('final_url',source['url']),
                             'source_sha256':source['sha256_text'],'source_method':source.get('method'),
                             'collected_at':source.get('collected_at'),'method':'lexical_signal_requires_review'})
    return rows


def sample_publications(sources,session):
    """Collect actual public Telegram messages, not a count of social links."""
    feeds={};publications=[];seen=set()
    for source in sources:
        if source['status']!='ok':continue
        for link in source.get('links',[]):
            if (urlsplit(link['url']).hostname or '').removeprefix('www.')!='t.me':continue
            path=urlsplit(link['url']).path.strip('/').split('/')
            name=path[1] if len(path)>1 and path[0]=='s' else path[0]
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{3,}',name) or name.lower().endswith('bot') or name in seen:continue
            seen.add(name)
            if len(feeds)>=2:break
            url='https://t.me/s/'+name
            try:page=fetch(session,url,{},include_html=True)
            except (requests.RequestException,ValueError):page={'status':'collection_failed'}
            row={'url':url,'found_on':source.get('final_url',source['url']),'status':page['status'],'posts':0}
            if page['status']=='ok':
                soup=BeautifulSoup(page['html'],'html.parser')
                for item in soup.select('.tgme_widget_message[data-post]')[-8:]:
                    text=item.select_one('.tgme_widget_message_text');date=item.select_one('time[datetime]')
                    body=text.get_text(' ',strip=True) if text else ''
                    if not body or not date:continue
                    post_url='https://t.me/'+item['data-post']
                    publications.append({'url':post_url,'final_url':post_url,'status':'ok','title':'Telegram: '+name,
                        'description':'','headings':[],'text':body,'sha256_text':digest(body),'links':[],
                        'collected_at':timestamp(),'published_at':date['datetime'],'method':'public_telegram_dom_message',
                        'source_kind':'publication','found_on':source.get('final_url',source['url'])})
                    row['posts']+=1
                row['status']='sample_collected' if row['posts'] else 'no_public_messages_observed'
            feeds[url]=row
    return publications,list(feeds.values())


def compare(companies,profile):
    dimensions=['assortment','pricing','positioning','conversion','editorial']
    result=[]
    for company in companies:
        sources=company['sources'];evidence=observations(sources);channels={}
        for source in sources:
            if source['status']!='ok':continue
            for link in source.get('links',[]):
                hostname=(urlsplit(link['url']).hostname or '').removeprefix('www.')
                if any(hostname==h or hostname.endswith('.'+h) for h in ['t.me','instagram.com','facebook.com','youtube.com','linkedin.com','tiktok.com','vk.com']):
                    channels[link['url']]={'url':link['url'],'found_on':source.get('final_url',source['url']),
                                         'status':'link_found_content_not_collected'}
        result.append({'url':company['url'],'name':next((s.get('title') for s in sources if s['status']=='ok' and s.get('title')),company['url']),
                       'role':company['role'],'added_by':company.get('added_by','own_site'),
                       'pages_ok':sum(s['status']=='ok' and s.get('source_kind')!='publication' for s in sources),
                       'evidence':evidence,'dimensions':{d:sum(e['category']==d for e in evidence) for d in dimensions},
                       'channels':list(channels.values()),'publication_samples':company.get('publication_samples',[]),
                       'posts_collected':sum(s.get('source_kind')=='publication' for s in sources),
                       'visual_status':'requires_screenshot_review',
                       'failures':[{k:s.get(k) for k in ('url','status','failure_kind','next_action')} for s in sources if s['status']!='ok']})
    return {'generated_at':timestamp(),'profile':profile,'companies':result,'new_llm_calls':0,'api_cost':0,
            'analysis_method':'Deterministic excerpt extraction; not a semantic model analysis.',
            'limits':['Упоминание не доказывает продажу услуги. Отсутствие цитаты означает недостаток данных.',
                      'Ссылки на соцсети не означают прочитанные публикации. Эффективность продвижения не измерена.',
                      'Визуал требует просмотра снимков; цвета и качество дизайна по тексту не определяются.',
                      'Цены без состава пакета, даты и условий нельзя считать сопоставимыми.'],
            'hypotheses':[]}


def render_report(result):
    esc=lambda value:html.escape(str(value),quote=True)
    parts=['<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Исследование конкурентов</title>',
           '<style>body{font:16px/1.65 system-ui;max-width:1050px;margin:32px auto;padding:0 24px;color:#19392f}article{border-top:1px solid #ccc;padding:24px 0}blockquote{border-left:3px solid #548878;padding-left:18px}small{color:#63716c}a{color:#176758}</style>',
           '<h1>Исследование конкурентов</h1><p>'+esc(result['profile']['company_name'])+'</p>',
           '<p>Автоматическая выборка цитат. Смысловые выводы и визуал требуют проверки.</p><h2>Ограничения</h2><ul>']
    parts.extend('<li>'+esc(limit)+'</li>' for limit in result['limits']);parts.append('</ul>')
    if result.get('semantic'):
        semantic=result['semantic'];reviewed=semantic.get('status')=='human_review_recorded'
        parts.append('<h2>'+('Выводы после проверки' if reviewed else 'Смысловой анализ модели — черновик для проверки')+'</h2>')
        if reviewed:parts.append('<p>Автор проверки: '+esc(semantic['reviewer'])+'. Принято выводов: '+str(semantic['accepted_findings'])+'. Это решения указанного автора, а не автоматическая оценка модели.</p>')
        by_id={s['source_id']:s for s in semantic['sources']}
        labels={'assortment':'Ассортимент','audience':'Аудитория','positioning':'Позиционирование','promotion':'Продвижение','content':'Публикации','tone':'Тон','pricing':'Цены и условия'}
        for index,finding in enumerate(semantic['findings']):
            if finding.get('review_status')=='reject':continue
            source=by_id[finding['source_id']]
            parts.append('<h3>F'+str(index)+' · '+esc(labels.get(finding['category'],finding['category']))+'</h3><p>'+esc(finding['summary'])+'</p><blockquote>'+esc(finding['quote'])+'</blockquote><a href="'+esc(source['url'])+'">Источник</a>')
        parts.append('<h3>Гипотезы для проверки</h3>')
        for hypothesis in semantic['hypotheses']:
            if hypothesis.get('review_status')!='reject':parts.append('<p>'+esc(hypothesis['action'])+' · основания: '+esc(hypothesis['evidence_indexes'])+'</p>')
        for missing in semantic['missing_evidence']:parts.append('<p>Не хватает данных: '+esc(missing)+'</p>')
    for company in result['companies']:
        parts.append('<article><h2>'+esc(company.get('name',company['url']))+'</h2><p>'+('Своя компания' if company['role']=='own' else 'Конкурент')+' · '+esc(company['url'])+'</p><p>Получено страниц сайта: '+str(company['pages_ok'])+'</p>')
        if company.get('added_by')=='user_added':parts.append('<p>Конкурент добавлен пользователем.</p>')
        elif company.get('added_by')=='script_search_confirmed':parts.append('<p>Кандидат найден скриптом и подтверждён пользователем.</p>')
        for failure in company['failures']:parts.append('<p>Не получено: '+esc(failure['url'])+' — '+esc(failure['status'])+'</p>')
        categories={'assortment':'Ассортимент и предложение','pricing':'Цены и условия','positioning':'Позиционирование и аргументы','conversion':'Переходы к обращению','editorial':'Редакционные материалы'}
        for category,label in categories.items():
            evidence_rows=[e for e in company['evidence'] if e['category']==category]
            parts.append('<details'+(' open' if category=='assortment' else '')+'><summary>'+label+' · цитат: '+str(len(evidence_rows))+'</summary>')
            if not evidence_rows:parts.append('<p>В полученной выборке не выделено подходящих цитат. Это не означает отсутствия предложения.</p>')
            for evidence in evidence_rows:
                origin='Текст предоставлен пользователем' if evidence.get('source_method')=='user_uploaded_text' else 'Сохранённый результат сбора'
                parts.append('<blockquote>'+esc(evidence['quote'])+'</blockquote><a href="'+esc(evidence['url'])+'" rel="noopener noreferrer">Открыть источник</a><p><small>'+origin+' · '+esc(evidence.get('collected_at',''))+'</small></p><details><summary>Проверить происхождение цитаты</summary><small>SHA256 сохранённого текста: '+esc(evidence['source_sha256'])+'</small></details>')
            parts.append('</details>')
        if company['channels']:parts.append('<h3>Найденные площадки (содержимое не прочитано)</h3>')
        for channel in company['channels']:parts.append('<p><a href="'+esc(channel['url'])+'">'+esc(channel['url'])+'</a></p>')
        parts.append('<p>Реально получено публикаций: '+str(company.get('posts_collected',0))+'. Ограниченное превью не позволяет оценить частоту.</p>')
        for sample in company.get('publication_samples',[]):parts.append('<p>'+esc(sample['url'])+' — '+esc(sample['status'])+'</p>')
        parts.append('</article>')
    parts.append('</html>');return '\n'.join(parts)


def run_project(website_url='',profile=None,competitor_urls=None,output_dir='var/projects',project_id=None,
                action='start',uploads=None,max_pages=4,api_key=None,model='openai/gpt-6-luna',review=None,progress=None):
    """Single orchestrator. Every action receives its inputs explicitly.

    start → confirm_profile → search (optional) → confirm_competitors → collect.
    Uploaded texts are bound to URLs and explicitly labelled as user supplied.
    """
    uploads={public_url(url):value for url,value in (uploads or {}).items()}
    if not 1<=max_pages<=8:raise WorkflowError('Лимит страниц должен быть от 1 до 8.')
    if action not in ('start','confirm_profile','search','confirm_competitors','collect','read','analyze','review_analysis'):
        raise WorkflowError('Неизвестное действие.')
    if project_id is not None:
        try:project_id=str(UUID(str(project_id)))
        except ValueError:raise WorkflowError('Некорректный номер проекта.') from None
    elif action!='start':raise WorkflowError('Сначала создайте проект.')
    root=Path(output_dir);root.mkdir(parents=True,exist_ok=True)
    identifier=project_id or str(uuid4());folder=root/identifier
    if action=='start':
        if project_id:raise WorkflowError('Для нового проекта не задавайте его номер.')
        website_url=public_url(website_url);folder.mkdir(exist_ok=False)
        with new_session() as session:
            source=capture_source(website_url,session,{},uploads or {})
        save(folder/'own_source.json',source)
        state={'id':identifier,'url':website_url,'created_at':timestamp(),'status':'profile_draft' if source['status']=='ok' else 'source_unavailable',
               'profile':draft(source) if source['status']=='ok' else None,'source_status':source['status'],'source_method':source.get('method'),
               'next_action':None if source['status']=='ok' else source.get('next_action'),'competitors':[],
               'profile_confirmed':False,'competitors_confirmed':False,'events':[]}
    else:
        if not (folder/'state.json').is_file():raise WorkflowError('Проект не найден.')
        state=json.loads((folder/'state.json').read_text(encoding='utf-8'))
        if action=='read':return state
        if action=='confirm_profile':
            if state['profile'] is None:raise WorkflowError('Сначала получите или загрузите исходную страницу.')
            if not profile or any(not str(profile.get(k,'')).strip() for k in ('company_name','summary','market_scope','search_terms')):
                raise WorkflowError('Заполните название, описание, рынок и поисковые слова.')
            state['profile']={**state['profile'],**{k:str(profile[k]).strip() for k in ('company_name','summary','market_scope','search_terms')}}
            state.update(profile_confirmed=True,competitors_confirmed=False,status='awaiting_competitors',search_queries=queries(state['profile']))
            state.pop('report',None)
        elif action=='search':
            if not state['profile_confirmed']:raise WorkflowError('Подтвердите профиль перед поиском.')
            search=discover(state['profile'])
            own_host=(urlsplit(state['url']).hostname or '').removeprefix('www.')
            search['candidates']=[c for c in search.get('candidates',[]) if (urlsplit(c['url']).hostname or '').removeprefix('www.')!=own_host]
            history=folder/'search_runs';history.mkdir(exist_ok=True)
            search['search_run_id']=str(uuid4());save(history/(search['search_run_id']+'.json'),search)
            save(folder/'search.json',search);state['search']=search
        elif action=='confirm_competitors':
            if not state['profile_confirmed']:raise WorkflowError('Сначала подтвердите профиль.')
            if not competitor_urls or len(competitor_urls)>20:raise WorkflowError('Укажите от 1 до 20 конкурентов.')
            competitors=list(dict.fromkeys(public_url(url.strip()) for url in competitor_urls))
            own_host=(urlsplit(state['url']).hostname or '').removeprefix('www.')
            if any((urlsplit(u).hostname or '').removeprefix('www.')==own_host for u in competitors):
                raise WorkflowError('Собственный сайт нельзя добавить как конкурента.')
            scripted={c['url'] for c in state.get('search',{}).get('candidates',[]) if c.get('added_by')=='script_search'}
            state['competitors']=[{'url':u,'added_by':'script_search_confirmed' if u in scripted else 'user_added'} for u in competitors]
            state.update(competitors_confirmed=True,status='ready_to_collect');state.pop('report',None)
        elif action=='review_analysis':
            from stage_4.review import apply_review
            if not state.get('report'):raise WorkflowError('Сначала получите отчёт.')
            previous=folder/'runs'/state['report']['run_id']
            source_bytes=(previous/'result.json').read_bytes()
            result=json.loads(source_bytes)
            companies=json.loads((previous/'sources.json').read_text(encoding='utf-8'))
            result=apply_review(result,review,hashlib.sha256(source_bytes).hexdigest(),companies)
            run_id=str(uuid4());run_folder=folder/'runs'/run_id;run_folder.mkdir(parents=True)
            result.update(run_id=run_id,new_llm_calls=0,generated_at=timestamp())
            save(run_folder/'result.json',result);save(run_folder/'sources.json',companies);save(run_folder/'review.json',review)
            (run_folder/'report.html').write_bytes(render_report(result).encode('utf-8'))
            state['report']={**state['report'],'run_id':run_id,'new_llm_calls':0,'semantic_status':result['semantic']['status'],
                             'accepted_findings':result['semantic']['accepted_findings'],'reviewer':result['semantic']['reviewer']}
        elif action=='analyze':
            from stage_4.semantic import analyze
            if not state.get('report'):raise WorkflowError('Сначала соберите данные.')
            previous=folder/'runs'/state['report']['run_id']
            companies=json.loads((previous/'sources.json').read_text(encoding='utf-8'))
            result=json.loads((previous/'result.json').read_text(encoding='utf-8'))
            run_id=str(uuid4());run_folder=folder/'runs'/run_id;run_folder.mkdir(parents=True)
            try:semantic=analyze(companies,state['profile'],api_key,run_folder/'model',model)
            except WorkflowError:
                attempted=(run_folder/'model/request.json').is_file()
                state['last_model_attempt']={'run_id':run_id,'status':'quarantined','request_prepared':attempted,
                                             'actual_billed_amount':None,'at':timestamp()}
                state['events'].append({'action':'analyze_failed','at':timestamp(),'run_id':run_id})
                save(folder/'state.json',state)
                raise
            result.update(semantic=semantic,run_id=run_id,new_llm_calls=1,api_cost=None,
                          analysis_method='Текстовая выборка и отдельно выполненный модельный черновик; требуется проверка смысла.')
            save(run_folder/'sources.json',companies);save(run_folder/'result.json',result)
            (run_folder/'report.html').write_bytes(render_report(result).encode('utf-8'))
            state['report']={**state['report'],'run_id':run_id,'new_llm_calls':1,'api_cost':None,'semantic_status':semantic['status']}
        elif action=='collect':
            if not state['profile_confirmed'] or not state['competitors_confirmed']:raise WorkflowError('Подтвердите профиль и конкурентов.')
            source=json.loads((folder/'own_source.json').read_text(encoding='utf-8'))
            if digest(source['text'])!=state['profile']['source_sha256']:raise WorkflowError('Источник изменился; создайте новый проект.')
            run_id=str(uuid4());run_folder=folder/'runs'/run_id;run_folder.mkdir(parents=True)
            companies=[]
            with new_session() as session:
                if progress:progress('Собираем страницы своей компании')
                own=collect_site(state['url'],session,uploads or {},max_pages)
                # Use the confirmed snapshot if the live page changed or is unavailable.
                for fresh in own:
                    if fresh.get('sha256_text')==source['sha256_text'] and fresh.get('text_blocks'):
                        source={**source,'text_blocks':fresh['text_blocks']}
                companies.append({'url':state['url'],'role':'own','sources':[source]+[s for s in own if s.get('sha256_text')!=source['sha256_text']]})
                for competitor in state['competitors']:
                    if progress:progress('Собираем '+(competitor.get('name') or competitor['url']))
                    companies.append({**competitor,'role':'competitor','sources':collect_site(competitor['url'],session,uploads or {},max_pages)})
                for company in companies:
                    if progress:progress('Проверяем открытые публикации: '+company['url'])
                    posts,samples=sample_publications(company['sources'],session)
                    company['sources'].extend(posts);company['publication_samples']=samples
            save(run_folder/'sources.json',companies)
            result=compare(companies,state['profile']);result['run_id']=run_id
            save(run_folder/'result.json',result)
            (run_folder/'report.html').write_bytes(render_report(result).encode('utf-8'))
            failed=sum(c['pages_ok']==0 for c in result['companies'])
            state.update(status='report_partial' if failed else 'report_ready',report={'run_id':run_id,'companies':len(companies),
                         'companies_without_content':failed,'evidence':sum(len(c['evidence']) for c in result['companies']),
                         'new_llm_calls':0,'api_cost':0})
    state['updated_at']=timestamp();state['events'].append({'action':action,'at':state['updated_at']})
    save(folder/'state.json',state)
    return state
