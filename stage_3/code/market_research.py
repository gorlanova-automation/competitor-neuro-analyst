"""Bounded whole-offer and promotion reconnaissance, with traceable excerpts.

Discovers links from official websites; never treats absent data as absent activity.
Rules propose observations for review; they are not a semantic LLM analysis.
"""
import argparse
import concurrent.futures
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urldefrag
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
UA='CompetitorResearchBot/1.0'
GROUPS={
 'residency':('ВНЖ и иммиграционные программы',r'ВНЖ|residen|digital.nomad|виза|visa|иммиграц'),
 'citizenship':('Гражданство',r'гражданств|citizenship|nationality'),
 'documents':('Документы и административные услуги',r'\bNIF\b|\bNISS\b|\bNIE\b|перевод|апостил|документ|tax.number'),
 'business':('Бизнес и регистрация компаний',r'регистрац.{0,30}(?:компан|бизнес)|открыт.{0,20}компан|company.formation|incorporation|aut[oó]nomo'),
 'tax':('Налоги и бухгалтерия',r'налог|бухгалтер|tax|accounting'),
 'property':('Недвижимость и адаптация',r'недвижим|аренд|жиль|real.estate|property|школ|адаптац'),
 'legal':('Юридическое сопровождение',r'адвокат|юридич|судеб|lawyer|legal.service'),
 'investment':('Инвестиционные программы',r'инвестиц|investment|golden.visa'),
}
SOCIAL={'t.me':'Telegram','instagram.com':'Instagram','facebook.com':'Facebook','youtube.com':'YouTube',
        'youtu.be':'YouTube','linkedin.com':'LinkedIn','tiktok.com':'TikTok','vk.com':'VK','vk.ru':'VK'}


def utc(): return datetime.now(timezone.utc).isoformat()
def sha(text): return hashlib.sha256(text.encode()).hexdigest()
def host(url): return (urlsplit(url).hostname or '').lower().removeprefix('www.')
def save(path,value): path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())


from resilient_fetch import fetch


def excerpt(text,pattern):
    m=re.search(pattern,text,re.I)
    return text[max(0,m.start()-70):min(len(text),m.end()+150)] if m else None


def collect_company(company,max_pages,out):
    session=requests.Session();session.headers['User-Agent']=UA
    policies={};pages=[];seen=set();queue=list(dict.fromkeys(urldefrag(u)[0] for u in company['seed_urls']))
    while queue and len(pages)<max_pages*3 and sum(p['status']=='ok' for p in pages)<max_pages:
        url=queue.pop(0)
        if url in seen:continue
        seen.add(url)
        try:page=fetch(session,url,policies)
        except (requests.RequestException,ValueError) as exc:page={'url':url,'status':'collection_error','error_type':type(exc).__name__,'collected_at':utc()}
        pages.append(page)
        if page['status']!='ok':
            if page.get('failure_kind',page['status'])=='dns_error' and urlsplit(url).netloc.startswith('www.'):
                alternate=url.replace('https://www.','https://',1)
                if alternate not in seen and alternate not in queue:queue.append(alternate)
            continue
        homehost=host(page['final_url'])
        options=[]
        for link in page['links']:
            if host(link['url'])!=homehost or link['url'] in seen:continue
            context=link['label']+' '+urlsplit(link['url']).path
            if re.search(r'privacy|cookie|terms|login|account|политик|оферт|agreement|\.pdf',context,re.I):continue
            score=3 if re.search(r'услуг|service|pricing|тариф|пакет|residen|внж|relocat',context,re.I) else 2 if re.search(r'blog|блог|стать|news|about|о.нас',context,re.I) else 0
            if score:options.append((score,link['url']))
        for _,candidate in sorted(options,key=lambda x:-x[0]):
            if candidate not in queue:queue.append(candidate)
    save(out/(company['id']+'_sources.json'),pages)
    observations=[];channels={};content_links={};ctas=[]
    for p in pages:
        if p['status']!='ok':continue
        for key,(label,pattern) in GROUPS.items():
            quote=excerpt(p['text'],pattern)
            if quote:observations.append({'category':key,'name':label,'quote':quote,'source_url':p['final_url'],
                'source_sha256':p['sha256_text'],'collected_at':p['collected_at'],
                'status':'rule_detected_mention_requires_review','basis':'Keyword in page text; navigation or article may mention an offer without proving it is sold.'})
        for link in p['links']:
            domain=host(link['url'])
            for base,label in SOCIAL.items():
                if domain==base or domain.endswith('.'+base):
                    channels[link['url']]={'platform':label,'url':link['url'],'found_on':p['final_url'],
                       'ownership':'linked_from_official_site_not_independently_verified',
                       'purpose':'contact_or_feed_not_yet_classified','posts_status':'not_collected'}
            if host(link['url'])==host(p['final_url']) and re.search(r'blog|стать|news|article',link['url']+' '+link['label'],re.I):
                content_links[link['url']]={**link,'found_on':p['final_url']}
        for pattern,label in [(r'консультац|consultation','Консультация'),(r'остав.{0,15}заявк|записат|book.a|contact.us','Обращение / запись'),(r'калькулятор|calculator','Калькулятор'),(r'бесплат|free','Заявление о бесплатном предложении')]:
            quote=excerpt(p['text'],pattern)
            if quote:ctas.append({'type':label,'quote':quote,'source_url':p['final_url']})
    tones=[]
    for pattern,label in [(r'поможем|помогаем|поддержк|комфорт|беззабот','Поддержка и снижение тревоги'),
                          (r'эксперт|адвокат|юрист|опыт|professional|expert','Экспертность и профессиональный опыт'),
                          (r'гарант|100\s*%|успешн|success','Заявления об успехе / гарантиях'),
                          (r'инвестиц|капитал|private|wealth','Инвестиционное позиционирование')]:
        for p in pages:
            if p['status']=='ok':
                q=excerpt(p['text'],pattern)
                if q:tones.append({'label':label,'quote':q,'source_url':p['final_url'],'method':'lexical_signal_not_semantic_verdict'});break
    return {'company_id':company['id'],'name':company['name'],'added_by':company.get('added_by'),
        'pages_attempted':len(pages),'pages_ok':sum(p['status']=='ok' for p in pages),
        'sources':[{k:v for k,v in p.items() if k not in ('text','links','image_metadata')} for p in pages],
        'assortment':observations,'channels':list(channels.values()),'content_links':list(content_links.values())[:30],
        'conversion_paths':ctas,'tone_signals':tones,
        'visual':{'status':'not_visually_reviewed','image_count_in_html':sum(len(p.get('image_metadata',[])) for p in pages),
                  'note':'HTML metadata cannot establish colours, composition, visual quality or brand consistency.'},
        'coverage':'bounded_official_pages_not_full_site','new_llm_calls':0}


def recovery_queue(results):
    """Keep collection failures separate from evidence of absent activity."""
    return [{'company_id':company['company_id'],'url':source.get('url'),
             'status':source['status'],'cause':source.get('failure_kind',source['status']),
             'next_action':source.get('next_action') or 'review_source_and_retry',
             'attempts':source.get('attempts',[])}
            for company in results for source in company['sources'] if source['status']!='ok']


def create_run_directory(parent):
    out=Path(parent)/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False)
    return out


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--max-pages',type=int,default=4)
    parser.add_argument('--output-root',type=Path,default=ROOT/'research/collection_runs')
    parser.add_argument('--company',action='append',help='Company ID; repeat to select several companies')
    args=parser.parse_args()
    if not 1<=args.max_pages<=30:parser.error('--max-pages must be between 1 and 30')
    companies=json.loads((ROOT/'input/companies.json').read_text(encoding='utf-8'))
    if args.company:
        unknown=set(args.company)-{c['id'] for c in companies}
        if unknown:parser.error('Unknown company IDs: '+', '.join(sorted(unknown)))
        companies=[c for c in companies if c['id'] in args.company]
    out=create_run_directory(args.output_root)
    print('Run directory:',out,flush=True)
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(collect_company,c,args.max_pages,out):c for c in companies}
        for future in concurrent.futures.as_completed(jobs):
            result=future.result();results.append(result)
            print(result['name'],result['pages_ok'],'pages;',len(result['channels']),'channels',flush=True)
    results.sort(key=lambda c:next(i for i,x in enumerate(companies) if x['id']==c['company_id']))
    save(out/'recovery_queue.json',recovery_queue(results))
    save(out/'overview.json',{'generated_at':utc(),'companies':results,'max_pages_per_company':args.max_pages,
         'method':'Bounded link discovery, lexical candidate observations, exact source excerpts. No LLM calls.',
         'limits':['Не полный обход сайтов и площадок.','Сигналы требуют смысловой проверки; упоминание не доказывает предложение услуги.',
                   'Частота публикаций и эффективность продвижения без корпуса и метрик не определяются.']})


if __name__=='__main__':main()
