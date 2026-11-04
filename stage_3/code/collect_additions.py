"""Collect explicitly approved URLs; preserve provenance, no LLM calls.

Run --fetch for new snapshots. Existing snapshots are reused by default.
"""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from analyst import digest, read, save

ROOT = Path(__file__).resolve().parents[1]
ADDITIONS = [
    ('portugaldom', 'PortugalDom', 'https://portugaldom.pt/legalizacziya-v-portugalii/'),
    ('movetocascais', 'MoveToCascais', 'https://movetocascais.com/ru/o-nas/'),
    ('monolite', 'MONOLITE', 'https://monolite.pt/#uslugi'),
    ('okno', 'OKNO Agency', 'https://okno.agency'),
]
AGENT = 'CompetitorResearchBot/1.0'


def collect():
    target = ROOT / 'input/additions'
    target.mkdir(parents=True, exist_ok=True)
    sources = []
    session = requests.Session()
    session.headers['User-Agent'] = AGENT
    for cid, name, supplied_url in ADDITIONS:
        url = supplied_url.split('#')[0]
        record = {'source_id': cid + '_20261104', 'company_id': cid,
                  'supplied_url': supplied_url, 'requested_url': url,
                  'collected_at': datetime.now(timezone.utc).isoformat(),
                  'method': 'python_requests_beautifulsoup', 'source_kind': 'official_website'}
        try:
            parts = urlsplit(url)
            robots_url = parts.scheme + '://' + parts.netloc + '/robots.txt'
            robots = session.get(robots_url, timeout=30)
            policy = RobotFileParser()
            if robots.status_code == 200:
                policy.parse(robots.text.splitlines())
                if not policy.can_fetch(AGENT, url):
                    record.update(status='robots_disallowed', robots_mode='parsed')
                    sources.append(record)
                    continue
                record['robots_mode'] = 'parsed'
            elif robots.status_code in (404, 410):
                record['robots_mode'] = 'not_found'
            else:
                record.update(status='robots_unavailable', robots_http_status=robots.status_code)
                sources.append(record)
                continue
            response = session.get(url, timeout=45)
            record.update(http_status=response.status_code, final_url=response.url)
            response.raise_for_status()
            if 'html' not in response.headers.get('content-type', '').lower():
                raise ValueError('not_html')
            response.encoding = response.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            record['title'] = soup.title.get_text(' ', strip=True) if soup.title else name
            for tag in soup(['script', 'style', 'noscript', 'svg', 'template']):
                tag.decompose()
            text = re.sub(r'\s+', ' ', soup.get_text(' ', strip=True)).strip()
            path = target / (cid + '.txt')
            path.write_text(text + '\n', encoding='utf-8')
            record.update(status='ok', sha256_response=hashlib.sha256(response.content).hexdigest(),
                          text_path=path.relative_to(ROOT / 'input').as_posix(),
                          sha256_text=digest(path), text_chars=len(text),
                          note='One supplied page only; no full-site coverage or legal verification')
        except (requests.RequestException, ValueError) as exc:
            record.update(status='collection_failed', error_type=type(exc).__name__)
        sources.append(record)
        time.sleep(1)
    save(target / 'sources.json', sources)
    print(json.dumps([{k: s.get(k) for k in ('company_id', 'status', 'final_url', 'text_chars')} for s in sources], ensure_ascii=False))


def register():
    companies = read(ROOT / 'input/companies.json')
    candidates = read(ROOT / 'input/competitor_candidates.json')
    log = []
    for cid, name, url in ADDITIONS:
        company = next((c for c in companies if c['id'] == cid), None)
        existing = company is not None
        if not existing:
            company = {'id': cid, 'name': name, 'role': 'confirmed_competitor', 'seed_urls': []}
            companies.append(company)
            candidates['candidates'].append({'name': name, 'url': url,
                'source_url': url, 'countries': ['Португалия'], 'added_by': 'user',
                'added_on': '2026-11-04', 'discovery_method': 'user_supplied',
                'category': 'Кандидат, подтверждённый пользователем',
                'match': 'Релокация и юридические услуги; проверка по сохранённой странице',
                'evidence': 'Ссылка предоставлена пользователем; не результат автоматического поиска'})
        company.update(added_by='user', discovery_method='user_supplied')
        if url not in company['seed_urls']:
            company['seed_urls'].append(url)
        candidate = next(c for c in candidates['candidates'] if c['name'] == name)
        candidate.update(added_by='user', discovery_method='user_supplied')
        candidate.setdefault('user_supplied_urls', [])
        if url not in candidate['user_supplied_urls']:
            candidate['user_supplied_urls'].append(url)
        log.append({'company_id': cid, 'name': name, 'supplied_url': url, 'added_by': 'user',
                    'discovery_method': 'user_supplied', 'already_registered': cid == 'movetocascais',
                    'action': 'enrich_existing_no_duplicate' if cid == 'movetocascais' else 'register_user_addition'})
    save(ROOT / 'input/companies.json', companies)
    candidates.update(updated_on='2026-11-04', confirmed_on='2026-11-04')
    save(ROOT / 'input/competitor_candidates.json', candidates)
    save(ROOT / 'input/user_additions.json', {'requested_on': '2026-11-04', 'items': log,
        'note': 'MoveToCascais was already user-added on 2026-10-21. The other three were absent from the saved candidate catalogs; not attributed to the search script.'})
    cfg = read(ROOT / 'config.json')
    cfg['competitors'] = [c['id'] for c in companies if c['role'] == 'confirmed_competitor']
    save(ROOT / 'config.json', cfg)


def manifest():
    save(ROOT / 'input/manifest.json', [
        {'path': p.relative_to(ROOT).as_posix(), 'sha256': digest(p), 'bytes': p.stat().st_size}
        for p in sorted((ROOT / 'input').rglob('*')) if p.is_file() and p.name != 'manifest.json'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    if args.fetch:
        collect()
    register()
    manifest()
