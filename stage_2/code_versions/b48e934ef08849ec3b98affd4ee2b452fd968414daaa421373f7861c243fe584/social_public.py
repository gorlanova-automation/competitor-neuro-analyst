"""Optional public Telegram preview adapter. Does not log in or bypass gates."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
import re
from bs4 import BeautifulSoup
from collector import fetch_public, robots_check, save_json, digest, utc_now, append_event


def collect_telegram_preview(channel_url, company_id, found_on, run_dir, config, max_pages=5):
    """User must review ownership before these posts feed company comparisons.

    max_pages limits retrieval, max_posts limits selected posts, calendar window
    is inclusive. Pinned/repeated post IDs are deduplicated. Missing dates excluded.
    """
    host = (urlsplit(channel_url).hostname or '').lower()
    channel = urlsplit(channel_url).path.strip('/').removeprefix('s/').split('/')[0]
    if host != 't.me' or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{3,}',channel) or channel.lower().endswith('bot'):
        raise ValueError('Нужен URL публичного Telegram-канала; бот/личный контакт не лента')
    run_dir=Path(run_dir)
    (run_dir/'social').mkdir(exist_ok=True)
    now=datetime.now(timezone.utc)
    start=now.date()-timedelta(days=config['social_days']-1)
    posts, events, before, seen, cache = [], [], None, set(), {}
    reached_start=False
    for page_number in range(max_pages):
        url='https://t.me/s/'+channel+(f'?before={before}' if before else '')
        allowed,mode=robots_check(url,config,cache,run_dir)
        if not allowed:
            events.append({'url':url,'status':'robots_disallowed_or_unavailable','robots_mode':mode})
            break
        response=fetch_public(url,config['timeout'],config['max_bytes'],config['user_agent'])
        raw=response.pop('raw')
        file_path=run_dir/'social'/(company_id+'_'+channel+f'_{page_number:02}.html')
        file_path.write_bytes(raw)
        event={'url':url,'collected_at':utc_now(),'sha256':digest(raw),'raw_path':str(file_path.relative_to(run_dir)),**response}
        soup=BeautifulSoup(raw.decode('utf-8',errors='replace'),'html.parser')
        items=soup.select('.tgme_widget_message[data-post]') if response['status']=='ok' else []
        if not items:
            event['status']='no_public_posts_or_contact_not_channel'
            events.append(event)
            break
        ids=[]
        for item in items:
            post_key=item.get('data-post','')
            if post_key in seen:
                continue
            seen.add(post_key)
            try:
                post_id=int(post_key.rsplit('/',1)[1]); ids.append(post_id)
                timestamp=item.select_one('time[datetime]')['datetime']
                published=datetime.fromisoformat(timestamp.replace('Z','+00:00'))
            except (ValueError,TypeError,KeyError):
                continue
            if published.date()<start:
                reached_start=True
                continue
            if published.date()>now.date():
                continue
            text_node=item.select_one('.tgme_widget_message_text')
            text=text_node.get_text('\n',strip=True) if text_node else ''
            formats=[]
            for selector,label in [('.tgme_widget_message_photo_wrap','photo'),('.tgme_widget_message_video','video'),('.tgme_widget_message_document','document'),('.tgme_widget_message_poll','poll')]:
                if item.select_one(selector): formats.append(label)
            posts.append({'company_id':company_id,'channel_url':channel_url,'found_on':found_on,'ownership_status':'pending_human_review','post_url':'https://t.me/'+post_key,'published_at':published.isoformat(),'collected_at':utc_now(),'text':text,'format':formats or ['text'],'topic':None,'topic_origin':'not_yet_extracted','method':'python_public_telegram_preview','raw_path':str(file_path.relative_to(run_dir))})
        events.append(event)
        if reached_start or len(posts)>=config['social_max_posts'] or not ids:
            break
        next_before=min(ids)
        if before is not None and next_before>=before:
            break
        before=next_before
    posts=sorted(posts,key=lambda x:x['published_at'],reverse=True)[:config['social_max_posts']]
    result={'company_id':company_id,'channel_url':channel_url,'found_on':found_on,'ownership_status':'pending_human_review','window_start':str(start),'window_end':str(now.date()),'max_posts':config['social_max_posts'],'max_pages':max_pages,'count':len(posts),'actual_first':min((p['published_at'] for p in posts),default=None),'actual_last':max((p['published_at'] for p in posts),default=None),'reached_window_start':reached_start,'coverage':'bounded_preview_not_proven_complete','pages':events,'posts':posts}
    path=run_dir/'social'/(company_id+'_'+channel+'_posts.json')
    save_json(path,result)
    append_event(run_dir,{'action':'telegram_preview','company_id':company_id,'channel_url':channel_url,'count':len(posts),'ownership_status':'pending_human_review','output':str(path.relative_to(run_dir))})
    return result
