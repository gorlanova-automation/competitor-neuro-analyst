"""Create the Word submission from real prototype outputs."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT

ROOT=Path(__file__).resolve().parents[1]
COLAB='https://colab.research.google.com/drive/17AaYUf-wWWAy2pneSUzUS_RZotlAU5Xn'
FOLDER='https://drive.google.com/drive/folders/1naN-5200DmVQUB9fimatlJZEcSi9Hi6e'


def hyperlink(p,text,url):
    rel=p.part.relate_to(url,'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink',is_external=True)
    h=OxmlElement('w:hyperlink'); h.set(qn('r:id'),rel)
    r=OxmlElement('w:r'); pr=OxmlElement('w:rPr'); color=OxmlElement('w:color'); color.set(qn('w:val'),'1C5969'); pr.append(color); r.append(pr)
    t=OxmlElement('w:t'); t.text=text; r.append(t); h.append(r); p._p.append(h)


def diagram():
    image=Image.new('RGB',(1800,760),'white'); d=ImageDraw.Draw(image)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',36)
    bold=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',40)
    boxes=[(20,30,560,270,'1  Вход','Компания и конкуренты\nСнимок этапа 2'),
           (630,30,1170,270,'2  Проверка Python','Хэши и точная цитата\nЧисла и происхождение'),
           (1240,30,1780,270,'3  Сопоставление','Шесть явных критериев\nБлокировка рейтинга'),
           (1240,440,1780,700,'4  Гипотезы','Правила Python\nНовая LLM необязательна'),
           (630,440,1170,700,'5  Решение человека','Смысл и условия услуг\nАктуальность и приоритет'),
           (20,440,560,700,'6  Результат','Отчёт и CSV\nИсточники и журнал')]
    for x1,y1,x2,y2,title,body in boxes:
        d.rounded_rectangle((x1,y1,x2,y2),radius=18,fill='#EDF3F5',outline='#617D86',width=3)
        d.text((x1+28,y1+30),title,font=bold,fill='#18353E')
        d.multiline_text((x1+28,y1+103),body,font=font,fill='#253E47',spacing=16)
    for start,end in [((560,150),(630,150)),((1170,150),(1240,150)),((1510,270),(1510,440)),((1240,565),(1170,565)),((630,565),(560,565))]:
        d.line((start,end),fill='#526D76',width=8)
        x,y=end; sx,sy=start
        if x>sx: points=[(x,y),(x-20,y-14),(x-20,y+14)]
        elif x<sx: points=[(x,y),(x+20,y-14),(x+20,y+14)]
        else: points=[(x,y),(x-14,y-20),(x+14,y-20)]
        d.polygon(points,fill='#526D76')
    path=ROOT/'submission/structure.png'; path.parent.mkdir(exist_ok=True); image.save(path)
    return path


def build():
    result=json.loads((ROOT/'results/demo/result.json').read_text(encoding='utf-8'))
    doc=Document(); sec=doc.sections[0]
    sec.page_width=Inches(8.5); sec.page_height=Inches(11)
    sec.top_margin=Inches(.7); sec.bottom_margin=Inches(.7)
    sec.left_margin=Inches(.75); sec.right_margin=Inches(.75)
    normal=doc.styles['Normal']; normal.font.name='Arial'; normal.font.size=Pt(11)
    normal.paragraph_format.space_after=Pt(7); normal.paragraph_format.line_spacing=1.08
    for style in ['Title','Heading 1','Heading 2']:
        doc.styles[style].font.name='Arial'; doc.styles[style].font.color.rgb=RGBColor.from_string('000000')
    doc.styles['Title'].font.size=Pt(24)
    doc.styles['Heading 1'].font.size=Pt(17); doc.styles['Heading 2'].font.size=Pt(12)
    footer=sec.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run('Этап 3  •  Елена Горланова  •  ')
    field=OxmlElement('w:fldSimple'); field.set(qn('w:instr'),'PAGE'); footer._p.append(field)
    doc.core_properties.title='Прототип нейроаналитика конкурентов'
    doc.core_properties.author='Елена Горланова'
    def p(s,style=None): return doc.add_paragraph(s,style)
    def h(s): doc.add_heading(s,level=1)
    def table(headers,rows,widths):
        t=doc.add_table(rows=1,cols=len(headers)); t.autofit=False
        for c,w in zip(t.columns,widths): c.width=Inches(w)
        props=t._tbl.tblPr; borders=OxmlElement('w:tblBorders')
        for name in ('top','left','bottom','right','insideH','insideV'):
            b=OxmlElement('w:'+name); b.set(qn('w:val'),'single'); b.set(qn('w:sz'),'4'); b.set(qn('w:color'),'D9D9D9'); borders.append(b)
        props.append(borders)
        for ri,row in enumerate([headers]+rows):
            cells=t.rows[0].cells if ri==0 else t.add_row().cells
            for ci,(cell,value) in enumerate(zip(cells,row)):
                cell.width=Inches(widths[ci]); cell.text=value; cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                tcPr=cell._tc.get_or_add_tcPr(); mar=OxmlElement('w:tcMar')
                for side,val in [('top','90'),('bottom','90'),('left','110'),('right','110')]:
                    e=OxmlElement('w:'+side); e.set(qn('w:w'),val); e.set(qn('w:type'),'dxa'); mar.append(e)
                tcPr.append(mar); shade=OxmlElement('w:shd'); shade.set(qn('w:fill'),'244B59' if ri==0 else ('F1F5F7' if ri%2==0 else 'FFFFFF')); tcPr.append(shade)
                for para in cell.paragraphs:
                    para.paragraph_format.space_after=Pt(2); para.paragraph_format.line_spacing=1.02
                    for run in para.runs:
                        run.font.size=Pt(10)
                        if ri==0: run.bold=True; run.font.color.rgb=RGBColor(255,255,255)
            if ri==0:
                repeat=OxmlElement('w:tblHeader'); t.rows[0]._tr.get_or_add_trPr().append(repeat)
        p('')
        return t
    p('Прототип нейроаналитика конкурентов','Title')
    p('Этап 3  •  Елена Горланова  •  27 октября 2026 года')
    p('Подготовлен работающий прототип на принятой базе этапа 2. Он проверяет происхождение фактов, показывает предложения компаний по общим критериям и формирует отчёт с проверяемыми гипотезами. Первый результат — шесть критериев, 13 наблюдений и три гипотезы на данных двух компаний. Полный рыночный анализ пока не выполнен.')
    h('1 Тема и описание задачи')
    p('Тема проекта — нейроаналитик конкурентов для Immigration Relocator. Задача — сократить ручную подготовку сопоставления публичных услуг релокационных компаний и сделать основания каждого вывода проверяемыми по цитате, URL и дате.')
    p('Целевая область — Португалия и Испания, комплексная релокация и отдельные юридические услуги для русскоязычной аудитории. Для первого сквозного сценария выбран фактически собранный португальский корпус Immigration Relocator и Migrun. Восемь конкурентов согласованы, но подробные данные семи остальных ещё не собраны.')
    h('2 База и обработка базы')
    p('Этап 2 принят 27.10.2026. В нём сохранены 175 черновых фактов последнего LLM-опыта, три записи карантина, исходные страницы и реальные запросы и ответы моделей. Принятие учебного этапа не означает смыслового утверждения всех 175 записей.')
    p('Этап 3 использует минимальную копию двух страниц услуг от 22.10.2026, очищенные тексты, их фрагменты, реестр компаний и SHA256-манифест. Из 175 записей по явному соответствию исследователя выбраны 13 наблюдений для шести критериев. Контекст португальских страниц указан отдельно; исходные country и review_status не переписываются.')
    p('Проверяются байты входов, компания, источник, точная цитата, её смещение и числовая цена. Карантинная цена NIF Migrun 109 EUR не включается. Клиентские договоры, CRM, переписка, личные данные и API-ключи в базу демонстрации не входят. Снимок не выдаётся за текущие цены рынка.')
    for title,url in [('Снимок Immigration Relocator дополнительные услуги','https://immigration-relocator.com/pt-otherservices'),('Снимок Migrun пакеты услуг Португалия','https://www.migrun.tech/ru/portugal/services-in-portugal/assistance-packages')]:
        hyperlink(p(''),title,url)
    doc.add_page_break()
    h('3 Структура нейросотрудника')
    doc.add_picture(str(diagram()),width=Inches(7))
    p('Черновой отчёт Python создаётся до ручной проверки. Блок 5 — внешняя проверка, в прогоне не выполненная. LLM извлекла данные в этапе 2; новый вызов выключен.')
    table(['Блок','Назначение и граница ответственности'],[
        ('1 Вход','Пользователь выбирает свою компанию, подмножество согласованных конкурентов и страну. Python читает сохранённый корпус и настройки.'),
        ('2 Проверка','Python проверяет хэши, ссылки на источник, компанию, цитату и сумму. Ошибки не превращаются в успешные наблюдения.'),
        ('3 Сопоставление','Шесть явных критериев связывают выбранные записи. Неизвестное остаётся неизвестным; конфликт 170/350 EUR сохраняется. Численный рейтинг заблокирован.'),
        ('4 Гипотезы','Python формирует три действия по правилам с основаниями и метрикой. Необязательная LLM может предложить формулировки только по переданным доказательствам.'),
        ('5 Решение человека','Владелец услуги уточняет состав, актуальность цены и приоритет гипотез. Проверка цитаты не подменяет такую оценку.'),
        ('6 Результат','Сохраняются JSON, CSV, Markdown, HTML и журнал конфигурации с хэшами входа и кода. Отчёт содержит источники и ограничения.')],[1.4,5.6])
    p('Использованы подходы курса: функции и модули из раздела 17, табличные данные из 19, роли system/user и Colab Secrets из 21, корпус и метаданные из 22–23. HTTP и BeautifulSoup из раздела 27 применены в предшествующем сборщике. Для маленькой структурированной выборки векторный поиск не требуется.')
    doc.add_page_break()
    h('4 Рабочий прототип и запуск')
    linkp=p(''); hyperlink(linkp,'Открыть отдельный Colab прототипа этапа 3',COLAB)
    linkp=p(''); hyperlink(linkp,'Открыть папку материалов этапа 3 на Google Drive',FOLDER)
    p('В Colab встроены код и минимальный корпус. Основной сценарий запускается без монтажа Drive, установки библиотек, секретов и новых платных запросов. Сохранённые выводы ноутбука получены реальным локальным исполнением; состояние повторного запуска Colab отражается в журнале проверки комплекта.')
    for line in ['1. Откройте Colab и выберите «Выполнить все».','2. В CONFIG оставьте Portugal для основного сценария или задайте Spain для контроля отсутствия данных.','3. Проверьте покрытие компаний, сравнение, три гипотезы и результат девяти тестов.','4. Откройте HTML-отчёт в последней ячейке. Для скачивания архива включите DOWNLOAD=True.']:
        p(line)
    p('Локальный запуск из корня проекта:')
    p('python -B stage_3/code/analyst.py')
    table(['Файл результата','Что можно проверить'],[
        ('result.json','Покрытие, шесть критериев, наблюдения, ссылки, гипотезы и ограничения.'),
        ('comparison.csv','Табличный результат по всем девяти выбранным компаниям, включая отсутствие наблюдений.'),
        ('report.md и report.html','Читаемый отчёт с точными цитатами, URL, датами и статусом проверки.'),
        ('run.json','Настройки, SHA256 манифеста и кода, режим, время и отсутствие новых API-вызовов.')],[2.1,4.9])
    p('Новая формулировка через ProxyAPI выключена: RUN_LLM=False. При явном включении используется PROXYAPI_KEY из Colab Secrets, одна попытка до 2500 выходных токенов без повторов. Запрос, ответ и usage сохраняются без ключа; неизвестные ID доказательств отклоняются. Смысловая корректность текста LLM требует ручной проверки.')
    p('Luna выбрана предварительно на основании извлечения этапа 2. Это не оценка качества рекомендаций: отдельного сравнения моделей для этой задачи ещё нет. В основном результате этапа 3 новых оплаченных вызовов нет; ранее оплаченные результаты не пересоздавались.')
    doc.add_page_break()
    h('5 Первые результаты и выводы')
    p('Сквозной локальный прогон завершён: 6 критериев, 13 наблюдений, 3 гипотезы; в критериях 8 наблюдений своей компании и 5 Migrun. Семь остальных конкурентов обозначены как не исследованные для выбранной страны. Программа не создаёт общий рейтинг компаний.')
    table(['Критерий','Наблюдение по снимку и ограничение'],[
        ('Входная консультация','Immigration Relocator — 150 EUR; Migrun — 40 EUR за 30 минут и 70 EUR за 60 минут. Длительность и состав собственной консультации не установлены этой цитатой.'),
        ('Налоговая консультация','На странице своей компании сохранены два блока 170 и 350 EUR. Нельзя выбрать актуальную цену автоматически.'),
        ('NIF','150 EUR у своей компании. Цена конкурента из карантина исключена; вывод об отсутствии услуги не делается.'),
        ('Продление ВНЖ','Повторные блоки 500 EUR своей компании не суммируются. Сопоставимое предложение Migrun в выборке не установлено.'),
        ('Пакеты сопровождения','Migrun: Check-up 530 EUR, Standard 1290 EUR, Premium 3490 EUR. Это разные продукты; они не приравниваются к консультации.'),
        ('Регистрация компании','Сумма 950 EUR в двух блоках сопровождается разными пометками государственных сборов. Полная сопоставимая стоимость не установлена.')],[1.6,5.4])
    summaries={
        'H1':'Владелец услуги сверяет блоки 170 и 350 EUR, состав и срок действия. После подтверждения — различить предложения или исправить устаревший блок. Метрика: ноль неразрешённых расхождений.',
        'H2':'Проверить карточку с длительностью, результатом и исключениями консультации. Сравнить долю квалифицированных обращений и вопросов о составе. Цену 150 EUR не снижать по несопоставимым предложениям 40/70 EUR.',
        'H3':'Проверить на интервью макет сравнения состава собственных пакетов. Метрика: доля участников, верно выбравших подходящий состав. Линейка Migrun — основание гипотезы, а не образец для копирования цен.'}
    for hitem in result['recommendations']:
        doc.add_heading(hitem['id']+' '+hitem['title'],level=2)
        p(summaries[hitem['id']])
    p('Вывод: прототип помогает находить неоднозначности и формировать задачи на уточнение предложения. Рост продаж, конверсия, качество юридических услуг и смысловая точность полного набора не измерены. Конкретные цены служат наблюдениями снимка, а не рекомендациями их менять.')
    doc.add_page_break()
    h('6 Проверки и план дальнейшей работы')
    p('Девять локальных проверок прошли. Встроенные шесть кодовых ячеек ноутбука также реально выполнены локально. Тест с искусственной ошибкой транспорта не является вызовом модели. Отдельный сценарий Spain вернул 0 критериев, 0 наблюдений и 0 гипотез.')
    table(['Проверка','Результат'],[
        ('Две разные цены налоговой консультации','Обе сохранены; рейтинг заблокирован.'),
        ('Семь конкурентов без подробного корпуса','Явно обозначены как не исследованные.'),
        ('Испания без данных','Нет португальских выводов и рекомендаций.'),
        ('Неподтверждённая компания','Конфигурация отклонена.'),
        ('Подмена цитаты, компании и суммы','Несоответствия обнаружены.'),
        ('Выдуманный ID в ответе LLM','Ответ не принимается.'),
        ('Отчёт без сети и экранирование HTML','API не вызывается; HTML-текст безопасно отображается.'),
        ('Ошибка транспорта API','Одна попытка, безопасный журнал без секрета.'),
        ('Подмена входного файла','Проверка SHA256 не проходит.')],[3.3,3.7])
    p('Дальнейшая работа выполняется в следующем порядке:')
    for line in [
        '1. Разметить смысловую корректность выбранных фактов и согласовать с владельцем актуальные цены, состав и государственные сборы.',
        '2. Зафиксировать сопоставимые категории, валюту, длительность, включённые платежи и статус цены. Только затем разрешать численные сравнения.',
        '3. Собрать и проверить Испанию и остальных семь конкурентов. Не переносить наблюдения одной страны в другую.',
        '4. Подготовить эталон качества гипотез. Сравнить Luna, Claude и Gemini при одинаковых входах и ограничении бюджета; учитывать стоимость корректного результата.',
        '5. Проверить три гипотезы на интервью или согласованном тесте карточек услуг. До измерения не заявлять бизнес-эффект.',
        '6. Добавить подтверждение человеком, версии базы и новый сбор в интерфейс. Сохранить этап 2 и исторические модельные ответы неизменными.']:
        p(line)
    output=ROOT/'submission/Этап_3_Прототип_нейроаналитика.docx'; output.parent.mkdir(exist_ok=True)
    for style in doc.styles:
        if style.style_id in ('Title','Subtitle'):
            for border in style.element.xpath('./w:pPr/w:pBdr'):
                border.getparent().remove(border)
    doc.save(output); print(output)


if __name__=='__main__': build()
