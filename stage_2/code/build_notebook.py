"""Build standalone notebook; embedded code matches local reviewed modules."""
import ast
import json
from pathlib import Path


def build_notebook(root):
    code_dir = root/'code'
    assets = {}
    for name in ['collector.py','discovery.py','evaluation.py','model_benchmark.py','summarize_experiments.py','prompt_next_experiment.json','drive_sync.py','social_public.py','export_review.py','test_collector.py','companies.json','config.json','prompts.json','fact_schema.json','requirements.txt']:
        assets['code/'+name] = (code_dir/name).read_text(encoding='utf-8')
    for name in ['README.md','docs/course_mapping.md','docs/model_selection.md','review/reference.json']:
        assets[name] = (root/name).read_text(encoding='utf-8')
    cells = []
    def md(text):
        cells.append({'cell_type':'markdown','metadata':{},'source':text.splitlines(True)})
    def py(text):
        cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':text.splitlines(True)})
    md('# Нейро-аналитик конкурентов — этап 2\n\nПилот: Immigration Relocator и Migrun. Все восемь конкурентов уже согласованы и включены в настройки.\n\nPython получает и очищает материалы. LLM извлекает поля. Код проверяет схему и цитаты. Человек подтверждает смысл, спорные аккаунты и результаты.\n\nВыполняйте ячейки по порядку до основного сценария; дополнительные эксперименты выключены по умолчанию. Ключ берётся из существующего Colab Secret `PROXYAPI_KEY`, значение не вводите в код. Два промпта обрабатывают одинаковые два контрольных фрагмента: четыре запросa генерации всего. Корпус сайта больше этой контрольной выборки. Массовый сбор не запускается автоматически.\n\nУчебные основы: разделы 17, 19, 21–23, 27. Связь с конкретными ячейками — в docs/course_mapping.md.')
    py('import sys, subprocess\nsubprocess.check_call([sys.executable,"-m","pip","install","-q","requests>=2.32,<3","beautifulsoup4>=4.12,<5","jsonschema>=4.23,<5"])\n')
    py('from pathlib import Path\nimport json, sys\nWORKDIR = Path("/content/competitor_stage2")\nWORKDIR.mkdir(parents=True, exist_ok=True)\nASSETS = '+repr(assets)+'\nfor relative, content in ASSETS.items():\n    destination = WORKDIR / relative\n    destination.parent.mkdir(parents=True, exist_ok=True)\n    destination.write_text(content, encoding="utf-8")\nsys.path.insert(0,str(WORKDIR / "code"))\nprint("Код и настройки подготовлены. Секрет не читался.")\n')
    md('## Проверка функций\n\nОфлайн-тесты используют только искусственные примеры в памяти. Они не попадают в реальную базу.')
    py('import unittest\nfrom test_collector import CollectorTests\nresult = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(CollectorTests))\nassert result.wasSuccessful()\n')
    md('## Настройки\n\nДля повторения пилота оставьте две компании. MODEL_OVERRIDE допускает другой полный идентификатор из каталога ProxyAPI. Если выбранная модель отсутствует, программа покажет список и запросит имя. Поддержка строгой JSON-схемы зависит от модели; ошибка сохраняется, автоматического перехода на другую модель нет.\n\nRUN_LLM=True запускает четыре разрешённых пользователем API-запроса генерации. SYNC_DRIVE=True сохраняет файлы только после проверки учебного аккаунта. Все значения доступны для изменения.')
    py('CONFIG = json.loads((WORKDIR/"code/config.json").read_text(encoding="utf-8"))\nCOMPANIES = json.loads((WORKDIR/"code/companies.json").read_text(encoding="utf-8"))\nPROMPTS = json.loads((WORKDIR/"code/prompts.json").read_text(encoding="utf-8"))\nREFERENCE = json.loads((WORKDIR/"review/reference.json").read_text(encoding="utf-8"))\nMODEL_OVERRIDE = ""\nRUN_LLM = True\nSYNC_DRIVE = False  # Отдельная функция sync_stage ниже сохраняет в указанную папку.\nMAX_CALLS_PER_PROMPT = 2\nprint("Выбраны:", CONFIG["collection"]["selected_ids"])\n')
    md('## Основной сценарий и сравнение\n\nОдна загрузка корпуса, затем два эксперимента на одинаковых фрагментах. Ручной эталон составлен до вызова модели. Автосравнение проверяет восемь контрольных цен; смысловую точность всех принятых фактов нужно оценить вручную. Если цитаты эталона изменились на сайте, эти примеры исключаются из расчёта, а не считаются ошибкой модели.\n\nИсходники, очищенный текст, URL/время/хэши, каждый промпт, модель, ответ, usage и карантин сохраняются в `runs`. Отсутствие отдельного поля по неполному корпусу нельзя трактовать как отсутствие услуги.')
    py('''def run_pilot(workdir, config, companies, prompts, reference, run_llm=True, model_override="", max_calls=2, sync_drive=False, resume_run=None):
    import json
    from pathlib import Path
    from collector import start_collection, load_colab_key, list_models, extract_run, read_json, save_json
    from evaluation import compare_reference
    workdir = Path(workdir)
    if resume_run:
        run_dir = Path(resume_run).resolve()
        if not run_dir.is_relative_to((workdir/"runs").resolve()) or not (run_dir/"chunks.json").is_file():
            raise ValueError("resume_run должен указывать на сохранённый корпус внутри runs")
    else:
        run_dir = start_collection(config["collection"],companies,workdir/"runs")
    sources = read_json(run_dir/"sources.json")
    print("Сбор:",len(sources),"страниц; успешных:",sum(s["status"]=="ok" for s in sources))
    print("Источник запуска:",run_dir.name)
    summaries = []
    if run_llm:
        api_key = load_colab_key()
        catalog = list_models(config["llm"]["base_url"],api_key)
        preferred = model_override or config["llm"]["preferred_model"]
        if preferred not in catalog:
            print("Доступные модели:",catalog)
            preferred = input("Полный идентификатор модели из списка: ").strip()
        if preferred not in catalog:
            raise ValueError("Модель не найдена в каталоге")
        print("Модель:",preferred)
        settings = {key:config["llm"][key] for key in ("base_url","response_format","parameters")}
        settings["chunk_ids"] = list(dict.fromkeys(r["chunk_id"] for r in reference))
        try:
            for version,prompt in prompts.items():
                experiment = extract_run(run_dir,api_key,preferred,settings,prompt,max_calls)
                summary = compare_reference(run_dir,experiment,reference)
                summary["prompt_version"] = version
                summaries.append(summary)
                print(version, json.dumps(summary,ensure_ascii=False))
        finally:
            del api_key
    save_json(run_dir/"comparison_summary.json",summaries)
    if sync_drive:
        from drive_sync import sync_stage
        drive = config["drive"]
        uploaded = sync_stage(workdir,drive["parent_folder_id"],drive["expected_email"],drive["stage_folder_name"]+" "+run_dir.name)
        save_json(workdir/"drive_export.json",uploaded)
        print("Папка Drive:",uploaded["folder"].get("webViewLink"))
    return str(run_dir)


# Основная функция вызывается ниже; все настройки переданы явно.
RUN_DIR = run_pilot(WORKDIR,CONFIG,COMPANIES,PROMPTS,REFERENCE,RUN_LLM,MODEL_OVERRIDE,MAX_CALLS_PER_PROMPT,SYNC_DRIVE)
''')
    md('## Дополнительные эксперименты\n\nВключайте только нужный опыт: каждый делает новые платные запросы. Сравнение моделей использует один evidence_v2 и те же фрагменты. Новый v3 проверяется отдельно; версия валидатора фиксируется хэшем. Сохранённый usage включает и неполные ответы. Итоговые расходы оцениваются по тарифному снимку, смысловая проверка обязательна.')
    py('''RUN_MODEL_COMPARISON = False
RUN_NEXT_PROMPT = False
if RUN_MODEL_COMPARISON or RUN_NEXT_PROMPT:
    from collector import load_colab_key, extract_run, read_json
    from model_benchmark import benchmark_models
    from summarize_experiments import summarize
    key = load_colab_key()
    settings = {k:CONFIG["llm"][k] for k in ("base_url","response_format","parameters")}
    settings["chunk_ids"] = list(dict.fromkeys(r["chunk_id"] for r in REFERENCE))
    try:
        if RUN_MODEL_COMPARISON:
            print(benchmark_models(RUN_DIR,key,CONFIG["model_policy"]["benchmark_candidates"],settings,PROMPTS["evidence_v2"],REFERENCE,2))
        if RUN_NEXT_PROMPT:
            candidate = read_json(WORKDIR/"code/prompt_next_experiment.json")
            experiment = extract_run(RUN_DIR,key,CONFIG["llm"]["preferred_model"],settings,candidate["prompt"],2)
            from evaluation import compare_reference
            print(compare_reference(RUN_DIR,experiment,REFERENCE))
        print(json.dumps(summarize(RUN_DIR),ensure_ascii=False,indent=2))
    finally:
        del key
''')
    nb={'nbformat':4,'nbformat_minor':5,'metadata':{'colab':{'name':'Этап_2_сбор_и_эксперименты.ipynb'},'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'}},'cells':cells}
    for i,cell in enumerate(cells):
        cell['id']=f'stage2_{i:02d}'
        if cell['cell_type']=='code':
            ast.parse(''.join(cell['source']))
    path=code_dir/'Этап_2_сбор_и_эксперименты.ipynb'
    path.write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding='utf-8')
    print(path)


if __name__=='__main__':
    build_notebook(Path(__file__).resolve().parents[1])
