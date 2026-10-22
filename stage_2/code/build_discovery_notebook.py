"""Standalone first-step Colab, preserves human confirmation boundary."""
import ast
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
assets={name:(root/'code'/name).read_text(encoding='utf-8') for name in ['collector.py','discovery.py','config.json']}
cells=[]
def md(text): cells.append({'cell_type':'markdown','metadata':{},'source':text.splitlines(True)})
def code(text):
    ast.parse(text)
    cells.append({'cell_type':'code','metadata':{},'source':text.splitlines(True),'execution_count':None,'outputs':[]})
md('# Шаг 1. Профиль компании и план поиска конкурентов\n\nЭтот ноутбук получает сайт, предлагает профиль с источниками, запрашивает подтверждение и формирует поисковые запросы. Поисковый API ещё не подключён: запросы не выдаются за найденные компании. Для текущего пилота профиль и восемь конкурентов уже подтверждены; повторный интерактивный сценарий нужен для демонстрации и новых компаний.\n\nКлюч только из Colab Secrets PROXYAPI_KEY. Стартовая модель Luna проверяется по каталогу. Пробный запуск модулей Luna выполнен 22.10.2026 в основном ноутбуке; новый профиль остаётся черновиком, а запросы построены по ранее подтверждённому ручному профилю. Этот интерактивный ноутбук при новом запуске требует собственного подтверждения профиля.')
code('import sys, subprocess\nsubprocess.check_call([sys.executable,"-m","pip","install","-q","requests>=2.32,<3","beautifulsoup4>=4.12,<5","jsonschema>=4.23,<5"])\n')
code('from pathlib import Path\nimport json,sys\nWORKDIR=Path("/content/company_discovery")\nWORKDIR.mkdir(exist_ok=True)\nASSETS='+repr(assets)+'\nfor name,text in ASSETS.items():\n    (WORKDIR/name).write_text(text,encoding="utf-8")\nsys.path.insert(0,str(WORKDIR))\n')
code('''def main(workdir, website=None, company_name=None):
    from collector import read_json, save_json, start_collection, load_colab_key, list_models, normalize_url
    from discovery import propose_profile, confirm_profile, propose_queries
    workdir=Path(workdir)
    settings=read_json(workdir/"config.json")
    website=website or input("Сайт компании: ").strip()
    if not normalize_url(website): raise ValueError("Нужен корректный HTTP(S) URL")
    company_name=company_name or input("Название компании: ").strip()
    social=input("Необязательные публичные соцсети через запятую (Enter — пропустить): ").strip()
    company={"id":"own_company","name":company_name,"role":"own_company","seed_urls":[website]}
    config={**settings["collection"],"purpose":"own_company_profile","selected_ids":["own_company"],"pages_per_company":4,"profile_confirmed":False,"competitors_confirmed":False}
    run=start_collection(config,[company],workdir/"runs")
    save_json(run/"user_input.json",{"company":company,"social_urls_supplied":[s.strip() for s in social.split(",") if s.strip()]})
    key=load_colab_key()
    try:
        model=settings["model_policy"]["stages"]["company_profile"]["preferred_model"]
        if model not in list_models(settings["llm"]["base_url"],key): raise ValueError("Предпочтительная модель недоступна; выберите доступную в config.json")
        profile=propose_profile(run,"own_company",key,model,settings["llm"]["base_url"])
        print(json.dumps(profile,ensure_ascii=False,indent=2))
        additions=input("Ручные исправления/приоритеты профиля: ").strip()
        approval=input("Подтверждаете профиль с этими поправками? Напишите ПОДТВЕРЖДАЮ: ").strip()=="ПОДТВЕРЖДАЮ"
        confirmed=confirm_profile(profile,additions,approval)
        save_json(run/"discovery/profile_confirmed.json",confirmed)
        countries=[x.strip() for x in input("Страны для поиска через запятую: ").split(",") if x.strip()]
        query_model=settings["model_policy"]["stages"]["search_queries"]["preferred_model"]
        if query_model not in list_models(settings["llm"]["base_url"],key): raise ValueError("Модель поисковых запросов недоступна")
        result=propose_queries(confirmed,key,query_model,settings["llm"]["base_url"],run/"discovery",countries)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        print("План поиска сохранён. Поиск ещё не выполнен; конкуренты не подтверждены.")
    finally:
        del key
    return str(run)

RUN_DIR=main(WORKDIR)
''')
for index,cell in enumerate(cells): cell['id']=f'discovery_{index:02}'
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'cells':cells}
path=root/'code/Шаг_1_профиль_и_поисковые_запросы.ipynb'
path.write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding='utf-8')
print(path)
