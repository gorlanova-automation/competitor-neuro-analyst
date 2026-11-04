"""Self-contained offline demonstration; optional live call is disabled."""
import ast
import base64
import contextlib
import hashlib
import io
import json
import lzma
from pathlib import Path
import tempfile
import os
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def build():
    payload=io.BytesIO()
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED) as archive:
        paths=[*ROOT.glob('config.json'),*ROOT.glob('README.md'),*(ROOT/'input').rglob('*')]
        paths += [ROOT/'code'/n for n in ['analyst.py','reporting.py','llm_report.py','test_analyst.py']]
        for p in paths:
            if p.is_file(): archive.write(p,p.relative_to(ROOT).as_posix())
    packed=lzma.compress(payload.getvalue()); encoded=base64.b64encode(packed).decode()
    chunks='\n'.join(encoded[i:i+120] for i in range(0,len(encoded),120))
    cells=[]
    def md(s): cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
    def code(s):
        ast.parse(s)
        cells.append({'cell_type':'code','metadata':{},'source':s.splitlines(True),'outputs':[],'execution_count':None})
    md('# Этап 3 Прототип нейроаналитика конкурентов\n\nСквозная демонстрация по принятой базе этапа 2: выбор компаний → проверка источников → сравнение → отчёт → гипотезы. Запустите все ячейки по порядку.\n\n**По умолчанию работает без ключа, сети и платных запросов.** Сведения извлечены реальными LLM-опытами этапа 2; новый текст формируется Python по явным правилам. Полная смысловая точность 175 фактов не подтверждена. Подробный корпус — две компании; остальные семь конкурентов явно помечаются как не исследованные. Это снимок 22.10.2026, не актуализация рынка.')
    code('''#@title Распаковать код и принятую базу
from pathlib import Path
import base64, hashlib, io, json, lzma, sys, zipfile
ROOT = Path.cwd()/"stage3_demo"
ROOT.mkdir(exist_ok=True)
PACKED = """'''+chunks+'''"""
data = base64.b64decode(PACKED)
assert hashlib.sha256(data).hexdigest() == "'''+hashlib.sha256(packed).hexdigest()+'''"
with zipfile.ZipFile(io.BytesIO(lzma.decompress(data))) as archive:
    for name in archive.namelist():
        assert (ROOT/name).resolve().is_relative_to(ROOT.resolve())
    archive.extractall(ROOT)
sys.path.insert(0,str(ROOT/"code"))
from analyst import read, verify_inputs, run
verify_inputs(ROOT)
print("Целостность входов подтверждена. Фактов этапа 2:",len(read(ROOT/"input/facts_draft.json")["facts"]))
''')
    cells[-1]['metadata']['cellView']='form'
    md('## Выбор сценария\n\nСобственная компания и восемь конкурентов уже согласованы в предыдущем этапе. Можно выбрать подмножество подтверждённых конкурентов. Для Испании демонстрация честно вернёт пустой результат. Повторный сбор сайтов — отдельная работа. Шесть критериев заданы исследователем явно; это не автоматическая полная классификация всех услуг.')
    code('''CONFIG=read(ROOT/"config.json")
COUNTRY="Portugal"  # "Spain" — контроль отсутствия исследованного корпуса
CONFIG["country"]=COUNTRY
print("Своя компания:",CONFIG["own_company"])
print("Подтверждённые конкуренты:",CONFIG["competitors"])
print("Страна:",COUNTRY)
''')
    md('## Сравнение и отчёт\n\nПроверяются манифест, происхождение, точная цитата и число. Цены разных составов не ранжируются. Все выводы остаются черновыми наблюдениями; три действия сформулированы как проверяемые гипотезы.')
    code('''RESULT=run(ROOT,CONFIG)
print("Критериев:",len(RESULT["criteria"]),"доказательств:",len(RESULT["evidence"]),"гипотез:",len(RESULT["recommendations"]))
for company in RESULT["coverage"]: print(company["name"],company["facts_in_demo"],company["status"])
for row in RESULT["criteria"]:
    print("\\n",row["name"],row["numeric_comparison"])
    for c in row["cells"]:
        if c["fact_ids"]: print(c["company_id"],c["amounts_eur"],c["status"])
for h in RESULT["recommendations"]: print("\\n",h["id"],h["title"],"\\n",h["action"],"\\nПроверка:",h["experiment"],"\\nМетрика:",h["metric"])
''')
    md('## Проверки ошибок и границ\n\nДевять проверок включают подмену цитаты/компании/числа, конфликт цен, незнакомого конкурента, Испанию без данных, выдуманную ссылку LLM и безопасную обработку ошибки API. Транспорт API в тесте искусственный; этот тест не выдаётся за платный модельный прогон.')
    code('''import unittest
suite=unittest.defaultTestLoader.discover(str(ROOT/"code"),pattern="test_*.py")
outcome=unittest.TextTestRunner(verbosity=1,stream=sys.stdout).run(suite)
assert outcome.wasSuccessful()
print("Проверок успешно:",outcome.testsRun)
''')
    md('## Необязательная новая формулировка LLM\n\nНе нужна для демонстрации. Включать только для отдельного исследования формулировок. Один запрос без повторов; максимум 2500 выходных токенов. Новому Colab может потребоваться разрешение доступа к секрету. Модель предварительно выбрана по пилоту этапа 2, но качество генерации рекомендаций отдельно не измерено. Ответ и настройки сохраняются; ссылки проверяются Python, смысл — человеком. Здесь нет нового сравнения цен моделей.')
    code('''RUN_LLM=False
if RUN_LLM:
    from google.colab import userdata
    from llm_report import generate
    narration=generate(RESULT,userdata.get("PROXYAPI_KEY"),ROOT/"results/llm",CONFIG["model"])
    print("LLM создала черновик; нужна смысловая проверка.",len(narration["hypotheses"]))
else:
    print("Новых LLM-вызовов нет. Основной результат воспроизведён по реальным извлечениям этапа 2.")
''')
    md('## Открыть и сохранить результат\n\nВ results/demo находятся result.json, comparison.csv, report.md, report.html и run.json. В Colab они доступны слева в панели файлов. Для скачивания архива задайте DOWNLOAD=True; выгрузка не вызывает API. Источники и даты приведены в отчёте. Клиентские и внутренние конфиденциальные данные не используются.')
    code('''try:
    from IPython.display import HTML, display
    display(HTML((ROOT/"results/demo/report.html").read_text(encoding="utf-8")))
except ImportError:
    print("HTML сохранён; локальный Python без IPython. Откройте results/demo/report.html в браузере.")
DOWNLOAD=False
if DOWNLOAD:
    import shutil
    from google.colab import files
    zip_path=shutil.make_archive(str(ROOT/"stage3_results"),"zip",ROOT/"results")
    files.download(zip_path)
print("Выходные файлы:",sorted(p.name for p in (ROOT/"results/demo").iterdir()))
''')
    # Execute code cells locally with genuine outputs; no paid call.
    with tempfile.TemporaryDirectory() as temp:
        original=Path.cwd(); ns={'__name__':'__main__'}
        try:
            os.chdir(temp)
            count=0
            for cell in cells:
                if cell['cell_type']!='code': continue
                count+=1; stdout=io.StringIO()
                with contextlib.redirect_stdout(stdout): exec(''.join(cell['source']),ns)
                cell['execution_count']=count
                cell['outputs']=[{'output_type':'stream','name':'stdout','text':stdout.getvalue().splitlines(True)}]
        finally: os.chdir(original)
    for i,c in enumerate(cells): c['id']=f'stage3_{i:02d}'
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'},
              'colab':{'name':'Этап_3_прототип_нейроаналитика.ipynb'},
              'execution_provenance':'Offline cells executed locally; no new model calls. Stage-2 source extraction was executed in Colab.'},'cells':cells}
    dest=ROOT/'Этап_3_прототип_нейроаналитика.ipynb'
    dest.write_bytes(json.dumps(notebook,ensure_ascii=False,indent=1).encode())
    print('Built',dest.name,'bytes',dest.stat().st_size,'executed code cells',count)


if __name__=='__main__': build()
