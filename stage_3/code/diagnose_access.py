"""Recheck failed sites and linked social profiles; emit actionable queue."""
import concurrent.futures
import json
from urllib.parse import urlsplit,urlunsplit
import requests
from market_research import ROOT,UA,save,utc
from resilient_fetch import fetch

OUT=ROOT/'research/access_20261105'


def probe(task):
    session=requests.Session();session.headers['User-Agent']=UA
    policies={};tried=[]
    urls=[task['url']]+task.get('verified_alternatives',[])
    # Same apex only; never guess an alternative brand/domain.
    parts=urlsplit(task['url'])
    if task.get('allow_apex_fallback') and parts.hostname.startswith('www.'):
        urls.append(urlunsplit((parts.scheme,parts.netloc[4:],parts.path,parts.query,'')))
    for url in dict.fromkeys(urls):
        page=fetch(session,url,policies);tried.append(page)
        if page['status']=='ok':break
        if page['status']=='robots_disallowed':break
    row={**task,'checked_at':utc(),'attempted_urls':len(tried),'results':tried,
         'status':tried[-1]['status'],'next_action':tried[-1].get('next_action'),
         'cause':tried[-1].get('failure_kind',tried[-1]['status']),
         'recovered':any(p['status']=='ok' for p in tried)}
    save(OUT/(task['company_id']+'_'+task['kind']+'.json'),row)
    print(task['company_id'],task['kind'],row['status'],flush=True)
    return row


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    market=json.loads((ROOT/'research/market_20261105/market.json').read_text(encoding='utf-8'))
    tasks=[{'company_id':'immigration_relocator','kind':'control_website','url':'https://immigration-relocator.com/'},
           {'company_id':'migran','kind':'website','url':'https://www.migran.es/','allow_apex_fallback':True},
           {'company_id':'relocate_group','kind':'website','url':'https://relocate-legal.com/',
            'verified_alternatives':['https://relocate-legal.com/o-nas/','https://relocate-legal.com/o-nas/kontakti/'],
            'alternative_provenance':'Official URLs verified in web search 2026-11-05; not alternate brands'}]
    for c in market['companies']:
        platforms=set()
        for link in c['channels']:
            if link['platform'] not in ('Instagram','Facebook') or link['platform'] in platforms:continue
            platforms.add(link['platform'])
            tasks.append({'company_id':c['company_id'],'kind':link['platform'].lower(),
                          'url':link['url'],'found_on':link['found_on']})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(probe,tasks))
    summary={'checked_at':utc(),'collector_version':'resilient_v2','items':[{k:v for k,v in r.items() if k!='results'} for r in rows],
             'browser_review_queue':[{'company_id':r['company_id'],'kind':r['kind'],'url':r['url'],
                 'reason':r['status'],'next_action':r['next_action']} for r in rows if not r['recovered']],
             'limits':['HTTP success does not establish a readable social feed.','No login, CAPTCHA or robots bypass.',
                       'Browser review queue is not a completed browser capture.']}
    save(OUT/'summary.json',summary)
    (ROOT.parent/'docs/access-data.js').write_bytes(('window.ACCESS_DIAGNOSTICS = '+json.dumps(summary,ensure_ascii=False,separators=(',',':'))+';\n').encode())


if __name__=='__main__':main()
