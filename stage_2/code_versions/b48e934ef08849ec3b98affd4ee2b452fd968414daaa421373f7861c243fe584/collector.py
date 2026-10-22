"""Reproducible public-source collection and evidence-grounded extraction.

No API keys are stored. Each run is append-only in its own directory.
"""
from __future__ import annotations

import csv
import hashlib
import html
import importlib.metadata
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from jsonschema import validate, ValidationError


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode('utf-8')).hexdigest()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def append_event(run_dir, event):
    with (Path(run_dir) / 'events.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'at': utc_now(), **event}, ensure_ascii=False) + '\n')


def write_csv(path, rows, fields):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            values = {key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()}
            # Spreadsheet formula injection protection in the human-facing CSV.
            writer.writerow({key: "'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@')) else value for key, value in values.items()})


def normalize_url(url):
    parts = urlsplit(url.strip())
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        return None
    # Query stays: service variants can depend on query. Only fragments removed.
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/', parts.query, ''))


def hostname(url):
    return (urlsplit(url).hostname or '').lower().removeprefix('www.')


def clean_html(raw_html, base_url):
    soup = BeautifulSoup(raw_html, 'html.parser')
    title = soup.title.get_text(' ', strip=True) if soup.title else ''
    links = []
    for anchor in soup.select('a[href]'):
        href = anchor.get('href', '').strip()
        absolute = normalize_url(urljoin(base_url, href))
        if absolute:
            links.append({'url': absolute, 'label': anchor.get_text(' ', strip=True)[:250]})
        elif href.startswith(('mailto:', 'tel:')):
            links.append({'url': href, 'label': anchor.get_text(' ', strip=True)[:250]})
    for tag in soup(['script', 'style', 'noscript', 'svg', 'template', 'head', 'form', 'nav', 'footer']):
        tag.decompose()
    lines = []
    for line in soup.get_text('\n', strip=True).splitlines():
        line = re.sub(r'\s+', ' ', html.unescape(line)).strip()
        if line:
            # Local context repeated in separate product cards must remain.
            lines.append(line)
            # Do not globally deduplicate price/name lines: their relation matters.
    return {'title': title, 'text': '\n'.join(lines), 'links': list({x['url']: x for x in links}.values())}


def split_chunks(text, size=7000, overlap=600):
    if size < 100 or not 0 <= overlap < size:
        raise ValueError('Неверные chunk_size/chunk_overlap')
    result, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind('\n', start + size // 2, end)
            if boundary > start:
                end = boundary
        result.append({'start': start, 'end': end, 'text': text[start:end]})
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return result


def fetch_public(url, timeout, max_bytes, user_agent):
    try:
        response = requests.get(url, headers={'User-Agent': user_agent, 'Accept-Language': 'ru,en;q=0.7'}, timeout=timeout, stream=True)
        pieces, total = [], 0
        for piece in response.iter_content(65536):
            total += len(piece)
            if total > max_bytes:
                response.close()
                return {'status': 'too_large', 'http_status': response.status_code, 'final_url': response.url, 'raw': b''}
            pieces.append(piece)
        raw = b''.join(pieces)
        response.close()
        content_type = response.headers.get('Content-Type', '')
        return {'status': 'ok' if response.status_code == 200 else 'http_error', 'http_status': response.status_code,
                'final_url': response.url, 'raw': raw, 'content_type': content_type,
                'encoding': response.encoding if response.encoding and 'charset=' in content_type.lower() else 'utf-8'}
    except requests.RequestException as exc:
        # Do not log headers, environment or request objects.
        return {'status': 'network_error', 'http_status': None, 'final_url': url, 'raw': b'', 'error_type': type(exc).__name__}


def robots_check(url, config, cache, run_dir):
    origin = urlunsplit((*urlsplit(url)[:2], '', '', ''))
    if origin not in cache:
        robots_url = origin + '/robots.txt'
        data = fetch_public(robots_url, config['timeout'], 512000, config['user_agent'])
        raw = data.pop('raw')
        robots_path = Path(run_dir) / 'raw' / (digest(robots_url)[:16] + '_robots.txt')
        robots_path.parent.mkdir(parents=True, exist_ok=True)
        robots_path.write_bytes(raw)
        parser = RobotFileParser()
        if data['http_status'] == 200:
            parser.parse(raw.decode('utf-8', errors='replace').splitlines())
            mode = 'parsed'
        elif data['http_status'] == 404:
            parser = None
            mode = 'not_found'
        else:
            parser = None
            mode = 'unavailable_stop'
        cache[origin] = (parser, mode)
        append_event(run_dir, {'action': 'robots_fetch', 'url': robots_url, 'sha256': digest(raw), 'raw_path': str(robots_path.relative_to(run_dir)), 'mode': mode, **data})
    parser, mode = cache[origin]
    return (parser.can_fetch(config['user_agent'], url) if parser else mode == 'not_found'), mode


def link_type(url):
    host = hostname(url)
    if host in ('t.me', 'telegram.me', 'instagram.com', 'facebook.com', 'linkedin.com', 'youtube.com', 'youtu.be', 'vk.com'):
        return 'social'
    if host in ('maps.app.goo.gl', 'goo.gl', 'yandex.ru', 'yandex.com', 'maps.google.com') or 'google.' in host and '/maps' in url:
        return 'map_candidate'
    if url.startswith(('tel:', 'mailto:')) or host in ('wa.me', 'api.whatsapp.com'):
        return 'contact'
    return 'website'


def crawl_company(company, config, run_dir, robots_cache):
    allowed = {hostname(u) for u in company['seed_urls']}
    queue = [normalize_url(u) for u in company['seed_urls']]
    visited, sources, links, chunks, seen_texts = set(), [], [], [], {}
    while queue and len(sources) < config['pages_per_company']:
        url = queue.pop(0)
        if not url or url in visited or hostname(url) not in allowed:
            continue
        visited.add(url)
        source_id = company['id'] + '_' + digest(url)[:14]
        source = {'source_id': source_id, 'company_id': company['id'], 'requested_url': url, 'collected_at': utc_now(), 'method': 'python_requests', 'source_kind': 'official_website', 'status': 'pending'}
        allowed_by_robots, robots_mode = robots_check(url, config, robots_cache, run_dir)
        source['robots_mode'] = robots_mode
        if not allowed_by_robots:
            source['status'] = 'robots_disallowed_or_unavailable'
            sources.append(source)
            append_event(run_dir, {'action': 'fetch_skipped', **source})
            continue
        time.sleep(config['delay_seconds'])
        result = fetch_public(url, config['timeout'], config['max_bytes'], config['user_agent'])
        raw = result.pop('raw')
        source.update(result)
        source['sha256_raw'] = digest(raw)
        raw_path = Path(run_dir) / 'raw' / (source_id + '.html')
        raw_path.write_bytes(raw)
        source['raw_path'] = str(raw_path.relative_to(run_dir))
        if result['status'] == 'ok' and 'html' in result.get('content_type', '').lower():
            if hostname(result['final_url']) not in allowed:
                source['status'] = 'redirect_outside_scope'
                sources.append(source)
                append_event(run_dir, {'action': 'fetch', **source})
                continue
            page = clean_html(raw.decode(result.get('encoding', 'utf-8'), errors='replace'), result['final_url'])
            source['title'] = page['title']
            text = page['text']
            text_hash = digest(text)
            source.update({'sha256_text': text_hash, 'text_chars': len(text)})
            if re.search(r'(Just a moment|Verify you are human|Access denied|Checking your browser)', page['title'], re.I):
                source['status'] = 'challenge'
            elif len(text) < 200:
                source['status'] = 'insufficient_static_text'
            elif text_hash in seen_texts:
                source.update({'status': 'duplicate_text', 'duplicate_of': seen_texts[text_hash]})
            else:
                seen_texts[text_hash] = source_id
                text_path = Path(run_dir) / 'clean' / (source_id + '.txt')
                text_path.parent.mkdir(exist_ok=True)
                text_path.write_text(text, encoding='utf-8')
                source['text_path'] = str(text_path.relative_to(run_dir))
                for index, chunk in enumerate(split_chunks(text, config['chunk_size'], config['chunk_overlap'])):
                    chunks.append({'chunk_id': source_id + f'_c{index:03}', 'source_id': source_id, 'company_id': company['id'], 'url': result['final_url'], 'collected_at': source['collected_at'], **chunk})
            for link in page['links']:
                links.append({'company_id': company['id'], 'source_id': source_id, 'found_on': result['final_url'], 'collected_at': source['collected_at'], 'type': link_type(link['url']), 'ownership_status': 'site_link_only' if link_type(link['url']) == 'social' else 'not_reviewed', **link})
                # Only linked pages on approved domains, prioritized by services/countries.
                if hostname(link['url']) in allowed and re.search(config['follow_pattern'], link['url'] + ' ' + link['label'], re.I) and not re.search(r'\.(pdf|jpg|png|zip|docx)(\?|$)', link['url'], re.I):
                    if link['url'] not in visited and link['url'] not in queue:
                        queue.append(link['url'])
        elif result['status'] == 'ok':
            source['status'] = 'unsupported_content_type'
        sources.append(source)
        append_event(run_dir, {'action': 'fetch', **source})
    return sources, links, chunks


def start_collection(config, companies, output_root):
    profile_stage = config.get('purpose') == 'own_company_profile'
    if not profile_stage and (not config.get('profile_confirmed') or not config.get('competitors_confirmed')):
        raise ValueError('Нужно подтверждение профиля и списка конкурентов')
    selected = [company for company in companies if company['id'] in config['selected_ids']]
    if len(selected) != len(config['selected_ids']) or not selected:
        raise ValueError('Неизвестные или повторные selected_ids')
    if profile_stage and (len(selected) != 1 or selected[0].get('role') != 'own_company'):
        raise ValueError('До подтверждения допустим только сайт собственной компании')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:6]
    run_dir = Path(output_root) / run_id
    (run_dir / 'raw').mkdir(parents=True)
    sources, links, chunks, robots_cache = [], [], [], {}
    save_json(run_dir / 'run_config.json', config)
    save_json(run_dir / 'companies.json', selected)
    save_json(run_dir / 'environment.json', {'python': __import__('sys').version, 'packages': {name: importlib.metadata.version(name) for name in ('requests', 'beautifulsoup4', 'jsonschema')}})
    for company in selected:
        company_sources, company_links, company_chunks = crawl_company(company, config, run_dir, robots_cache)
        sources.extend(company_sources)
        links.extend(company_links)
        chunks.extend(company_chunks)
    save_json(run_dir / 'sources.json', sources)
    save_json(run_dir / 'discovered_links.json', links)
    save_json(run_dir / 'chunks.json', chunks)
    write_csv(run_dir / 'sources.csv', sources, ['company_id','source_id','requested_url','final_url','collected_at','status','http_status','text_chars','sha256_raw','raw_path','text_path','robots_mode'])
    save_json(run_dir / 'external_queue.json', make_external_queue(selected, links, config))
    append_event(run_dir, {'action': 'collection_complete', 'sources': len(sources), 'chunks': len(chunks), 'llm_executed': False})
    return run_dir


def make_external_queue(companies, links, config):
    queue = []
    for company in companies:
        queue.extend({'company_id': company['id'], 'kind': engine, 'query': company['name'], 'language': 'ru', 'region': config['search_region'], 'status': 'pending', 'method': 'browser_or_licensed_search_api', 'coverage': 'first_results_page', 'url': base + requests.utils.quote(company['name'])} for engine, base in [('google','https://www.google.com/search?hl=ru&gl=pt&q='),('yandex','https://yandex.com/search/?lang=ru&text=')])
        queue.append({'company_id': company['id'], 'kind':'social_internal_search','query':company['name'],'status':'pending','method':'native_social_search_after_profile_selection'})
        for link in links:
            if link['company_id'] == company['id'] and link['type'] in ('social','map_candidate'):
                queue.append({**link, 'kind':link['type'], 'status':'pending', 'sampling_days':config['social_days'], 'max_posts':config['social_max_posts'], 'method':'public_http_if_supported_else_manual_browser'})
    return queue


def load_colab_key():
    from google.colab import userdata
    return userdata.get('PROXYAPI_KEY')


def api_json(base_url, path, api_key, payload=None):
    # Restrict the secret's destination to the provider the user authorized.
    parsed = urlsplit(base_url)
    if parsed.scheme != 'https' or parsed.hostname != 'api.proxyapi.ru' or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('Допустим HTTPS endpoint api.proxyapi.ru')
    headers = {'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'}
    method = requests.get if payload is None else requests.post
    try:
        response = method(base_url.rstrip('/') + path, headers=headers, **({} if payload is None else {'json': payload}), timeout=120, allow_redirects=False)
    except requests.RequestException:
        raise RuntimeError('ProxyAPI: ошибка соединения; ключ не включён в журнал') from None
    if response.status_code != 200:
        try:
            error = response.json().get('error', {})
            message = str(error.get('message','')) if isinstance(error,dict) else str(error)
        except ValueError:
            message = 'non_json_error'
        message = message.replace(api_key, '[REDACTED]')[:500]
        raise RuntimeError(f'ProxyAPI HTTP {response.status_code}: {message}')
    return response.json()


def list_models(base_url, api_key):
    return sorted(item['id'] for item in api_json(base_url, '/models', api_key).get('data', []))


def fact_schema():
    properties = {'field': {'type':'string','enum':['service','composition','price','condition','audience','geography','positioning','trust','contact']}, 'value':{'type':'string'}, 'evidence':{'type':'string'}, 'kind':{'type':'string','enum':['company_claim','published_offer']}, 'country':{'type':['string','null']}, 'offer_name':{'type':['string','null']}, 'amount':{'type':['number','null']}, 'currency':{'type':['string','null']}, 'price_basis':{'type':['string','null']}}
    return {'type':'object','properties':{'facts':{'type':'array','items':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}},'required':['facts'],'additionalProperties':False}


def validate_extraction(result, chunk, schema):
    validate(result, schema)
    accepted, quarantine = [], []
    for fact in result['facts']:
        errors = []
        quote = fact['evidence']
        if len(quote.strip()) < 8 or quote not in chunk['text']:
            errors.append('quote_not_found_or_too_short')
        if not fact['value'].strip():
            errors.append('empty_value')
        if fact['field'] == 'price' and (not fact['offer_name'] or fact['amount'] is None or not fact['currency']):
            errors.append('price_missing_offer_amount_currency')
        if fact['field'] == 'price':
            context = re.sub(r'\b(?:EUR|USD|GBP|RUB)\b', '', quote, flags=re.I)
            if not re.search(r'[A-Za-zА-Яа-яЁё]', context):
                errors.append('price_quote_has_no_service_context')
        if fact['amount'] is not None and (fact['amount'] < 0 or fact['field'] != 'price'):
            errors.append('amount_requires_nonnegative_price')
        if fact['field'] == 'price' and fact['amount'] is not None:
            numbers = []
            for token in re.findall(r'\d(?:[\d \u00a0\u202f]*\d)?(?:[.,]\d{1,2})?', quote):
                try:
                    numbers.append(float(re.sub(r'[ \u00a0\u202f]', '', token).replace(',', '.')))
                except ValueError:
                    pass
            if not any(abs(number-fact['amount']) < 0.005 for number in numbers):
                errors.append('amount_not_present_in_quote')
        if fact['field'] == 'trust' and fact['kind'] != 'company_claim':
            errors.append('trust_must_remain_company_claim')
        offset = chunk['text'].find(quote)
        record = {**fact, 'company_id':chunk['company_id'], 'source_id':chunk['source_id'], 'chunk_id':chunk['chunk_id'], 'url':chunk['url'], 'collected_at':chunk['collected_at'], 'extracted_at':utc_now(), 'evidence_start':chunk['start']+offset if offset >= 0 else None, 'review_status':'pending_human_review', 'origin':'llm_extraction'}
        record['fact_id'] = digest(json.dumps([record['company_id'], record['source_id'], fact], ensure_ascii=False, sort_keys=True))[:20]
        if errors:
            quarantine.append({**record,'validation_errors':errors})
        else:
            accepted.append(record)
    return accepted, quarantine


def extract_run(run_dir, api_key, model, settings, prompt, max_calls=4):
    run_dir = Path(run_dir)
    if not model:
        raise ValueError('Выберите модель из /v1/models')
    if model not in list_models(settings['base_url'], api_key):
        raise ValueError('Выбранная модель отсутствует в полученном каталоге')
    if not isinstance(max_calls, int) or max_calls < 1:
        raise ValueError('max_calls должен быть положительным целым')
    chunks = read_json(run_dir / 'chunks.json')
    if settings.get('chunk_ids'):
        requested_ids = settings['chunk_ids']
        selected_chunks = [c for c in chunks if c['chunk_id'] in requested_ids]
        if len(selected_chunks) != len(requested_ids):
            raise ValueError('Не найдены выбранные контрольные фрагменты')
        chunks = selected_chunks
    # Round-robin prevents spending the entire pilot on company one's homepage.
    ids = list(dict.fromkeys(c['company_id'] for c in chunks))
    groups = [[c for c in chunks if c['company_id'] == cid] for cid in ids]
    ordered = [group[i] for i in range(max((len(g) for g in groups), default=0)) for group in groups if i < len(group)]
    experiment = run_dir / 'experiments' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:6])
    experiment.mkdir(parents=True)
    safe_settings = {key: value for key,value in settings.items() if key in ('base_url','response_format','parameters','chunk_ids')}
    meta = {'model':model,'settings':safe_settings,'prompt':prompt,'prompt_sha256':digest(prompt),'schema':fact_schema(),'max_calls':max_calls,'started_at':utc_now(),'chunks_total':len(chunks),'status':'running'}
    meta['collector_sha256'] = digest(Path(__file__).read_bytes())
    meta['chunks_sha256'] = digest((run_dir/'chunks.json').read_bytes())
    save_json(experiment / 'experiment.json', meta)
    accepted, quarantine, failures = [], [], []
    for chunk in ordered[:max_calls]:
        content = json.dumps({'company_id':chunk['company_id'],'url':chunk['url'],'text':chunk['text']}, ensure_ascii=False)
        payload = {'model':model,'messages':[{'role':'system','content':prompt},{'role':'user','content':content}], **settings.get('parameters',{})}
        if settings.get('response_format') == 'json_schema':
            payload['response_format'] = {'type':'json_schema','json_schema':{'name':'company_facts','strict':True,'schema':fact_schema()}}
        elif settings.get('response_format') == 'json_object':
            payload['response_format'] = {'type':'json_object'}
        save_json(experiment / (chunk['chunk_id']+'_request.json'), payload)
        try:
            response = api_json(settings['base_url'], '/chat/completions', api_key, payload)
            # Only content and usage are saved, never request headers.
            choice = response.get('choices',[{}])[0]
            raw_content = choice.get('message',{}).get('content')
            save_json(experiment / (chunk['chunk_id']+'_response.json'), {'content':raw_content,'usage':response.get('usage'),'finish_reason':choice.get('finish_reason'),'model':response.get('model')})
            if choice.get('finish_reason') != 'stop':
                raise ValueError('incomplete_response')
            good, bad = validate_extraction(json.loads(raw_content), chunk, fact_schema())
            accepted.extend(good)
            quarantine.extend(bad)
        except (RuntimeError, ValueError, TypeError, KeyError, IndexError, ValidationError) as exc:
            failure = {'chunk_id':chunk['chunk_id'],'error_type':type(exc).__name__,'status':'not_extracted','detail':str(exc).replace(api_key,'[REDACTED]')[:600]}
            failures.append(failure)
            append_event(run_dir, {'action':'llm_failure','experiment':experiment.name,**failure})
    accepted = list({digest(json.dumps([r['company_id'],r['source_id'],r['field'],r['value'],r['evidence']],ensure_ascii=False)):r for r in accepted}.values())
    save_json(experiment / 'facts.json', accepted)
    save_json(experiment / 'price_conflicts.json', find_price_conflicts(accepted))
    save_json(experiment / 'quarantine.json', quarantine)
    save_json(experiment / 'failures.json', failures)
    write_csv(experiment / 'facts.csv', accepted, ['fact_id','company_id','field','value','country','offer_name','amount','currency','price_basis','kind','url','collected_at','evidence','review_status'])
    meta.update({'completed_at':utc_now(),'status':'completed_with_errors' if failures else 'completed','chunks_attempted':min(max_calls,len(ordered)),'accepted':len(accepted),'quarantined':len(quarantine),'failures':len(failures),'coverage':'partial' if max_calls < len(chunks) or failures else 'all_saved_chunks_attempted'})
    save_json(experiment / 'experiment.json', meta)
    append_event(run_dir, {'action':'extraction_complete','experiment':experiment.name,'model':model,'accepted':len(accepted),'quarantined':len(quarantine),'failures':len(failures)})
    return experiment


def find_price_conflicts(facts):
    groups = {}
    for fact in facts:
        if fact['field'] != 'price':
            continue
        key = (fact['company_id'], re.sub(r'\W+', '', (fact['offer_name'] or '').casefold()), fact['country'], fact['currency'])
        groups.setdefault(key,[]).append(fact)
    return [{'company_id':key[0],'offer_key':key[1],'fact_ids':[f['fact_id'] for f in group],'amounts':sorted({f['amount'] for f in group}),'status':'potential_conflict_requires_context_review'} for key,group in groups.items() if len({f['amount'] for f in group})>1]


def main(config, companies, output_root='runs', api_key=None, model=None, llm_settings=None, prompt=None, max_calls=4):
    run_dir = start_collection(config, companies, output_root)
    if api_key is not None:
        extract_run(run_dir, api_key, model, llm_settings, prompt, max_calls)
    return run_dir


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--companies', default='companies.json')
    parser.add_argument('--output', default='../runs')
    args = parser.parse_args()
    print(main(read_json(args.config)['collection'], read_json(args.companies), args.output))
