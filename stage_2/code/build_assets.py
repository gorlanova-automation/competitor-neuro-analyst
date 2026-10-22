"""Generate config assets and a standalone Colab notebook from reviewed sources."""
import json
from pathlib import Path


def build(root):
    code = root / 'code'
    candidates = json.loads((root/'competitor_candidates.json').read_text(encoding='utf-8-sig'))
    candidates['status'] = 'confirmed_by_user'
    candidates['confirmed_on'] = '2026-10-21'
    (root/'competitor_candidates.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2),encoding='utf-8')
    ids = ['migrun','migran','relotus','relocate_group','e_residence','dh_private','migrall','movetocascais']
    companies = [{'id':'immigration_relocator','name':'Immigration Relocator','role':'own_company','seed_urls':['https://immigration-relocator.com/','https://immigration-relocator.com/pt-otherservices','https://immigration-relocator.com/about']}]
    for cid, candidate in zip(ids,candidates['candidates']):
        seeds = [candidate['url']]
        if cid == 'migrun':
            seeds += ['https://www.migrun.tech/ru/portugal/services-in-portugal/assistance-packages','https://www.migrun.tech/ru/relocation-for-teams-and-companies']
        companies.append({'id':cid,'name':candidate['name'],'role':'confirmed_competitor','seed_urls':seeds})
    (code/'companies.json').write_text(json.dumps(companies,ensure_ascii=False,indent=2),encoding='utf-8')
    import collector
    (code/'fact_schema.json').write_text(json.dumps(collector.fact_schema(),ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    build(Path(__file__).resolve().parents[1])
