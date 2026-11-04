"""Package current code and snapshots for a genuine, offline-safe Colab run."""
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
        paths=[ROOT/'config.json',*(ROOT/'input').rglob('*'),*(ROOT/'cases').rglob('*.json')]
        paths += list((ROOT/'code').glob('*.py'))
        for p in paths:
            if p.is_file(): archive.write(p,'stage_3/'+p.relative_to(ROOT).as_posix())
        for p in (ROOT.parent/'app').glob('*.py'):
            archive.write(p,'app/'+p.name)
    packed=lzma.compress(payload.getvalue())
    encoded=base64.b64encode(packed).decode()
    cells=[]
    def md(s): cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
    def code(s): cells.append({'cell_type':'code','metadata':{},'source':s.splitlines(True),'outputs':[],'execution_count':None})
    md('# Этап 3 · два проекта\n\nImmigration Relocator: 11 конкурентов, 9 критериев, 30 наблюдений. SHIFT: отдельный профиль и кандидаты с обязательной проверкой человеком.\n\nВстроены реальные сохранённые снимки. По умолчанию новых LLM-запросов нет. Старые данные 22.10 и дополнения 04.11.2026 различаются датами источников. Это новый исследовательский ноутбук; старый Colab остаётся историей предыдущего этапа.')
    code('''#@title 1. Подготовить окружение и распаковать сохранённые данные
import base64, hashlib, io, json, lzma, pathlib, subprocess, sys, zipfile
subprocess.check_call([sys.executable,'-m','pip','install','-q','requests>=2.32,<3','beautifulsoup4>=4.12,<5','fastapi==0.162.0','uvicorn==0.54.0','httpx==0.28.1'])
PACKED="""'''+encoded+'''"""
data=base64.b64decode(PACKED)
assert hashlib.sha256(data).hexdigest()=="'''+hashlib.sha256(packed).hexdigest()+'''"
WORK=pathlib.Path.cwd()/'stage3_two_cases'
WORK.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(lzma.decompress(data))) as archive:
    for name in archive.namelist():
        assert (WORK/name).resolve().is_relative_to(WORK.resolve())
    archive.extractall(WORK)
ROOT=WORK/'stage_3'
sys.path.insert(0,str(WORK)); sys.path.insert(0,str(ROOT/'code'))
from analyst import read, run, verify_inputs
verify_inputs(ROOT)
print('Целостность снимков подтверждена. Новых LLM-вызовов: 0.')
''')
    code('''#@title 2. Запустить анализ релокации
COUNTRY='Portugal' #@param ['Portugal','Spain']
CONFIG=read(ROOT/'config.json'); CONFIG['country']=COUNTRY
RESULT=run(ROOT,CONFIG,ROOT/'results/current')
print('Конкурентов:',len(CONFIG['competitors']))
print('Критериев:',len(RESULT['criteria']),'наблюдений:',len(RESULT['evidence']),'гипотез:',len(RESULT['recommendations']))
for c in RESULT['coverage']: print(c['name'],c['facts_in_demo'],c['status'],c.get('added_by'))
from IPython.display import HTML, display
display(HTML((ROOT/'results/current/report.html').read_text(encoding='utf-8')))
''')
    code('''#@title 3. Прогнать тесты движка, другой отрасли и API
import unittest
suite=unittest.defaultTestLoader.discover(str(ROOT/'code'),pattern='test_*.py')
suite.addTests(unittest.defaultTestLoader.discover(str(WORK/'app'),pattern='test_api.py',top_level_dir=str(WORK)))
outcome=unittest.TextTestRunner(verbosity=2,stream=sys.stdout).run(suite)
assert outcome.wasSuccessful()
print('PASS:',outcome.testsRun,'тестов; LLM-вызовов: 0')
''')
    md('## Здесь нужен человек\n\nПроверьте профиль SHIFT, рынок и кандидатов. Они не подтверждены автоматически. Retensis и Acuity имеют сохранённые страницы; Pacing — только кандидат из поиска, прямой сбор не удался. Новые URL сначала надо собрать. Проверка в тестах использует искусственное подтверждение только для отрицательных сценариев и не считается вашим согласием.')
    code('''#@title 4. Проверить профиль и обязательную остановку
from profile_site import draft_profile
from review_case import analyze_case
PROFILE=draft_profile(read(ROOT/'cases/shift/own_source.json'))
print(json.dumps(PROFILE,ensure_ascii=False,indent=2))
print(json.dumps(read(ROOT/'cases/shift/result.json')['candidates'],ensure_ascii=False,indent=2))
SHIFT=analyze_case(ROOT/'cases/shift')
assert SHIFT['status']=='needs_user_review'
print('Нужно ваше действие:',SHIFT['next_action'])
''')
    code('''#@title 5. Применить ваши уточнения со стенда (по желанию)
UPLOAD_REVIEW=False #@param {type:'boolean'}
if UPLOAD_REVIEW:
    from google.colab import files
    uploaded=files.upload()
    assert len(uploaded)==1,'Загрузите один shift-user-review.json'
    REVIEW=json.loads(next(iter(uploaded.values())).decode('utf-8-sig'))
    SHIFT=analyze_case(ROOT/'cases/shift',REVIEW)
    print(json.dumps(SHIFT,ensure_ascii=False,indent=2))
else:
    print('Ожидается проверка пользователя. На стенде заполните рынок, подтвердите профиль и выберите конкурентов; скачайте файл уточнений.')
''')
    code('''#@title 6. Ручное дополнение списка и повторный сбор (по желанию)
RUN_COLLECTION=False #@param {type:'boolean'}
NEW_COMPETITOR_URL='' #@param {type:'string'}
if RUN_COLLECTION:
    assert NEW_COMPETITOR_URL.startswith('https://'),'Введите публичный HTTPS URL'
    from profile_site import capture
    NEW_SOURCE=capture(NEW_COMPETITOR_URL)
    candidates=read(ROOT/'cases/shift/candidate_sources.json')
    NEW_SOURCE.update(role='candidate',discovery_method='user_supplied',added_by='user',confirmation_status='pending_user_confirmation')
    candidates=[s for s in candidates if s['requested_url']!=NEW_COMPETITOR_URL]+[NEW_SOURCE]
    (ROOT/'cases/shift/candidate_sources.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Собрано. Источник требует подтверждения; обновите список в файле проверки перед сравнением.')
else:
    print('Новые сайты не загружались. Сохранённые снимки не перезаписаны.')
''')
    for i,c in enumerate(cells): c['id']='two_cases_'+str(i)
    nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'},
        'colab':{'name':'Этап_3_два_проекта.ipynb'},'execution_provenance':'Unexecuted build; actual Colab run recorded separately.'},'cells':cells}
    dest=ROOT/'Этап_3_два_проекта.ipynb'
    dest.write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding='utf-8')
    print('Built',dest.name,dest.stat().st_size)


if __name__=='__main__': build()
