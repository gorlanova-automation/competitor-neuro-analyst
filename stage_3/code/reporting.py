"""Readable outputs; all source content escaped in HTML."""
import csv
import html
import json


def write_report(result, out):
    lines = ['# Нейро аналитик конкурентов', '',
             'Отчёт по сохранённым источникам этапов 2–3. '+result['generated_at'], '',
             '## Покрытие', '']
    for c in result['coverage']:
        lines.append(f"- {c['name']}: {c['facts_in_demo']} доказательств в выбранных критериях; {c['status']}.")
    lines += ['', '## Сравнение по общим критериям', '']
    records = []
    for criterion in result['criteria']:
        lines += ['### '+criterion['name'], '', criterion['reason'], '']
        for cell in criterion['cells']:
            amounts = ', '.join(str(a)+' EUR' for a in cell['amounts_eur']) or ('Услуга упомянута, цена не зафиксирована' if cell['fact_ids'] else 'Нет наблюдений')
            lines.append(f"- {cell['company_id']}: {amounts}; {cell['status']}. Источники: {', '.join(cell['fact_ids']) or 'нет'}.")
            records.append({'criterion': criterion['name'], **cell, 'comparison': criterion['numeric_comparison']})
        lines.append('')
    lines += ['## Рекомендации как проверяемые гипотезы', '']
    for h in result['recommendations']:
        lines += ['### '+h['id']+' '+h['title'], '', h['action'], '',
                  'Проверка: '+h['experiment'], 'Метрика: '+h['metric'],
                  'Основания: '+', '.join(h['evidence_ids']), '']
    lines += ['## Доказательства', '']
    for f in result['evidence']:
        lines += ['### '+f['fact_id'], '', f['company_id']+' — '+f['value'], '',
                  '> '+f['evidence'].replace('\n', '\n> '), '',
                  'Источник: '+f['url'], 'Собран UTC: '+f['source_collected_at'],
                  'Статус: '+f['semantic_review']+'; проверены цитата, число, компания и происхождение.', '']
    lines += ['## Ограничения', '']+['- '+s for s in result['limits']]
    md = '\n'.join(lines)+'\n'
    (out/'report.md').write_bytes(md.encode())
    (out/'report.html').write_bytes(('''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Этап 3 Результаты</title><style>body{max-width:1000px;margin:40px auto;padding:0 24px;font:16px/1.6 system-ui;color:#172e35}pre{white-space:pre-wrap;overflow-wrap:anywhere}h1{font-size:26px}</style><h1>Результаты прототипа этапа 3</h1><pre>'''+html.escape(md)+'</pre></html>').encode())
    with (out/'comparison.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        fields = ['criterion', 'company_id', 'status', 'amounts_eur', 'fact_ids', 'comparison']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in records:
            values = {k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k,v in row.items()}
            writer.writerow({k: "'"+v if isinstance(v,str) and v.startswith(('=', '+', '-', '@')) else v for k,v in values.items()})
