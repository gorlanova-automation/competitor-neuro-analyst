"""Interactive demonstration and new research, with explicit checkpoints."""
import json
import sys
from pathlib import Path
from stage_4.workflow import run_project,WorkflowError,public_url


def launch_colab(output_dir='var/projects'):
    from IPython.display import display,HTML
    print('Новый проект. Ключ не нужен для сбора и текстовой выборки.')
    url=input('HTTPS-адрес собственной компании: ').strip()
    uploads={}
    if input('Загрузить TXT страницы вместо HTTP? да/нет [нет]: ').strip().lower()=='да':
        from google.colab import files
        data=files.upload()
        if len(data)!=1:raise WorkflowError('Загрузите один TXT-файл.')
        uploads[public_url(url)]={'text':next(iter(data.values())).decode('utf-8-sig')}
    state=run_project(website_url=url,output_dir=output_dir,uploads=uploads)
    print(json.dumps(state,ensure_ascii=False,indent=2))
    if state['profile'] is None:
        print('Источник недоступен. Повторите запуск с TXT-файлом; предыдущий результат сохранён.');return state
    draft=state['profile']
    print('Проверьте черновик. Enter сохраняет предложенное значение.')
    profile={key:input(label+' ['+draft.get(key,'')+']: ').strip() or draft.get(key,'')
             for key,label in [('company_name','Название'),('summary','Описание'),('market_scope','Рынок, язык и аудитория'),('search_terms','Поисковые слова')]}
    if input('Подтверждаете профиль? Напишите да: ').strip().lower()!='да':return state
    state=run_project(project_id=state['id'],profile=profile,action='confirm_profile',output_dir=output_dir)
    print('Поисковые запросы:',*state['search_queries'],sep='\n')
    if input('Попробовать автоматический поиск кандидатов? да/нет [нет]: ').strip().lower()=='да':
        state=run_project(project_id=state['id'],action='search',output_dir=output_dir)
        print(json.dumps(state.get('search'),ensure_ascii=False,indent=2))
    urls=[u.strip() for u in input('Сайты выбранных конкурентов, через запятую (1–10): ').split(',') if u.strip()]
    print('Будут исследованы:',urls)
    if input('Подтверждаете этот список? Напишите да: ').strip().lower()!='да':return state
    state=run_project(project_id=state['id'],competitor_urls=urls,action='confirm_competitors',output_dir=output_dir)
    state=run_project(project_id=state['id'],action='collect',uploads=uploads,output_dir=output_dir,max_pages=4)
    print('Сбор завершён:',json.dumps(state['report'],ensure_ascii=False))
    if input('Добавить смысловой анализ? Один вызов ProxyAPI, максимум 2500 токенов ответа. да/нет [нет]: ').strip().lower()=='да':
        key=None
        try:
            from google.colab import userdata
            key=userdata.get('PROXYAPI_KEY')
            state=run_project(project_id=state['id'],action='analyze',api_key=key,output_dir=output_dir)
        except Exception:
            print('Модельный шаг не завершён. Проверьте подключение Colab и доступ к секрету. Отчёт сбора сохранён; автоматического повторного запроса нет.')
        finally:key=None
    folder=Path(output_dir)/state['id']/'runs'/state['report']['run_id']
    display(HTML((folder/'report.html').read_text(encoding='utf-8')))
    print('HTML и JSON:',folder)
    if input('Скачать отчёт и источники ZIP? да/нет [да]: ').strip().lower()!='нет':
        import shutil
        from google.colab import files
        archive=shutil.make_archive(str(folder.parent.parent/'result'),'zip',root_dir=folder)
        files.download(archive)
    return state


def run_saved_demo(project_root='.',output_dir='var/demo_projects',case='immigration'):
    """Reproducible real saved texts. Not a fresh collection or human approval."""
    root=Path(project_root)
    if case=='immigration':
        market=root/'stage_3/research/market_20261105'
        own=next(s for s in json.loads((market/'immigration_relocator_sources.json').read_text(encoding='utf-8')) if s['status']=='ok')
        rival=next(s for s in json.loads((market/'okno_sources.json').read_text(encoding='utf-8')) if s['status']=='ok')
        name='Immigration Relocator';scope='Португалия и Испания; русскоязычные клиенты';terms='релокация ВНЖ документы'
    else:
        own=json.loads((root/'stage_3/cases/shift/own_source.json').read_text(encoding='utf-8'))
        rival=next(s for s in json.loads((root/'stage_3/cases/shift/candidate_sources.json').read_text(encoding='utf-8')) if s.get('sha256_text'))
        name='SHIFT';scope='Демонстрационный рынок коротких видео; аудитория требует пользовательского уточнения';terms='AI short video analysis feedback'
    own_url=own.get('requested_url') or own.get('url');rival_url=rival.get('requested_url') or rival.get('url')
    uploads={public_url(url):{'text':source['text'],'title':source['title'],'description':source.get('description','')}
             for url,source in [(own_url,own),(rival_url,rival)]}
    state=run_project(website_url=own_url,output_dir=output_dir,uploads=uploads)
    state=run_project(project_id=state['id'],action='confirm_profile',output_dir=output_dir,
        profile={'company_name':name,'summary':own.get('description') or own['text'][:300],
                 'market_scope':scope+' [Автоматическая демонстрация, не подтверждение пользователем]','search_terms':terms})
    state=run_project(project_id=state['id'],action='confirm_competitors',competitor_urls=[rival_url],output_dir=output_dir)
    state=run_project(project_id=state['id'],action='collect',uploads=uploads,max_pages=1,output_dir=output_dir)
    return state
