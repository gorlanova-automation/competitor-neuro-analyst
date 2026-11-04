"""Source-backed stage-3 prototype. Standard library, no network by default."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_inputs(root):
    root = Path(root).resolve()
    manifest = read(root/'input/manifest.json')
    for item in manifest:
        p = (root/item['path']).resolve()
        if not p.is_relative_to(root/'input') or not p.is_file() or digest(p) != item['sha256']:
            raise ValueError('Input integrity failed: '+item['path'])
    return manifest


def validate_fact(fact, chunks, sources, root):
    errors = []
    chunk = chunks.get(fact.get('chunk_id'))
    source = sources.get(fact.get('source_id'))
    if not chunk or not source:
        return ['missing_provenance']
    if source['company_id'] != fact.get('company_id') or chunk['company_id'] != fact.get('company_id'):
        errors.append('company_mismatch')
    if chunk['source_id'] != source['source_id']:
        errors.append('source_mismatch')
    quote = fact.get('evidence', '')
    if not quote or quote not in chunk['text']:
        errors.append('quote_mismatch')
    elif fact.get('evidence_start') != chunk['start']+chunk['text'].find(quote):
        errors.append('offset_mismatch')
    if fact.get('url') not in (source.get('requested_url'), source.get('final_url')):
        errors.append('url_mismatch')
    if fact.get('field') == 'price':
        amount = fact.get('amount')
        numbers = [float(v.replace(' ', '').replace('\u00a0', '').replace(',', '.'))
                   for v in re.findall(r'\d[\d \u00a0]*(?:[.,]\d+)?', quote)]
        if not isinstance(amount, (float, int)) or amount not in numbers:
            errors.append('amount_not_in_quote')
        if fact.get('currency') != 'EUR' or not ('€' in quote or 'EUR' in quote):
            errors.append('currency_unverified')
    # Source text must actually contain the stored chunk, not only its quote.
    text = (Path(root)/'input'/source['text_path']).read_text(encoding='utf-8')
    if text[chunk['start']:chunk['end']] != chunk['text']:
        errors.append('chunk_text_mismatch')
    return errors


def compare(root, config):
    root = Path(root)
    verify_inputs(root)
    candidates = read(root/'input/competitor_candidates.json')
    if candidates['status'] != 'confirmed_by_user':
        raise ValueError('Competitor list is not confirmed')
    catalog = {c['id']: c for c in read(root/'input/companies.json')}
    own = config['own_company']
    if catalog.get(own, {}).get('role') != 'own_company':
        raise ValueError('Unknown own company')
    for cid in config['competitors']:
        if catalog.get(cid, {}).get('role') != 'confirmed_competitor':
            raise ValueError('Unknown/unconfirmed competitor: '+cid)
    if len(config['competitors']) != len(set(config['competitors'])):
        raise ValueError('Duplicate competitor')
    selected = [own]+config['competitors']
    facts = read(root/'input/facts_draft.json')['facts']
    chunks = {c['chunk_id']: c for c in read(root/'input/chunks.json')}
    sources = {s['source_id']: s for s in read(root/'input/sources.json')}
    additions = root/'input/additions'
    if (additions/'facts.json').is_file():
        facts += read(additions/'facts.json')['facts']
        chunks.update({c['chunk_id']: c for c in read(additions/'chunks.json')})
        sources.update({s['source_id']: s for s in read(additions/'sources.json')})
    valid = {}; rejected = []
    for fact in facts:
        if fact['company_id'] not in selected:
            continue
        # The demonstration uses an explicitly reviewed Portugal-page mapping.
        source = sources.get(fact['source_id'])
        if not source:
            rejected.append({'fact_id': fact['fact_id'], 'errors': ['source_outside_demo']})
            continue
        errors = validate_fact(fact, chunks, sources, root)
        if errors:
            rejected.append({'fact_id': fact['fact_id'], 'errors': errors})
        else:
            valid[fact['fact_id']] = fact
    criteria = []; used = {}
    for criterion in read(root/'input/criteria.json'):
        if criterion['country'] != config['country']:
            continue
        cells = []
        for cid in selected:
            ids = criterion['fact_ids'].get(cid, [])
            rows = [valid[i] for i in ids if i in valid and valid[i]['company_id'] == cid]
            for f in rows:
                used[f['fact_id']] = f
            prices = sorted(set(f['amount'] for f in rows if f.get('amount') is not None))
            status = 'observed_draft' if rows else 'not_observed_in_limited_corpus'
            if rows and not prices:
                status = 'service_mentioned_price_not_observed'
            if criterion['id'] == 'tax_consultation' and len(prices) > 1:
                status = 'conflicting_published_prices'
            cells.append({'company_id': cid, 'status': status,
                          'amounts_eur': prices, 'fact_ids': [f['fact_id'] for f in rows]})
        criteria.append({'id': criterion['id'], 'name': criterion['name'],
                         'country': criterion['country'], 'cells': cells,
                         'numeric_comparison': 'blocked_unverified_scope_or_terms',
                         'reason': criterion['comparison_note']})
    evidence = [{**f, 'source_collected_at': sources[f['source_id']]['collected_at'],
                 'source_country_context': 'Portugal',
                 'country_context_basis': 'Explicit researcher mapping of selected Portugal pages; not legal verification',
                 'verification': 'quote_number_provenance_only',
                 'semantic_review': f.get('semantic_review', 'not_complete')} for f in used.values()]
    coverage = []
    for cid in selected:
        coverage.append({'company_id': cid, 'name': catalog[cid]['name'],
                         'facts_in_demo': sum(f['company_id'] == cid for f in evidence),
                         'status': 'limited_snapshot' if any(f['company_id'] == cid for f in evidence) else 'not_researched_for_selected_country',
                         'added_by': catalog[cid].get('added_by'),
                         'discovery_method': catalog[cid].get('discovery_method', 'previous_candidate_catalog')})
    recommendations = []
    def hypothesis(rid, title, action, experiment, metric, ids):
        refs = [i for i in ids if i in used]
        if refs and len(refs) == len(ids):
            recommendations.append({'id': rid, 'status': 'hypothesis_requires_owner_review',
                                    'title': title, 'action': action, 'experiment': experiment,
                                    'metric': metric, 'evidence_ids': refs})
    if config['country'] == 'Portugal':
        hypothesis('H1', 'Уточнить две цены налоговой консультации',
                   'Проверить блоки 170 и 350 EUR: обозначить различия состава или исправить устаревший блок после подтверждения владельцем.',
                   'Владелец услуги сверяет оба блока, срок действия цены и объём консультации.',
                   'Число неразрешённых расхождений в опубликованной карточке: целевое 0.',
                   ['556890c135ee959d318d', 'daa9c3a4e66e2e1f2031'])
        hypothesis('H2', 'Яснее описать входную консультацию',
                   'Проверить гипотезу о пользе явных длительности и результата консультации. Не снижать 150 EUR по несопоставимым предложениям 40/70 EUR.',
                   'Вариант карточки с длительностью, результатом и исключениями; после утверждения сравнить с текущим описанием.',
                   'Доля квалифицированных обращений и вопросов о составе; исходных данных для эффекта пока нет.',
                   ['15de784c6b8a45af95dd', 'eb214cd8635a995b22cc', '0ec799da32b5bc76f79f'])
        hypothesis('H3', 'Проверить понятность ступеней сопровождения',
                   'Использовать наблюдаемую линейку Migrun как повод проверить понятность собственных границ услуг, без копирования цен.',
                   'Создать согласованный макет сравнения состава пакетов и проверить понимание на интервью с клиентами.',
                   'Доля участников, правильно выбравших подходящий состав. Результаты интервью пока отсутствуют.',
                   ['7020aa1cee8bd213e04f', '1275c05e3ab20fe956d4', 'e950fd041d8cb1266532'])
    return {'schema_version': 1, 'mode': 'offline_reuse_stage2_llm_facts',
            'generated_at': datetime.now(timezone.utc).isoformat(), 'config': config,
            'coverage': coverage, 'criteria': criteria, 'evidence': evidence,
            'recommendations': recommendations, 'rejected': rejected,
            'limits': ['Смешанные снимки: пилот 22.10.2026 и четыре страницы 04.11.2026. Даты источников сохранены; это не полный актуальный сбор всех компаний.',
                       '175 фактов этапа 2 остаются черновиками; техническая проверка не равна смысловой.',
                       'Полный состав и условия услуг не сопоставлены; рейтинг и проценты дешевизны не рассчитываются.',
                       'Отсутствие наблюдения в ограниченном корпусе не означает отсутствия услуги.',
                       'Новые вызовы LLM в основном офлайн-прогоне отсутствуют; используются реальные результаты LLM этапа 2.']}


def run(root, config=None, out=None):
    root = Path(root).resolve()
    config = config or read(root/'config.json')
    result = compare(root, config)
    out = Path(out) if out else root/'results/demo'
    out.mkdir(parents=True, exist_ok=True)
    save(out/'result.json', result)
    save(out/'run.json', {'config': config, 'mode': result['mode'],
                         'input_manifest_sha256': digest(root/'input/manifest.json'),
                         'code_sha256': {p.name: digest(p) for p in (root/'code').glob('*.py')},
                         'new_llm_calls': 0, 'new_api_cost': 0,
                         'generated_at': result['generated_at']})
    from reporting import write_report
    write_report(result, out)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--country', choices=['Portugal', 'Spain'])
    parser.add_argument('--out')
    args = parser.parse_args()
    cfg = read(Path(args.root)/'config.json')
    if args.country:
        cfg['country'] = args.country
    r = run(args.root, cfg, args.out)
    print(json.dumps({'criteria': len(r['criteria']), 'evidence': len(r['evidence']),
                      'hypotheses': len(r['recommendations']), 'covered_companies': sum(bool(c['facts_in_demo']) for c in r['coverage'])}, ensure_ascii=False))
