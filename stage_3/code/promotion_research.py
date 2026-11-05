"""Public-feed and article sampling from links discovered on official sites."""
import concurrent.futures
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
import requests
from market_research import ROOT, UA, fetch, save, utc, sha, host

OUT=ROOT/'research/market_20261105'


def telegram(link,cid):
    name=urlsplit(link['url']).path.strip('/').split('/')[0]
    row={**link,'company_id':cid,'checked_at':utc(),'posts':[]}
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{3,}',name) or name.lower().endswith('bot') or name=='USERNAME_BOT':
        row.update(purpose='contact_invite_or_bot',posts_status='not_a_public_feed');return row
    session=requests.Session();session.headers['User-Agent']=UA
    url='https://t.me/s/'+name
    try:
        p=fetch(session,url,{})
        if p['status']!='ok':row.update(posts_status=p['status']);return row
        # Fetch the same public response to parse message boundaries, not flattened text.
        r=session.get(url,timeout=25);r.raise_for_status()
        soup=BeautifulSoup(r.content,'html.parser')
        for item in soup.select('.tgme_widget_message[data-post]')[-8:]:
            text=item.select_one('.tgme_widget_message_text');date=item.select_one('time[datetime]')
            body=text.get_text(' ',strip=True) if text else ''
            if not body or not date:continue
            media=[]
            for selector,label in [('.tgme_widget_message_photo_wrap','photo'),('.tgme_widget_message_video','video'),('.tgme_widget_message_document','document')]:
                if item.select_one(selector):media.append(label)
            row['posts'].append({'company_id':cid,'post_url':'https://t.me/'+item['data-post'],
                'published_at':date['datetime'],'text':body,'sha256_text':sha(body),'formats':media or ['text'],
                'collected_at':utc(),'source_url':url,'ownership_status':'linked_from_official_site_not_independently_verified'})
        row.update(purpose='public_feed' if row['posts'] else 'contact_or_unavailable_feed',
                   posts_status='sample_collected' if row['posts'] else 'no_public_messages_observed',
                   coverage='latest_visible_page_max_8_posts_no_frequency_estimate')
    except requests.RequestException as exc:row.update(posts_status='collection_error',error_type=type(exc).__name__)
    return row


def articles(company):
    session=requests.Session();session.headers['User-Agent']=UA
    policies={};results=[];seen=set()
    links=company['content_links']
    # Prefer an editorial index over incidental mentions of the word "article".
    index=next((x for x in links if re.search(r'blog/?$|articles/?$|journal/?$|poleznie-statii/?$|category/news/?$',x['url'])),None)
    queue=[index['url']] if index else []
    queue += [x['url'] for x in links if x['url'] not in queue][:2]
    while queue and len(results)<3:
        url=queue.pop(0)
        if url in seen:continue
        seen.add(url)
        try:p=fetch(session,url,policies)
        except (requests.RequestException,ValueError) as exc:p={'url':url,'status':'collection_error','error_type':type(exc).__name__}
        results.append(p)
        if p['status']=='ok' and len(results)==1:
            for link in p['links']:
                path=urlsplit(link['url']).path
                if host(link['url'])==host(url) and re.search(r'/blog/.+|/journal/.+|/articles/.+|/news/.+',path) and not re.search(r'category|page/\d|privacy',path):
                    if link['url'] not in queue:queue.append(link['url'])
    save(OUT/(company['company_id']+'_editorial.json'),results)
    return {'company_id':company['company_id'],'pages':[{k:v for k,v in p.items() if k not in ('text','links','image_metadata')} for p in results],
        'status':'sample_collected' if any(p['status']=='ok' for p in results) else 'not_collected',
        'note':'Index and bounded article sample; no claim of exhaustive publication history or frequency.'}


def main():
    import json
    data=json.loads((OUT/'overview.json').read_text(encoding='utf-8'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(telegram,l,c['company_id']) for c in data['companies'] for l in c['channels'] if l['platform']=='Telegram']
        feeds=[f.result() for f in futures]
        editorial=list(pool.map(articles,data['companies']))
    for c in data['companies']:
        checked={r['url']:r for r in feeds if r['company_id']==c['company_id']}
        c['channels']=[checked.get(r['url'],r) for r in c['channels']]
        c['editorial']=next(r for r in editorial if r['company_id']==c['company_id'])
        c['posts']=[p for r in checked.values() for p in r['posts']]
        c['promotion_status']='site_and_linked_channels_sampled' if c['pages_ok'] else 'collection_blocked'
    save(OUT/'feeds.json',feeds)
    save(OUT/'overview.json',data)
    print('Public posts:',sum(len(c['posts']) for c in data['companies']),
          'companies:',sum(bool(c['posts']) for c in data['companies']),flush=True)
    for c in data['companies']:print(c['name'],len(c['posts']),'posts;',c['editorial']['status'],flush=True)


if __name__=='__main__':main()
