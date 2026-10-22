"""Package saved stage-2 research and a self-contained offline Colab."""
import ast
import base64
import contextlib
import csv
import io
import json
import lzma
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
from research_audit import audit, read, sha

ROOT=Path(__file__).resolve().parents[1]

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def build():
    # Historical runtime code is already preserved as individual source files.
    # Validate it directly; full Colab environment archives are unnecessary.
    index=read(ROOT/'code_versions/index.json')
    main_run=ROOT/'runs/20261022T111451Z_0f8116'
    for version in index.values():
        path=ROOT/version['path']
        assert sha(path.read_bytes())==version['collector_sha256'], path
    result=audit(ROOT)
    assert result['checks_passed'],result['integrity_errors']
    kb=ROOT/'knowledge_base'; kb.mkdir(exist_ok=True)
    selected='20261022T113037Z_be7ea6'
    facts=read(main_run/'experiments'/selected/'facts.json')
    save(kb/'facts_draft.json',{'status':'draft_pending_semantic_review','experiment':selected,'run':main_run.name,'facts':facts})
    save(kb/'quarantine.json',read(main_run/'experiments'/selected/'quarantine.json'))
    merged_sources=[]
    for r in sorted((ROOT/'runs').iterdir()):
        if not (r/'sources.json').exists(): continue
        for s in read(r/'sources.json'):
            item={'run':r.name,**s}
            for kind in ('raw','text'):
                if s.get(kind+'_path'):
                    item[kind+'_artifact_path']='runs/'+r.name+'/'+s[kind+'_path'].replace('\\','/')
            merged_sources.append(item)
    save(kb/'sources.json',merged_sources)
    posts=[]
    for p in (ROOT/'runs/20261021T191729Z_4005ca/social').glob('*posts.json'):
        posts.extend(read(p)['posts'])
    save(kb/'social_posts.json',{'status':'public_preview_partial_ownership_pending','posts':posts})
    for filename,rows in [('facts_draft.csv',facts),('sources.csv',read(kb/'sources.json'))]:
        fields=list(dict.fromkeys(k for row in rows for k in row))
        with (kb/filename).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader()
            for row in rows:
                safe={k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()}
                writer.writerow({k:"'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for k,v in safe.items()})
    save(kb/'dataset_card.json',{'status':'pilot_draft','own_company':'Immigration Relocator','competitors_in_detailed_pilot':['Migrun'],'confirmed_competitor_list':'competitor_candidates.json','website_snapshots':['20261021T191729Z_4005ca','20261022T111451Z_0f8116'],'facts_selected_experiment':selected,'facts_count':len(facts),'quarantine_count':3,'social_posts_count':len(posts),'manual_price_references':8,'facts_semantic_review':'not_complete','source_claims_independently_verified':False,'scope_limit':'Two companies; website source rows include repeated snapshots. Eight confirmed competitors have not all been collected.','actual_api_billing_rub':None})
    (kb/'README.txt').write_text('База пилота этапа 2. facts_draft — 175 записей модели, не утверждённые знания. quarantine — 3 записи. sources хранит run: одинаковый URL в разные моменты является разными снимками. social_posts — 25 постов публичного превью, полнота и принадлежность не подтверждены. Эталон review/reference.json — 8 цен, подготовлен вручную до модели. Сырые источники и полные эксперименты находятся в runs. Поиск выдачи и полный сбор восьми конкурентов не завершены.\n',encoding='utf-8')
    # Dataset contains provenance and experiment inputs, never runtime dependencies or keys.
    include=[]
    for folder in ['runs','code_versions','knowledge_base']:
        include.extend(p for p in (ROOT/folder).rglob('*') if p.is_file())
    include += [ROOT/'review/reference.json',ROOT/'company_profile_draft.json',ROOT/'competitor_candidates.json']
    manifest=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted(include)]
    payload=io.BytesIO()
    with ZipFile(payload,'w',ZIP_DEFLATED) as z:
        for p in include: z.write(p,p.relative_to(ROOT).as_posix())
        z.writestr('dataset_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        z.writestr('research_audit.py',(ROOT/'code/research_audit.py').read_text(encoding='utf-8'))
    dataset=payload.getvalue()
    artifacts=ROOT/'artifacts'
    artifacts.mkdir(exist_ok=True)
    (artifacts/'Этап_2_база_и_эксперименты.zip').write_bytes(dataset)
    cells=[]
    def md(s): cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
    def py(s):
        ast.parse(s)
        cells.append({'cell_type':'code','metadata':{},'source':s.splitlines(True),'execution_count':None,'outputs':[]})
    md('# Этап 2 — исследование сбора базы знаний\n\nСамостоятельный исследовательский ноутбук: пересчитывает результаты реально проведённых опытов из сохранённых данных. **Нет сетевых запросов, доступа к секретам и платных вызовов.** Встроены корпус, реестр источников, запросы/ответы моделей, эталон, версии кода. Результаты Python-проверок ниже исполнены локально; платные опыты ранее выполнены в Colab 22.10.2026. Для повторения проверки достаточно Run all.\n\nПрофиль → запросы исследуется отдельно в [первом Colab](https://colab.research.google.com/drive/1VrOW30seMq_-kOrXQ0pgJ9kdHI9FqX6S). [Основной Colab](https://colab.research.google.com/drive/1wWOfqx-i27wJDFxnG0SPkai_XFgwIqiN) хранит исходные исполнения. Этот ноутбук относится только к этапу 2; объединение этапов в приложение — последующая работа.')
    # Solid LZMA compression removes repeated snapshots and short source lines
    # avoid a multi-megabyte editor line that can stall Colab/Monaco.
    solid=io.BytesIO()
    with ZipFile(io.BytesIO(dataset)) as original_zip, ZipFile(solid,'w',ZIP_STORED) as stored_zip:
        for name in original_zip.namelist(): stored_zip.writestr(name,original_zip.read(name))
    notebook_data=solid.getvalue()
    encoded=base64.b64encode(lzma.compress(notebook_data)).decode()
    encoded_source='(\n'+''.join(repr(encoded[i:i+120])+'\n' for i in range(0,len(encoded),120))+')'
    py('from pathlib import Path\nimport base64,hashlib,io,json,zipfile,sys,lzma\nROOT=Path("/content/stage2_research") if Path("/content").exists() else Path.cwd()/"stage2_research"\nROOT.mkdir(parents=True,exist_ok=True)\nDATA=lzma.decompress(base64.b64decode('+encoded_source+'))\nassert hashlib.sha256(DATA).hexdigest()=='+repr(sha(notebook_data))+'\nwith zipfile.ZipFile(io.BytesIO(DATA)) as archive:\n    for name in archive.namelist():\n        if not (ROOT/name).resolve().is_relative_to(ROOT.resolve()): raise ValueError("Unsafe archive path")\n    archive.extractall(ROOT)\nfor item in json.loads((ROOT/"dataset_manifest.json").read_text(encoding="utf-8")):\n    assert hashlib.sha256((ROOT/item["path"]).read_bytes()).hexdigest()==item["sha256"],item["path"]\nsys.path.insert(0,str(ROOT))\nprint("Проверены все файлы манифеста:",len(json.loads((ROOT/"dataset_manifest.json").read_text(encoding="utf-8"))))\n')
    cells[-1]['metadata']['cellView']='form'
    cells[-1]['source'].insert(0,'#@title Распаковать сохранённую базу и проверить манифест\n')
    md('## Сбор и очистка Python\n\nПроверяются байты/хэши HTML и очищенных текстов, смещения фрагментов. Неуспешные источники остаются в реестре. Повторные снимки одного URL не считаются разными компаниями. Публичный Telegram — ограниченное превью, отдельно от сайтов.')
    py('from research_audit import audit\nRESULT=audit(ROOT)\nprint(json.dumps({k:RESULT[k] for k in ("source_rows","source_statuses","chunks_in_colab_corpus","same_inputs_across_experiments","integrity_errors","checks_passed")},ensure_ascii=False,indent=2))\nassert RESULT["checks_passed"]\n')
    md('## Извлечение LLM: сравнение сохранённых опытов\n\nОдин корпус и два контрольных фрагмента. Для v1/v2 меняется промпт на одной Luna; для сравнения моделей фиксирован evidence_v2. В v3 изменены промпт и валидатор одновременно — отдельный опыт доработки. Время ниже — весь опыт, а не индивидуальная задержка API. Тарифная оценка не равна фактическому списанию.')
    py('for c in RESULT["experiments"]:\n    print(c["experiment"],c["model"],"цены",str(c["reference_result"]["matched_by_rules"])+"/8","принято",c["facts_accepted"],"карантин",len(c["quarantine"]),"ошибки",len(c["failures"]),"сек",c["elapsed_pipeline_seconds"],"оценка RUB",c["cost"]["tariff_estimate_rub"])\n')
    md('## Полные промпты, версии и ошибки\n\nКаждая карточка содержит цель, модель, настройки, версию кода, хэши корпуса/промпта, даты UTC, время, usage, тарифную оценку и ошибки. Для ранних опытов исходник восстановлен из архива среды; хэш во время выполнения не журналировался. Полные пользовательские сообщения и схема сохранены в *_request.json.')
    py('for c in RESULT["experiments"]:\n    print("\\nОПЫТ",c["experiment"],"\\nЦЕЛЬ",c["goal"],"\\nКОД",c["code_version"],"\\nНАСТРОЙКИ",json.dumps(c["settings"],ensure_ascii=False),"\\nСИСТЕМНЫЙ ПРОМПТ\\n",c["prompt"],"\\nОШИБКИ",json.dumps(c["failures"],ensure_ascii=False))\n')
    md('## База и ручной контроль\n\nВыбранный v3 дал 175 записей после автоматической проверки и 3 в карантине. Это **черновая база**, полного смыслового утверждения нет. Восемь контрольных цен подготовлены вручную до LLM; совпадение по правилам не измеряет точность всех 175 фактов. Контроль налоговой консультации сохраняет обе суммы 170/350 EUR, не выбирая актуальную автоматически.')
    py('CARD=json.loads((ROOT/"knowledge_base/dataset_card.json").read_text(encoding="utf-8"))\nprint(json.dumps(CARD,ensure_ascii=False,indent=2))\nprint("\\nКонтрольные примеры:")\nfor row in json.loads((ROOT/"review/reference.json").read_text(encoding="utf-8")):\n    print(row["reference_id"],row["company_id"],row["amount"],row["manual_note"])\n')
    md('## Вывод и остаток работы\n\nLuna — предварительный выбор для извлечения в этом пилоте: 8/8 цен при меньшей тарифной оценке. Gemini нарушила разделение суммы и поля услуги; Claude получила length при 4096 токенах на одной странице. Для честного следующего опыта нужны отдельные адаптации, а не вывод о качестве вендоров вообще. v2 дешевле v1, но теряет часть отдельных полей; v3 исправил наблюдавшийся дефект цитаты о типах виз и вернул отдельные поля, стоит дороже.\n\nОстаются: смысловая проверка фактов, расширение эталона за пределы цен, автоматический поиск выдачи/кандидатов, полный сбор восьми конкурентов, проверка соцсетей и карт, рекомендации. Профиль/кандидаты ранее подтверждены пользователем; повторное подтверждение тех же вводных не требуется.\n\nПромежуточный контракт объединения этапов: knowledge_base/facts_draft.json + sources.json + dataset_card.json; только утверждённые человеком факты допускаются в будущие рекомендации. Схема интеграции ещё не реализована как приложение.')
    # Execute only the offline cells locally and preserve real stdout in the notebook.
    import tempfile
    temporary=tempfile.TemporaryDirectory(prefix='.research_notebook_check_',dir=ROOT)
    sandbox=Path(temporary.name)
    env={'__name__':'__main__'}
    import os
    original=Path.cwd()
    try:
        os.chdir(sandbox)
        count=0
        for cell in cells:
            if cell['cell_type']!='code': continue
            count+=1; out=io.StringIO()
            with contextlib.redirect_stdout(out): exec(''.join(cell['source']),env)
            cell['execution_count']=count
            cell['outputs']=[{'output_type':'stream','name':'stdout','text':out.getvalue().splitlines(True)}]
    finally:
        os.chdir(original)
        temporary.cleanup()
    for i,c in enumerate(cells): c['id']=f'research_{i:02d}'
    nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'},'colab':{'name':'Этап_2_исследование_по_сохранённым_опытам.ipynb'},'execution_provenance':'Offline cells executed locally; original LLM calls executed in separate Colab on 2026-10-22.'},'cells':cells}
    save(ROOT/'code/Этап_2_исследование_по_сохранённым_опытам.ipynb',nb)
    print('Audit passed; experiments:',len(result['experiments']),'dataset bytes:',len(dataset),'offline notebook cells:',count)

if __name__=='__main__': build()
