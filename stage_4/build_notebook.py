"""Build a self-contained final Colab without overwriting stage 3 notebooks."""
import base64
import hashlib
import io
import json
import lzma
import zipfile
from pathlib import Path


def build(project_root='.',destination='stage_4/Этап_4_приложение.ipynb'):
    root=Path(project_root).resolve();files=[]
    for folder in ['stage_4','app','stage_3/code']:
        files.extend((root/folder).glob('*.py'))
    files.extend([root/'stage_3/config.json',root/'stage_3/code/requirements.txt',root/'app/requirements.txt'])
    for folder in ['stage_3/input','stage_3/cases/shift','stage_3/research/market_20261105']:
        files.extend((root/folder).rglob('*.json'))
    files.extend((root/'releases/stage_3_20261027').glob('*'))
    if (root/'stage_4/experiments.json').is_file():files.append(root/'stage_4/experiments.json')
    payload=io.BytesIO()
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            if path.is_file():archive.write(path,path.relative_to(root).as_posix())
    packed=payload.getvalue();package_hash=hashlib.sha256(packed).hexdigest()
    packages=root/'stage_4/packages';packages.mkdir(parents=True,exist_ok=True)
    package=packages/(package_hash+'.zip');package.write_bytes(packed)
    cells=[]
    def md(text):cells.append({'cell_type':'markdown','metadata':{},'source':text.splitlines(True)})
    def code(text):cells.append({'cell_type':'code','metadata':{},'source':text.splitlines(True),'execution_count':None,'outputs':[]})
    md('# Нейро-аналитик конкурентов · финальное приложение\n\nСайт → проверка профиля → подтверждение конкурентов → сбор → проверяемый отчёт. Ни один шаг не утверждает отсутствие услуги из-за ошибки загрузки.\n\nШаги 1–3 проверяют код и воспроизводят сохранённые исследования двух отраслей. **Последняя ячейка запускает новый пользовательский проект через input/upload.** По умолчанию платных вызовов нет. Модель включается только отдельным явным ответом, ключ берётся из Colab Secret `PROXYAPI_KEY`.\n\nОригинальный комплект этапа 3 находится внутри `releases/stage_3_20261027/`, включая Word. Сохранённые снимки и свежий HTTP-сбор — разные режимы.\n\nКод и публичная база: https://github.com/gorlanova-automation/competitor-neuro-analyst .')
    code('''#@title 1. Загрузить зафиксированный комплект и установить зависимости
import hashlib,io,json,pathlib,sys,zipfile,subprocess,urllib.request
PACKAGE_URL='https://raw.githubusercontent.com/gorlanova-automation/competitor-neuro-analyst/main/stage_4/packages/'''+package.name+'''\x27
with urllib.request.urlopen(PACKAGE_URL,timeout=60) as response:payload=response.read(15000000)
assert hashlib.sha256(payload).hexdigest()=="'''+package_hash+'''", 'Package checksum mismatch'
WORK=pathlib.Path.cwd()/'neuro_analyst_final'
WORK.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(payload)) as archive:
    for name in archive.namelist():
        if not (WORK/name).resolve().is_relative_to(WORK.resolve()):raise ValueError('Unsafe archive path')
    archive.extractall(WORK)
subprocess.check_call([sys.executable,'-m','pip','-q','install','-r',str(WORK/'stage_3/code/requirements.txt'),'-r',str(WORK/'app/requirements.txt')])
sys.path.insert(0,str(WORK));sys.path.insert(0,str(WORK/'stage_3/code'))
print('Комплект распакован; API-ключ не запрашивался.')
''')
    code('''# 2. Проверить движок, приложение, подтверждения и модельный контракт без платных вызовов
import unittest
suite=unittest.defaultTestLoader.discover(str(WORK/'stage_3/code'),pattern='test_*.py')
for module in ['stage_4.test_workflow','stage_4.test_semantic','app.test_api','app.test_workflow_api']:
    suite.addTests(unittest.defaultTestLoader.loadTestsFromName(module))
result=unittest.TextTestRunner(verbosity=1,stream=sys.stdout).run(suite)
assert result.wasSuccessful()
manifest=json.loads((WORK/'releases/stage_3_20261027/manifest.json').read_text(encoding='utf-8'))
for item in manifest['files']:
    assert hashlib.sha256((WORK/'releases/stage_3_20261027'/item['file']).read_bytes()).hexdigest()==item['sha256']
print('PASS:',result.testsRun,'тестов. Этап 3: все контрольные суммы совпали. Новых LLM-вызовов: 0.')
''')
    code('''# 3. Две отрасли на сохранённых реальных текстах — не свежий сбор
from stage_4.colab_app import run_saved_demo
for case in ['immigration','shift']:
    state=run_saved_demo(project_root=WORK,output_dir=WORK/'var/demo_projects',case=case)
    print(case,state['status'],state['report'])
print('Подтверждения в этих двух прогонах демонстрационные. Они не заменяют решения пользователя.')
print('Новых LLM-вызовов: 0. Следующая ячейка — ваш новый проект.')
''')
    md('## Запуск своего исследования\n\nНужны URL своей компании, описание рынка и 1–10 подтверждённых конкурентов. Можно попробовать автоматический поиск; если он недоступен, укажите адреса вручную. Файлы новых результатов пишутся в отдельные папки.\n\nСмысловой ответ модели — черновик с проверенными цитатами. Проверка цитат не гарантирует правильность интерпретации. Instagram/Facebook и визуал не объявляются изученными по найденным ссылкам. Для обхода закрытых страниц и CAPTCHA инструментов нет.\n\n**Платный шаг необязателен:** один запрос ProxyAPI, максимум 2500 токенов ответа, без автоматического повтора. Не вставляйте ключ в текст ячеек.')
    code('''# 4. Пользовательский запуск: ввод данных / загрузка TXT
from stage_4.colab_app import launch_colab
user_project=launch_colab(output_dir=WORK/'var/projects')
''')
    for index,cell in enumerate(cells):cell['id']='final_'+str(index)
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','language':'python','display_name':'Python 3'},
        'colab':{'name':'Этап_4_приложение.ipynb'},'execution_provenance':'Built; actual execution must be verified separately.'},'cells':cells}
    dest=root/destination;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(json.dumps(notebook,ensure_ascii=False,indent=1).encode('utf-8'))
    print('Built',dest.name,dest.stat().st_size,'bytes; payload SHA256',hashlib.sha256(packed).hexdigest())


if __name__=='__main__':build()
