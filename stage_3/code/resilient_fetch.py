"""Bounded public HTTP collection with typed failures and an audit trail."""
import hashlib
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

UA='CompetitorResearchBot/1.0'
MAX_BYTES=4_000_000


def utc():return datetime.now(timezone.utc).isoformat()


def error_kind(exc):
    text=str(exc).lower()
    if isinstance(exc,requests.exceptions.SSLError):return 'tls_error'
    if isinstance(exc,requests.exceptions.ProxyError):return 'proxy_error'
    if isinstance(exc,requests.exceptions.Timeout):return 'timeout'
    if re.search(r'getaddrinfo|name.?resolution|nameresolution|name or service not known|11001|nodename',text):return 'dns_error'
    return 'connection_error'


def request(session,url,attempts=2,limit=MAX_BYTES,sleep=time.sleep):
    log=[]
    for number in range(1,attempts+1):
        try:
            with session.get(url,timeout=(8,18),stream=True) as response:
                row={'attempt':number,'http_status':response.status_code,'final_url':response.url}
                if response.status_code in (429,500,502,503,504):
                    row['outcome']='rate_limited' if response.status_code==429 else 'server_error';log.append(row)
                    delay=response.headers.get('Retry-After','1')
                    if number<attempts and delay.isdigit() and int(delay)<=2:
                        sleep(max(1,int(delay)));continue
                    return None,{'status':row['outcome'],'attempts':log,'next_action':'retry_later'}
                if response.status_code>=400:
                    row['outcome']='http_error';log.append(row)
                    return None,{'status':'http_error','http_status':response.status_code,'attempts':log,
                                 'next_action':'browser_review' if response.status_code in (401,403) else 'check_source_url'}
                body=bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body)>limit:
                        row['outcome']='size_limit';log.append(row)
                        return None,{'status':'size_limit','attempts':log,'next_action':'review_content_size'}
                row['outcome']='received';log.append(row)
                return {'body':bytes(body),'url':response.url,'http_status':response.status_code,
                        'content_type':response.headers.get('Content-Type',''),'encoding':response.encoding}, {'attempts':log}
        except requests.RequestException as exc:
            kind=error_kind(exc)
            log.append({'attempt':number,'outcome':kind,'error_type':type(exc).__name__})
            # Do not repeat permanent DNS/TLS/configuration errors as transient failures.
            if kind in ('dns_error','tls_error','proxy_error') or number==attempts:
                return None,{'status':kind,'attempts':log,'next_action':
                    {'dns_error':'check_domain_and_canonical_host','tls_error':'site_certificate_review',
                     'proxy_error':'check_network_configuration'}.get(kind,'browser_review')}
            sleep(1)


def fetch(session,url,policies,include_html=False):
    parts=urlsplit(url)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:
        return {'url':url,'status':'invalid_url','collected_at':utc(),'next_action':'correct_https_url','attempts':[]}
    base=parts.scheme+'://'+parts.netloc
    result={'url':url,'collected_at':utc(),'method':'requests_beautifulsoup_resilient_v2','robots_cached':base in policies}
    if base not in policies:
        response,details=request(session,base+'/robots.txt',limit=512000)
        if response and re.search(br'<html|<!doctype|captcha',response['body'][:2048],re.I):
            policies[base]={'status':'unavailable','failure':{'status':'robots_invalid_response',
                'attempts':details['attempts'],'next_action':'browser_review'},'attempts':details['attempts']}
        elif response:
            parser=RobotFileParser();parser.parse(response['body'].decode('utf-8',errors='replace').splitlines())
            policies[base]={'status':'parsed','parser':parser,'attempts':details['attempts']}
        elif details.get('http_status') in (404,410):policies[base]={'status':'not_found','attempts':details['attempts']}
        else:policies[base]={'status':'unavailable','failure':details,'attempts':details['attempts']}
    policy=policies[base]
    result['robots']={k:v for k,v in policy.items() if k!='parser'}
    if policy['status']=='unavailable':
        failure=policy['failure'];return {**result,'status':'robots_unavailable',
            'failure_kind':failure['status'],'attempts':failure['attempts'],'next_action':failure['next_action']}
    if policy.get('parser') and not policy['parser'].can_fetch(UA,url):
        return {**result,'status':'robots_disallowed','attempts':[],'next_action':'manual_source_review_no_automated_fetch'}
    response,details=request(session,url)
    if not response:return {**result,**details}
    result.update(final_url=response['url'],http_status=response['http_status'],attempts=details['attempts'])
    if 'html' not in response['content_type'].lower():return {**result,'status':'unsupported_content','next_action':'use_format_adapter'}
    # Let BeautifulSoup honour the actual document encoding, including HTML meta.
    soup=BeautifulSoup(response['body'],'html.parser')
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    meta=soup.select_one('meta[name="description"]')
    description=meta.get('content','') if meta else ''
    headings=[h.get_text(' ',strip=True) for h in soup.select('h1,h2,h3')]
    links=[{'url':urljoin(response['url'],a['href']).split('#')[0],'label':a.get_text(' ',strip=True)[:180]}
           for a in soup.select('a[href]') if urljoin(response['url'],a['href']).startswith('https://')]
    images=[{'url':urljoin(response['url'],i.get('src','')),'alt':i.get('alt','')[:200]} for i in soup.select('img[src]')][:25]
    videos=len(soup.select('video,iframe[src*="youtube"]'))
    for node in soup(['script','style','noscript','template','svg']):node.decompose()
    text=re.sub(r'\s+',' ',soup.get_text(' ',strip=True)).strip()
    status='ok';action=None
    if re.search(r'/accounts/login|/login(?:[/?]|$)|consent\.',response['url'],re.I):status='login_required';action='browser_review'
    elif re.search(r'checking your browser|just a moment|verify you are human|captcha|complete the following challenge|select all squares|unfortunately,? bots',title+' '+text[:700],re.I):status='challenge_page';action='browser_review'
    elif len(text)<200:status='render_required';action='browser_review'
    page={**result,'status':status,'title':title,'description':description,'headings':headings,'text':text,
        'sha256_text':hashlib.sha256(text.encode()).hexdigest(),'links':links,'image_metadata':images,
        'video_elements':videos,'next_action':action,'quality':'text_received_not_semantically_verified' if status=='ok' else 'not_research_content'}
    if include_html:page['html']=response['body']
    return page
