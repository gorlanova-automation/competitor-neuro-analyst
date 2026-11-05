"""Reproducible broad research notebook; no new web/LLM calls by default."""
import base64
import hashlib
import io
import json
import lzma
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def build():
    payload=io.BytesIO()
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED) as archive:
        paths=[ROOT/'config.json',*(ROOT/'input').rglob('*'),*(ROOT/'cases').rglob('*.json'),*(ROOT/'research').rglob('*.json'),*(ROOT/'code').glob('*.py')]
        for p in paths:
            if p.is_file():archive.write(p,'stage_3/'+p.relative_to(ROOT).as_posix())
        for p in (ROOT.parent/'app').glob('*.py'):archive.write(p,'app/'+p.name)
    packed=lzma.compress(payload.getvalue());encoded=base64.b64encode(packed).decode();cells=[]
    def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
    def code(s):cells.append({'cell_type':'code','metadata':{'cellView':'form'},'source':s.splitlines(True),'outputs':[],'execution_count':None})
    md('# Ассортимент и продвижение · этап 3\n\nСохранённый сбор 05.11.2026: 12 компаний, широкий ассортимент, площадки, редакционные страницы, Telegram и заметки о визуальной подаче. Это ограниченный сбор, не полный маркетинговый аудит.\n\n**Код** собирает/проверяет источники и выделяет сигналы. **Помощник** написал отдельно помеченные смысловые и визуальные заметки. **Человек** подтверждает выводы. Платных LLM-вызовов в этом прогоне нет. Повторное исследование сайтов выключено по умолчанию.')
    code('''#@title 1. Подготовить воспроизводимое окружение
import base64,hashlib,io,json,lzma,pathlib,subprocess,sys,zipfile
subprocess.check_call([sys.executable,'-m','pip','install','-q','requests>=2.32,<3','beautifulsoup4>=4.12,<5','fastapi==0.162.0','uvicorn==0.54.0','httpx==0.28.1'])
PACKED="""'''+encoded+'''"""
blob=base64.b64decode(PACKED)
assert hashlib.sha256(blob).hexdigest()=="'''+hashlib.sha256(packed).hexdigest()+'''"
WORK=pathlib.Path.cwd()/'market_research_demo';WORK.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(lzma.decompress(blob))) as archive:
    for name in archive.namelist():assert (WORK/name).resolve().is_relative_to(WORK.resolve())
    archive.extractall(WORK)
ROOT=WORK/'stage_3';sys.path.insert(0,str(WORK));sys.path.insert(0,str(ROOT/'code'))
from analyst import read,verify_inputs
verify_inputs(ROOT)
MARKET=read(ROOT/'research/market_20261105/market.json')
print('Снимки распакованы. Новых LLM-вызовов: 0.')
''')
    code('''#@title 2. Проверить широкое покрытие
print(json.dumps(MARKET['summary'],ensure_ascii=False,indent=2))
for c in MARKET['companies']:
    print(c['name'],'страниц:',c['pages_ok'],'соцссылок:',len(c['channels']),'Telegram:',len(c['posts']),'визуал:',c['visual']['status'])
print('Ноль полученных публикаций НЕ означает отсутствия публикаций компании.')
print('Историческая выборка Migrun хранится отдельно и не выдаётся за свежий сбор.')
''')
    code('''#@title 3. Изучить компанию: ассортимент, продвижение, тон, визуал
COMPANY='immigration_relocator' #@param ['immigration_relocator','migrun','migran','relotus','relocate_group','e_residence','dh_private','migrall','movetocascais','portugaldom','monolite','okno']
C=next(c for c in MARKET['companies'] if c['company_id']==COMPANY)
print(C['name'])
print('ИНТЕРПРЕТАЦИЯ ПОМОЩНИКА:',json.dumps(C['researcher_review'],ensure_ascii=False,indent=2))
print('НАЗВАНИЯ ПРЕДЛОЖЕНИЙ:',json.dumps(C['offer_inventory'],ensure_ascii=False,indent=2))
print('ПЛОЩАДКИ:',json.dumps([{k:x.get(k) for k in ['platform','url','found_on','posts_status','purpose']} for x in C['channels']],ensure_ascii=False,indent=2))
for x in C['tone_signals']:print('СИГНАЛ ТОНА:',x['label'],'\\nЦитата:',x['quote'],'\\nИсточник:',x['source_url'])
print('ВИЗУАЛ: ручной просмотр первого экрана, не LLM:',json.dumps(C['visual'],ensure_ascii=False,indent=2))
print('Скриншоты: https://gorlanova-automation.github.io/competitor-neuro-analyst/market.html#visual')
''')
    code('''#@title 4. Проверить публикации и происхождение данных
for c in MARKET['companies']:
    if c['posts']:
        print('\\nКОМПАНИЯ:',c['name'])
        for p in c['posts'][:2]:print(p['published_at'],p['post_url'],'\\n',p['text'][:1200])
import unittest
suite=unittest.defaultTestLoader.discover(str(ROOT/'code'),pattern='test_*.py')
suite.addTests(unittest.defaultTestLoader.discover(str(WORK/'app'),pattern='test_api.py',top_level_dir=str(WORK)))
outcome=unittest.TextTestRunner(verbosity=1,stream=sys.stdout).run(suite)
assert outcome.wasSuccessful()
print('PASS:',outcome.testsRun,'тестов; новых LLM-вызовов: 0')
''')
    md('## Дополнения и повторное исследование\n\nКаталог компаний: stage_3/input/companies.json. Новые компании должны быть подтверждены пользователем; новые цитаты, тексты и даты нельзя выдавать за прежний снимок. Сбор сайтов/лент выполняется market_research.py и promotion_research.py. Они могут вернуть недоступность. Визуальные заметки visual_reviews.json и смысловые editorial_reviews.json нужно обновлять после фактического просмотра, не проставлять автоматически новую дату.\n\nСкачанный JSON можно изучить на стенде; пользовательское подтверждение профиля SHIFT остаётся отдельным процессом. Частота публикаций, стоимость трафика, реклама, конверсия и смысловая разметка всего рынка этим запуском не доказаны.')
    for i,c in enumerate(cells):c['id']='market_'+str(i)
    nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','language':'python','display_name':'Python 3'},'colab':{'name':'Этап_3_ассортимент_и_продвижение.ipynb'},'execution_provenance':'Built, not yet executed; verify actual Colab outputs separately.'},'cells':cells}
    dest=ROOT/'Этап_3_ассортимент_и_продвижение.ipynb';dest.write_bytes(json.dumps(nb,ensure_ascii=False,indent=1).encode())
    print('Built',dest.name,dest.stat().st_size)


if __name__=='__main__':build()
