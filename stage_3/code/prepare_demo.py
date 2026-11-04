"""Copy a minimal immutable demonstration snapshot from accepted stage 2."""
import json
import shutil
from pathlib import Path
from analyst import save, digest, read

ROOT=Path(__file__).resolve().parents[1]


def prepare():
    if (ROOT/'input/additions/facts.json').exists():
        raise RuntimeError('Current stage 3 contains user additions. Refusing to overwrite them with the historical stage-2 demo. Use a separate checkout for reconstruction.')
    previous=ROOT.parent/'stage_2'
    inputs=ROOT/'input'; inputs.mkdir(exist_ok=True)
    run=previous/'runs/20261022T111451Z_0f8116'
    for src,name in [(previous/'knowledge_base/facts_draft.json','facts_draft.json'),
                     (previous/'competitor_candidates.json','competitor_candidates.json'),
                     (previous/'code/companies.json','companies.json')]:
        shutil.copy2(src,inputs/name)
    ids={f['source_id'] for f in read(inputs/'facts_draft.json')['facts']}
    sources=[s for s in read(run/'sources.json') if s['source_id'] in ids]
    for source in sources:
        for kind in ('raw','text'):
            rel=source[kind+'_path'].replace('\\','/')
            dest=inputs/rel; dest.parent.mkdir(exist_ok=True)
            shutil.copy2(run/rel,dest)
            source[kind+'_path']=rel
    save(inputs/'sources.json',sources)
    save(inputs/'chunks.json',[c for c in read(run/'chunks.json') if c['source_id'] in ids])
    definitions=[
        ('consultation','Входная консультация',{'immigration_relocator':['15de784c6b8a45af95dd'],'migrun':['eb214cd8635a995b22cc','0ec799da32b5bc76f79f']},'150 EUR против 40/70 EUR — разные описания; длительность собственной консультации в цитате не указана. Численный рейтинг заблокирован.'),
        ('tax_consultation','Налоговая консультация',{'immigration_relocator':['556890c135ee959d318d','daa9c3a4e66e2e1f2031']},'Два блока 170 и 350 EUR сохраняются как неразрешённое расхождение; нельзя выбрать актуальную цену автоматически.'),
        ('nif','Оформление NIF',{'immigration_relocator':['a3250126d0a017dc1f98']},'150 EUR — наблюдение своей компании. Цена Migrun 109 EUR не используется: факт остался в карантине этапа 2. Отсутствие в выбранных данных не равно отсутствию услуги.'),
        ('renewal','Продление ВНЖ',{'immigration_relocator':['3887e2ca5004d9f85f44','00ded96e3b08df2070aa']},'Повторные блоки 500 EUR не суммируются и не считаются отдельными тарифами. Сопоставимого предложения конкурента в данном наборе нет.'),
        ('assistance','Пакеты сопровождения',{'migrun':['7020aa1cee8bd213e04f','1275c05e3ab20fe956d4','e950fd041d8cb1266532']},'Check-up 530 EUR, Standard 1290 EUR и Premium 3490 EUR — разные пакеты одного конкурента. Входная консультация или отдельные услуги своей компании не являются эквивалентом пакета.'),
        ('company_registration','Регистрация компании',{'immigration_relocator':['91504d485cf00fdd15af','935281eb6991e994697d']},'Два блока 950 EUR различаются пометками государственных сборов. Не выдавать сумму за сопоставимую полную стоимость без уточнения включённых платежей.')]
    save(inputs/'criteria.json',[{'id':i,'name':n,'country':'Portugal','fact_ids':f,'comparison_note':note,
                                  'mapping_origin':'explicit_researcher_demo_mapping_not_user_semantic_annotation'} for i,n,f,note in definitions])
    save(inputs/'manifest.json',[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p),'bytes':p.stat().st_size}
                                 for p in sorted(inputs.rglob('*')) if p.is_file() and p.name!='manifest.json'])
    save(ROOT/'config.json',{'own_company':'immigration_relocator',
                           'competitors':[c['id'] for c in read(inputs/'companies.json') if c['role']=='confirmed_competitor'],
                           'country':'Portugal','live_llm_enabled':False,
                           'model':'openai/gpt-6-luna','max_live_calls':1,
                           'mapping_status':'researcher_defined_demo_not_full_semantic_review'})


if __name__=='__main__': prepare()
