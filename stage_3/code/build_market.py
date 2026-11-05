"""Aggregate the market view without confusing heuristics and reviewed evidence."""
import json
import re
from market_research import ROOT, GROUPS, save, sha

OUT=ROOT/'research/market_20261105'


def build():
    data=json.loads((OUT/'overview.json').read_text(encoding='utf-8'))
    reviews=json.loads((OUT/'visual_reviews.json').read_text(encoding='utf-8'))
    editorial=json.loads((OUT/'editorial_reviews.json').read_text(encoding='utf-8'))
    for c in data['companies']:
        c['researcher_review']={'method':editorial['method'],'reviewed_on':editorial['reviewed_on'],
            **editorial['companies'].get(c['company_id'],{'assortment':'Нужен повторный сбор: текущий сайт недоступен.',
                'tone':'Тексты не получены, тон не оценивался.','promotion':'Не установлено по текущему сбору.'})}
        pages=json.loads((OUT/(c['company_id']+'_sources.json')).read_text(encoding='utf-8'))
        c['pages_ok']=len({p['final_url'].split('#')[0] for p in pages if p['status']=='ok'})
        c['assortment']=list({(x['category'],x['source_url'].split('#')[0],x['quote']):x for x in c['assortment']}.values())
        # A product link/title is a more useful inventory than isolated amount rows.
        offers={}
        for p in pages:
            if p['status']!='ok':continue
            for l in p['links']:
                label=l['label'].strip()
                if re.search(r'/journal/|/blog/|/articles/|/tpost/|/category/',l['url'],re.I):continue
                if len(label)<5 or len(label)>160:continue
                if re.search(r'политик|читать|все статьи|блог|подроб|отзыв|новост|стать партн|контакт|cookie',label,re.I):continue
                if any(re.search(pattern,label,re.I) for _,pattern in GROUPS.values()):
                    offers[(label,l['url'])]={'name':label,'url':l['url'],'found_on':p['final_url'],
                        'status':'site_link_label_not_verified_tariff','country_context':'derive_from_link_and_page_not_assumed_Portugal'}
        c['offer_inventory']=list(offers.values())[:60]
        c['offer_inventory_limit']=60
        c['visual']={**reviews['companies'][c['company_id']],
                      'method':reviews['method'],'reviewed_on':reviews['reviewed_on'],
                      'screenshot':'research-images/'+c['company_id']+'.png' if reviews['companies'][c['company_id']]['status'] not in ('unavailable',) else None}
        # Deduplicate identical Telegram entries discovered through several links.
        c['posts']=list({p['post_url']:p for p in c.get('posts',[])}.values())
        for p in c['posts']:
            p['topics']=[label for label,pattern in [('Иммиграция и документы',r'ВНЖ|виз|AIMA|паспорт|документ'),('Налоги и бизнес',r'налог|бизнес|компан|aut[oó]nomo'),('Жизнь и адаптация',r'праздник|кино|жизн|семь|город|культур'),('Изменения правил',r'изменен|закон|новост|ужесточ')]
                         if re.search(pattern,p['text'],re.I)] or ['Тема требует проверки']
            p['topic_method']='keyword_labels_for_navigation_not_semantic_analysis'
        c['publication_summary']={'telegram_sample':len(c['posts']),
            'sample_first':min((p['published_at'] for p in c['posts']),default=None),
            'sample_last':max((p['published_at'] for p in c['posts']),default=None),
            'frequency':'not_estimated_incomplete_sample','other_platforms':'Links found; feeds not read unless explicitly stated'}
        # Avoid interpreting legal financial thresholds as marketing guarantees.
        c['tone_signals']=[t for t in c['tone_signals'] if not (t['label']=='Заявления об успехе / гарантиях' and re.search(r'100% IPREM',t['quote']))]
    data['summary']={'companies_total':len(data['companies']),
        'companies_with_pages':sum(c['pages_ok']>0 for c in data['companies']),
        'pages_ok':sum(c['pages_ok'] for c in data['companies']),
        'channel_links':sum(len(c['channels']) for c in data['companies']),
        'telegram_posts':sum(len(c['posts']) for c in data['companies']),
        'companies_with_telegram_posts':sum(bool(c['posts']) for c in data['companies']),
        'editorial_pages':sum(sum(p['status']=='ok' for p in c['editorial']['pages']) for c in data['companies']),
        'visual_reviewed_or_limited':sum(c['visual']['status']!='unavailable' for c in data['companies'])}
    data['scope_notes']=['Ассортимент рассматривается шире отдельных одинаковых услуг: программы, документы, право, бизнес, налоги, недвижимость и адаптация.',
        'Инвентарь составлен из названий ссылок и заголовков; автоматические упоминания отделены от подтверждённого состава продукта.',
        'Найденная соцсеть — точка присутствия/контакта, не доказательство рекламного трафика. Платная реклама и эффективность не исследованы.',
        'Для тона показаны цитаты и лексические сигналы. Полноценная смысловая оценка всего корпуса ещё не завершена.',
        'Визуальные заметки сделаны помощником по реальным скриншотам первого экрана; не моделью и не анализатором CSS.',
        'Telegram: ограниченное публичное превью, до 8 сообщений на найденную ленту. Не равно частоте и полному календарю публикаций.']
    data['findings']=[
      {'title':'Сравнивать нужно несколько уровней предложения','text':'Общий каталог включает миграционные программы, административные услуги, право, бизнес и адаптацию. Один прайс-лист NIF не отражает эту линейку. В карточках доступны найденные названия предложений и исходные страницы.','companies':['immigration_relocator','e_residence','okno','monolite']},
      {'title':'Разные способы начать общение','text':'На первых экранах Relotus предлагает диагностический опрос; MigrAll — подбор ВНЖ и калькулятор; Immigration Relocator — стоимость сопровождения и консультацию. Гипотеза: проверить, какой вход понятнее разным сегментам клиентов, без утверждения о росте конверсии.','companies':['relotus','migrall','immigration_relocator']},
      {'title':'Контент работает не только как каталог услуг','text':'В полученном превью MoveToCascais встречаются культурные события и партнёрская акция; у Relotus — профессиональные и визовые темы. Это разные поводы для контакта. Расширять собственные рубрики стоит после проверки интересов аудитории, а не по числу постов неполной выборки.','companies':['movetocascais','relotus']},
      {'title':'Визуальные подходы различаются','text':'Фотография основателей у Immigration Relocator, продуктовые карточки e-residence и статусная тёмно-золотая подача DH Private задают разные ожидания. Выбирать оформление следует под сегмент и предложение; победитель по конверсии не измерялся.','companies':['immigration_relocator','e_residence','dh_private']}]
    save(OUT/'market.json',data)
    public=json.loads(json.dumps(data))
    (ROOT.parent/'docs/market-data.js').write_bytes(('window.MARKET_DATA = '+json.dumps(public,ensure_ascii=False,separators=(',',':'))+';\n').encode())
    print(json.dumps(data['summary'],ensure_ascii=False))


if __name__=='__main__':build()
