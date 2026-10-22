"""Build human-readable review tables without changing underlying evidence."""
from pathlib import Path
from html import escape
from collector import read_json, save_json, write_csv


def html_table(rows, fields):
    header=''.join('<th>'+escape(label)+'</th>' for key,label in fields)
    body=[]
    for row in rows:
        cells=[]
        for key,label in fields:
            value=row.get(key,'')
            text='' if value is None else str(value)
            if text.startswith(('https://','http://')):
                cells.append('<td><a href="'+escape(text,quote=True)+'">'+escape(text)+'</a></td>')
            else:
                cells.append('<td>'+escape(text)+'</td>')
        body.append('<tr>'+''.join(cells)+'</tr>')
    return '<div class="scroll"><table><thead><tr>'+header+'</tr></thead><tbody>'+''.join(body)+'</tbody></table></div>'


def export_review(root, run_dir):
    root,run_dir=Path(root),Path(run_dir)
    sources=read_json(run_dir/'sources.json')
    gold=read_json(root/'review/reference.json')
    posts=[]
    for path in (run_dir/'social').glob('*posts.json'):
        posts.extend(read_json(path)['posts'])
    write_csv(run_dir/'social_posts.csv',posts,['company_id','channel_url','post_url','published_at','collected_at','format','text','ownership_status','method','raw_path'])
    write_csv(root/'review/reference.csv',gold,['reference_id','company_id','field','amount','kind','evidence','manual_note'])
    facts=[]
    for path in (run_dir/'experiments').glob('*/facts.json'):
        facts.extend({**row,'experiment':path.parent.name} for row in read_json(path))
    content='''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Этап 2 — проверка базы</title><style>body{font:15px system-ui;margin:32px;color:#163047;background:#f5f7fa}h1{font-size:28px}h2{margin-top:32px}p{max-width:1050px;line-height:1.6}.scroll{overflow:auto;border:1px solid #c8d1db;background:white}table{border-collapse:collapse;min-width:950px;width:100%}th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #dce3ea;vertical-align:top;white-space:pre-wrap;min-width:100px;max-width:500px;overflow-wrap:anywhere}th{background:#153d57;color:white;position:sticky;top:0}tr:nth-child(even){background:#f4f8fb}a{color:#136296}</style><h1>Этап 2 — проверка базы пилота</h1>'''
    content+='<p>Запуск '+escape(run_dir.name)+'. Пилот: Immigration Relocator и Migrun. Исходные страницы собрал Python. Контрольные цены подготовлены вручную. Публикации Telegram получены из ограниченного публичного превью. Полнота сайтов и соцсетей не доказана. Модельные факты требуют смысловой проверки.</p>'
    content+='<h2>Реестр источников</h2>'+html_table(sources,[('company_id','Компания'),('final_url','URL'),('status','Результат'),('collected_at','Время UTC'),('text_chars','Символов'),('source_id','ID источника')])
    content+='<h2>Ручная контрольная выборка</h2>'+html_table(gold,[('reference_id','ID'),('company_id','Компания'),('amount','Сумма EUR'),('evidence','Точный фрагмент'),('manual_note','Контекст проверки')])
    content+='<h2>Telegram: '+str(len(posts))+' публикаций</h2>'+html_table(posts,[('company_id','Компания'),('post_url','Публикация'),('published_at','Опубликовано'),('format','Формат'),('text','Текст'),('ownership_status','Принадлежность')])
    content+='<h2>Извлечённые моделью факты: '+str(len(facts))+'</h2>'
    if facts:
        content+=html_table(facts,[('experiment','Эксперимент'),('company_id','Компания'),('field','Поле'),('value','Значение'),('evidence','Цитата'),('url','Источник'),('review_status','Проверка')])
    else:
        content+='<p>В этом локальном запуске модельные эксперименты ещё не выполнялись. Ручные контрольные примеры не подставлены вместо ответа модели.</p>'
    content+='</html>'
    (root/'review/index.html').write_text(content,encoding='utf-8')
    return root/'review/index.html'


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',default='stage_2')
    parser.add_argument('--run',required=True)
    args=parser.parse_args()
    print(export_review(args.root,args.run))
