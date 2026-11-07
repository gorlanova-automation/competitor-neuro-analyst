"""Reusable first step: capture a public page, draft profile and search queries.

No model or paid API is called. A draft must be confirmed by a person.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

AGENT = 'CompetitorResearchBot/1.0'


def capture(url):
    from resilient_fetch import fetch
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise ValueError('A public HTTPS URL without credentials is required')
    session = requests.Session()
    session.headers['User-Agent'] = AGENT
    source=fetch(session,url,{})
    if source['status']!='ok':raise ValueError(source['status'])
    return {**source,'requested_url':url}


def draft_profile(source):
    text = source['text']
    video = 'video' in (source['title']+' '+source['description']+' '+text[:1500]).lower()
    market_terms = 'AI video analysis short form creators' if video else source['description'] or source['title']
    return {'company_name': re.split(r'[·|—]', source['title'])[0].strip(),
            'headline': source['headings'][0] if source['headings'] else None,
            'summary': source['description'], 'market_terms': market_terms,
            'inference_method': 'metadata_headings_and_explicit_keyword_rule_no_llm',
            'source_url': source['final_url'], 'source_sha256': source['sha256_text'],
            'review_status': 'pending_user_confirmation',
            'search_queries': [market_terms+' competitors', market_terms+' timestamp editing feedback',
                               market_terms+' pricing alternatives'],
            'needs_user_input': ['Подтвердить продукт и аудиторию', 'Уточнить географию и язык рынка',
                                 'Подтвердить или дополнить конкурентов'],
            'limits': ['Черновик по одной странице; утверждения сайта не проверены на практике.',
                       'Профиль и запросы требуют подтверждения. Правило video — демонстрационная эвристика, не универсальный классификатор.']}


def build_case(out, own_url, candidate_urls, own_snapshot=None):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    own = json.loads(Path(own_snapshot).read_text(encoding='utf-8')) if own_snapshot else capture(own_url)
    if own['requested_url'] != own_url: raise ValueError('Snapshot URL mismatch')
    actual_hash = hashlib.sha256(own['text'].encode()).hexdigest()
    if own.get('sha256_text') and own['sha256_text'] != actual_hash: raise ValueError('Snapshot hash mismatch')
    own['sha256_text'] = actual_hash
    (out/'own_source.json').write_text(json.dumps(own, ensure_ascii=False, indent=2), encoding='utf-8')
    profile = draft_profile(own)
    (out/'profile.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
    sources = []
    for url in candidate_urls:
        try:
            source = capture(url)
            source.update(role='candidate', discovery_method='researcher_selected_from_web_search',
                          confirmation_status='pending_user_confirmation')
        except (requests.RequestException, ValueError) as exc:
            source = {'requested_url': url, 'status': 'collection_failed', 'error_type': type(exc).__name__,
                      'confirmation_status': 'pending_user_confirmation'}
        sources.append(source)
    (out/'candidate_sources.json').write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding='utf-8')
    state = {'case_id': out.name, 'status': 'awaiting_profile_and_competitor_confirmation',
             'profile': profile, 'candidates': [{k: s.get(k) for k in ('title','requested_url','final_url','description','sha256_text','confirmation_status','status')} for s in sources],
             'new_llm_calls': 0, 'new_api_cost': 0,
             'comparison_status': 'blocked_pending_user_review',
             'requested_market_scope': None,
             'search_provenance': 'Search performed by assistant web tool, not by the Python collector. Queries saved in search_log.json.',
             'hypotheses': [], 'limits': ['Не смешивать с услугами релокации.', 'Наличие страницы не доказывает качество продукта.']}
    (out/'result.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--candidate', action='append', default=[])
    parser.add_argument('--own-snapshot', help='Explicit rendered capture when direct collection is unavailable')
    args = parser.parse_args()
    result = build_case(args.out, args.url, args.candidate, args.own_snapshot)
    print(json.dumps({'status': result['status'], 'profile': result['profile']['company_name'],
                      'candidates': len(result['candidates']), 'new_llm_calls': 0}, ensure_ascii=False))
