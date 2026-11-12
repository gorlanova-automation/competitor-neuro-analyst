"""Interactive Colab runner that exports the same result shown by Pages."""
import json
import os
import time
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app


def launch(output_dir='var/colab_product'):
    from google.colab import files,userdata
    print('Сайт → профиль → кандидаты → ваш список → сбор → JSON для GitHub Pages.')
    print('LLM не вызывается. Автопоиск — один Tavily basic-запрос, 1 кредит; без повторов.')
    names=('TAVILY_API_KEY','ANALYST_SEARCH_ENABLED','ANALYST_SEARCH_PROVIDER','ANALYST_SEARCH_BUDGET_FILE')
    previous={n:os.environ.get(n) for n in names}
    os.environ['ANALYST_SEARCH_ENABLED']='0'
    try:
        with TestClient(create_app(output_dir)) as client:
            def run(body,identifier=None):
                response=client.post('/api/research'+('/'+identifier if identifier else ''),json=body)
                response.raise_for_status()
                for _ in range(1200):
                    job=client.get('/api/jobs/'+response.json()['id']).json()
                    if job['status'] not in ('queued','running'):break
                    time.sleep(.5)
                if job['status']!='succeeded':raise RuntimeError(job.get('error','Не завершено; исходные материалы сохранены.'))
                return client.get('/api/research/'+job['project_id']).json()
            url=input('HTTPS-сайт своей компании: ').strip()
            uploads={}
            if input('Предоставить TXT вместо загрузки сайта? да/нет [нет]: ').strip().lower()=='да':
                data=files.upload()
                if len(data)!=1:raise ValueError('Нужен один TXT-файл.')
                uploads[url]={'text':next(iter(data.values())).decode('utf-8-sig')}
            state=run({'action':'start','website_url':url,'uploads':uploads})
            if not state.get('profile'):
                print('Сайт недоступен. Повторите запуск с TXT; не делаем вывод об отсутствии услуг.');return state
            profile={}
            for name,label in [('company_name','Название'),('summary','Описание'),('market_scope','Рынок и аудитория'),('search_terms','Поисковые слова')]:
                draft=state['profile'].get(name,'');profile[name]=input(label+' ['+draft+']: ').strip() or draft
            if input('Подтвердить профиль? да: ').strip().lower()!='да':return state
            if input('Один запрос Tavily из бесплатного лимита? да/нет [нет]: ').strip().lower()=='да':
                try:
                    os.environ['TAVILY_API_KEY']=userdata.get('TAVILY_API_KEY')
                    os.environ['ANALYST_SEARCH_ENABLED']='1';os.environ['ANALYST_SEARCH_PROVIDER']='tavily'
                    os.environ['ANALYST_SEARCH_BUDGET_FILE']=str(Path(output_dir)/'search_budget.json')
                except Exception:print('Секрет недоступен. Продолжаем с ручным списком.')
            state=run({'action':'confirm_profile','profile':profile},state['id'])
            os.environ['ANALYST_SEARCH_ENABLED']='0'
            print('Поиск:',state.get('search',{}).get('status'))
            print('Это кандидаты, включая статьи и публикации. Проверьте компанию и основной сайт:')
            for c in state.get('suggestions',[]):print(c['name'],c['url'],c.get('origin',''))
            print('Введите окончательный список: Название | https://сайт/ . Пустая строка завершает ввод.')
            competitors=[]
            for _ in range(20):
                line=input('Компания | HTTPS-адрес: ').strip()
                if not line:break
                if '|' not in line:raise ValueError('Разделите название и адрес знаком |.')
                name,target=line.split('|',1);competitors.append({'name':name.strip(),'url':target.strip()})
            print(json.dumps(competitors,ensure_ascii=False,indent=2))
            if input('Подтвердить именно этот список и начать сбор? да: ').strip().lower()!='да':return state
            state=run({'action':'confirm_competitors','competitors':competitors},state['id'])
            state=run({'action':'collect','max_pages':2,'uploads':uploads},state['id'])
            result=client.get('/api/research/'+state['id']+'/result').json()
            target=Path(output_dir)/state['id']/'product-result.json'
            target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print('Готово. Компаний:',len(result['companies']),'; страниц:',sum(c['pages_ok'] for c in result['companies']))
            print('Предложения — гипотезы для проверки. Откройте JSON на https://gorlanova-automation.github.io/competitor-neuro-analyst/')
            files.download(str(target))
            return state
    finally:
        for name,value in previous.items():
            if value is None:os.environ.pop(name,None)
            else:os.environ[name]=value
