"""Bounded official search adapters. Secrets never enter public state or logs."""
import hashlib
import json
import os
import re
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

import requests

from stage_4.workflow import public_url,timestamp

ENDPOINTS={'tavily':'https://api.tavily.com/search','brave':'https://api.search.brave.com/res/v1/web/search'}
_budget_lock=Lock()


def reserve(env):
    """Conservative attempt budget, single server process; never a billing claim."""
    try:limit=int(env.get('ANALYST_SEARCH_MONTHLY_LIMIT','1000'))
    except ValueError:return 'invalid_configuration'
    if not 0<=limit<=1000:return 'invalid_configuration'
    file=Path(env.get('ANALYST_SEARCH_BUDGET_FILE','var/search_budget.json'))
    month=timestamp()[:7]
    with _budget_lock:
        try:
            current=json.loads(file.read_text(encoding='utf-8')) if file.exists() else {}
            used=current.get('attempts',0) if current.get('month')==month else 0
            if type(used) is not int or used<0:return 'budget_unavailable'
            if used>=limit:return 'budget_exhausted'
            file.parent.mkdir(parents=True,exist_ok=True)
            temporary=file.with_suffix('.tmp');temporary.write_text(json.dumps({'month':month,'attempts':used+1}),encoding='utf-8');temporary.replace(file)
            return None
        except (OSError,ValueError):return 'budget_unavailable'


def normalize(rows,query,provider,key='',own_url='',deduplicate_by_host=True):
    candidates=[];seen=set();own=(urlsplit(own_url).hostname or '').removeprefix('www.')
    for row in rows:
        if not isinstance(row,dict):continue
        target=row.get('url','')
        if not isinstance(target,str) or key and key in target:continue
        try:target=public_url(target)
        except ValueError:continue
        host=(urlsplit(target).hostname or '').removeprefix('www.')
        identity=host if deduplicate_by_host else target
        if host==own or identity in seen:continue
        seen.add(identity)
        clean=lambda text:str(text or '').replace(key,'[redacted]') if key else str(text or '')
        candidates.append({'url':target,'label':clean(row.get('title') or host)[:200],
                           'snippet':clean(row.get('description',row.get('content','')))[:600],
                           'added_by':'script_search','provider':provider,'query':query})
        if len(candidates)==10:break
    return candidates


def official_search(query,own_url='',session=None,settings=None,deduplicate_by_host=True):
    env=os.environ if settings is None else settings
    provider=env.get('ANALYST_SEARCH_PROVIDER','tavily')
    result={'query':query,'provider':provider,'candidates':[],'collected_at':timestamp(),
            'api_attempts':0,'actual_billed_amount':None,'limits':'Поисковые результаты — кандидаты. Соответствие нише подтверждает пользователь.'}
    if provider not in ENDPOINTS:return {**result,'status':'invalid_configuration'}
    key=env.get('TAVILY_API_KEY' if provider=='tavily' else 'BRAVE_SEARCH_API_KEY','')
    if env.get('ANALYST_SEARCH_ENABLED')!='1' or not key:return {**result,'status':'not_configured'}
    budget_error=reserve(env)
    if budget_error:return {**result,'status':budget_error}
    query=query[:400];result.update(query=query,engine_url=ENDPOINTS[provider],api_attempts=1)
    headers={'Accept':'application/json'}
    kwargs={'headers':headers,'timeout':(8,20),'stream':True,'allow_redirects':False}
    if provider=='tavily':
        headers['Authorization']='Bearer '+key
        kwargs['json']={'query':query,'search_depth':'basic','max_results':10,'include_answer':False,
                        'include_raw_content':False,'auto_parameters':False,'include_usage':True}
        method='POST'
    else:
        headers['X-Subscription-Token']=key
        kwargs['params']={'q':query,'count':10,'safesearch':'moderate'};method='GET'
    owned=session is None;session=session or requests.Session()
    try:
        with session.request(method,ENDPOINTS[provider],**kwargs) as response:
            result['http_status']=response.status_code
            failures={401:'authentication_failed',403:'access_denied',429:'rate_limited',432:'quota_exhausted',433:'quota_exhausted'}
            if response.status_code in failures:return {**result,'status':failures[response.status_code]}
            if 300<=response.status_code<400:return {**result,'status':'redirect_refused'}
            if response.status_code>=500:return {**result,'status':'provider_unavailable'}
            if response.status_code!=200:return {**result,'status':'request_rejected'}
            body=bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body)>2_000_000:return {**result,'status':'response_too_large'}
            result['response_sha256']=hashlib.sha256(body).hexdigest()
            try:data=json.loads(body)
            except (ValueError,UnicodeError):return {**result,'status':'invalid_response'}
            if not isinstance(data,dict):return {**result,'status':'invalid_response'}
            web=data.get('web',{})
            rows=data.get('results',[]) if provider=='tavily' else web.get('results',[]) if isinstance(web,dict) else None
            if not isinstance(rows,list):return {**result,'status':'invalid_response'}
            result['candidates']=normalize(rows,query,provider,key,own_url,deduplicate_by_host)
            if isinstance(data.get('usage'),dict):
                credits=data['usage'].get('credits')
                if type(credits) in (int,float):result['reported_credits']=credits
            return {**result,'status':'ok' if result['candidates'] else 'no_candidates'}
    except requests.Timeout:return {**result,'status':'timeout'}
    except requests.RequestException:return {**result,'status':'network_error'}
    finally:
        if owned:session.close()


def manual_candidates(text,query):
    """User pastes addresses after ordinary browser search, including human CAPTCHA."""
    rows=[]
    for line in text.splitlines():
        matches=re.findall(r'https://[^\s<>"\']+',line)
        for url in matches:rows.append({'url':url.rstrip('.,;)'),'title':line.split(url)[0].strip(' \t—-') or urlsplit(url).hostname})
    values=normalize(rows,query,'manual_browser')
    for row in values:row['added_by']='user_provided_search_result'
    return values
