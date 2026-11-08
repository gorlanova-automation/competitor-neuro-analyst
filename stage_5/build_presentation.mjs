import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(import.meta.url);
const runtime='C:/Users/Lena/.cache/codex-runtimes/codex-primary-runtime/dependencies';
process.env.RUNTIME_NODE_MODULES=runtime+'/node/node_modules';
const skill='C:/Users/Lena/.codex/plugins/cache/openai-primary-runtime/presentations/26.1103.10131/skills/presentations';
const {Presentation,PresentationFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool',{paths:[runtime+'/node/node_modules']})).href);
const {finalizePresentation,resolvePresentationFont}=await import(pathToFileURL(skill+'/container_tools/artifact_tool_utils.mjs').href);
const root=path.resolve('.'),build=path.join(root,'stage_5/build'),output=path.join(root,'stage_5/output');
await fs.mkdir(build,{recursive:true});await fs.mkdir(output,{recursive:true});
const font=resolvePresentationFont({fontFamily:'Arial'});
const p=Presentation.create({slideSize:{width:1280,height:720}});
const dark='#173D30',ink='#173D30',muted='#53675D',paper='#F6F7F2',accent='#DDBB72';
function text(slide,value,x,y,w,h,size=28,color=ink,bold=false){const s=slide.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});s.text=value;s.text.style={typeface:font,fontSize:size,color,bold};return s;}
function slide(title,notes){const s=p.slides.add();s.background.fill=paper;text(s,title,72,50,1136,90,44,ink,true);s.speakerNotes.text=notes;return s;}
function body(s,lines,y=176){lines.forEach((line,i)=>text(s,line,76,y+i*100,1124,88,30));}
function table(s,values,y=172,h=410,widths){const t=s.tables.add({rows:values.length,columns:values[0].length,left:72,top:y,width:1136,height:h,columnWidths:widths,values});t.borders.assign({style:'solid',fill:'#CDD8D0',width:1});for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){let cell=t.getCell(r,c);cell.fill=r===0?dark:paper;cell.text.style={typeface:font,fontSize:r===0?25:24,color:r===0?'#FFFFFF':ink,bold:r===0};}return t;}
const repo='https://github.com/gorlanova-automation/competitor-neuro-analyst';
const source=relative=>repo+'/blob/main/'+relative;
{
 const s=p.slides.add();s.background.fill=dark;
 text(s,'Нейро-аналитик\nконкурентов',76,145,1100,200,70,'#FFFFFF',true);
 text(s,'От сайта компании к отчёту\nс проверяемыми источниками',80,400,1000,120,34,'#DDE8DF');
 text(s,'Елена Горланова · дипломный проект',80,620,1040,40,24,accent);
 s.speakerNotes.text='0:00–0:50. Проект помогает исследовать предложения и коммуникацию конкурентов. Его задача — собрать основания для решения, а не автоматически объявить лучшую компанию. Материалы и код: '+repo;
}
{
 const s=slide('Задача исследования','0:50–2:00. На старте сравнение сводилось к нескольким точным услугам и ценам. Пользователю нужен ассортимент целиком, площадки продвижения, публикации, тон и визуальная подача. Разные пакеты нельзя ранжировать по цене без состава и условий.');
 body(s,['Собрать предложение каждой компании в границах доступных источников.','Показать сходства и различия ассортимента и коммуникации.','Связать каждое наблюдение с цитатой, страницей или снимком.','Превратить различия в гипотезы для проверки владельцем бизнеса.']);
}
{
 const s=slide('Границы анализа','2:00–3:10. Свой бизнес и конкурентов подтверждает пользователь. Не все наблюдения можно получить автоматически: HTML не доказывает визуальные свойства, а ссылка на площадку не является корпусом публикаций. '+source('stage_3/code/market_analysis_prompt.md'));
 table(s,[['Направление','Что проверяем'],['Ассортимент','Направления, пакеты, дополнения, аудитории и условия'],['Продвижение','Площадки, статьи, лид-магниты, переходы к заявке'],['Публикации и тон','Полученные тексты, темы, аргументы, обращения'],['Визуальная подача','Реально просмотренные снимки; отдельно от HTML']],172,420,[340,796]);
}
{
 const s=slide('Собранная база: снимок 5 ноября','3:10–4:30. Это ограниченная выборка 12 компаний, включая свою. Страницы получены для 10 компаний. 34 — уникальные страницы сайтов; 20 редакционных страниц и Telegram учитываются как отдельные части исследования. Визуальные заметки — ручной просмотр первых экранов помощником. Источник: '+source('stage_3/research/market_20261105/market.json'));
 table(s,[['Материал','Фактический объём'],['Компании в каталоге','12; сайты получены для 10'],['Страницы сайтов','34 уникальные'],['Редакционные страницы','20'],['Telegram','23 сообщения у 3 компаний'],['Первые экраны сайтов','10 ручных просмотров']],165,455,[650,486]);
}
{
 const s=slide('Пользовательский сценарий','4:30–5:40. Главная функция run_project управляет состоянием проекта. Профиль и выбранные конкуренты подтверждаются до анализа. Недоступность источника отображается, а предоставленный пользователем текст не выдаётся за HTTP-сбор. '+source('stage_4/workflow.py'));
 body(s,['Сайт → черновик профиля → исправление и подтверждение','Поисковые запросы → кандидаты → подтверждённый список','Сбор доступных страниц → причины ошибок → сохранённые источники','Текстовая выборка → модельный черновик → отчёт и проверка'],180);
}
{
 const s=slide('Устройство приложения','5:40–7:00. Локальный FastAPI обслуживает интерфейс и сохраняет проекты в var/projects. Исторический SQLite API этапа 3 остаётся отдельно. Colab вызывает ту же главную функцию. Модельный вызов включается отдельно; ключ остаётся в Colab Secrets. '+source('app/main.py')+' '+source('stage_4/workflow.py'));
 table(s,[['Блок','Ответственность'],['Интерфейс / Colab','Ввод сайта, редактирование профиля, подтверждения'],['Загрузчик Python','HTTPS, robots, повторы, лимиты и статусы ошибок'],['Анализ и проверки','Цитаты, источники, модельный JSON и карантин'],['Сохранение и отчёт','Версии запусков, HTML, JSON, история проекта']],175,410,[370,766]);
}
{
 const s=slide('Эксперименты с моделями и промптами','7:00–8:30. Пять реальных опытов 22 октября используют одинаковые входные тексты. Метрика — восемь контрольных цен в двух фрагментах, а не точность всей базы. Gemini нарушала контракт amount, Claude получил усечённый ответ: это не доказывает общую непригодность моделей. Полные настройки, ответы, промпты и тарифные оценки: '+source('stage_4/experiments.json'));
 table(s,[['Вариант','Контроль','Наблюдение'],['Luna · исходный','8/8','Короткие цитаты не всегда доказывают связь'],['Luna · evidence v2','8/8','Меньше расход; часть полей потеряна'],['Claude Haiku · v2','3/8','Усечение ответа и проблемы цитирования'],['Gemini Flash-Lite · v2','0/8','Суммы в неподходящих полях'],['Luna · atomic v3','8/8','Рабочий пилот; 175 черновых записей']],165,465,[380,170,586]);
}
{
 const s=slide('Выбор модели по задаче','8:30–9:40. Поиск, загрузка, хэши и проверка цитат не требуют LLM. Luna — предварительный рабочий выбор по сохранённому пилоту, а не универсальный победитель. 7 ноября: первый запрос потратил 2500 токенов на рассуждения без ответа. Второй с reasoning_effort=none дал 1190 токенов содержимого; из 9 выводов помощник оставил или исправил 6 и отклонил 3. Это не независимая разметка и не приёмка Еленой. Источники: '+source('stage_2/docs/model_selection.md')+' https://developers.openai.com/api/docs/models/gpt-6-luna');
 body(s,['Код: загрузка, очистка, хранение, проверка цитат и ссылок.','Luna: ограниченный смысловой черновик по полученным текстам.','Claude / Gemini: сравнение на одинаковых данных и контракте.','Человек: профиль, конкуренты и отдельная версия принятых выводов.']);
}
{
 const s=slide('Проверяемость результата','9:40–10:50. Для каждой цитаты сохраняется SHA256 исходного текста. Модель не может сослаться на неизвестный source_id. Неполный ответ или выдуманная цитата отправляются в карантин без автоматического повторного запроса. Проверка формата и точной цитаты не гарантирует правильность интерпретации. '+source('stage_4/semantic.py'));
 body(s,['Наблюдение → дословная цитата → URL → сохранённый текст.','Запрет или ошибка доступа → пробел данных, а не отсутствие услуги.','Реклама компании → заявление, а не доказанное качество.','Гипотеза → действие для проверки, а не обещание роста продаж.']);
}
{
 const s=slide('Демонстрация интерфейса','10:50–12:40. Открыть локальное приложение, показать этапы профиля и подтверждения конкурентов, затем сохранённый отчёт с источниками. 7 ноября помощник прошёл UI: Immigration Relocator → OKNO и MONOLITE → реальный HTTP-сбор трёх сайтов. Для этого прогона LLM не вызывалась. '+source('stage_4/experiments.json'));
 const screenshot=path.join(root,'stage_4/review/live_workflow_20261107.png');
 try{await fs.access(screenshot);s.images.add({blob:new Uint8Array(await fs.readFile(screenshot)),contentType:'image/png',fit:'contain',position:{left:72,top:160,width:720,height:480}});text(s,'Профиль и конкуренты\nподтверждаются явно.\n\nHTML и JSON сохраняются\nдля повторной проверки.',830,210,360,360,29);}catch{body(s,['Сайт → подтверждение профиля','Выбор конкурентов → сбор','HTML-отчёт → цитаты и источники']);}
}
{
 const s=slide('Проверка другой отрасли: SHIFT','12:40–13:50. SHIFT — сервис анализа коротких видео. Исследование нельзя смешивать с релокацией. На сохранённых реальных текстах прогнан тот же сценарий: новая компания, описание рынка, выбранный кандидат и отчёт. География и аудитория SHIFT остаются пользовательским решением. '+source('stage_4/colab_app.py')+' '+source('stage_3/cases/shift/own_source.json'));
 table(s,[['Релокация','SHIFT'],['ВНЖ, документы, сопровождение','Анализ и обратная связь по видео'],['Португалия / Испания','Рынок уточняет пользователь'],['Свой профиль и источники','Отдельный профиль и источники'],['Сохранённый демонстрационный прогон','Тот же код, другие входные данные']],180,390,[568,568]);
}
{
 const validation=JSON.parse(await fs.readFile(path.join(root,'stage_4/results/validation.json'),'utf-8'));
 const s=slide('Проверки приложения','13:50–15:00. Тесты проверяют отрицательные сценарии, сохранение истории, происхождение цитат, подтверждения и модельный контракт. Они не измеряют полноту рынка. В тестах модельный транспорт подставлен явно; реальные вызовы в эти цифры не включены. '+source('stage_4/results/validation.json'));
 text(s,String(validation.tests_run),76,170,400,170,130,ink,true);text(s,'проверок прошли\nбез ошибок',500,208,650,130,42,ink,true);
 text(s,'Ошибки сети · изменённые источники · выдуманные цитаты\nПропущенные подтверждения · повторные запуски · сохранение отчёта',80,470,1120,140,28);
}
{
 const s=slide('Ограничения и участие пользователя','15:00–16:20. Ограничения являются частью рабочего сценария, а не скрытыми предположениями. Закрытые площадки могут потребовать предоставленный текст или снимок; автоматическое обнаружение кандидатов зависит от доступа к поиску. Визуальный аудит первого экрана не является аудитом всего бренда. '+source('stage_4/README.md'));
 body(s,['Часть сайтов и площадок недоступна для автоматического сбора.','Публикации получены по выборке; частота и эффективность не измерены.','Смысловые выводы требуют проверки; визуал — реальных изображений.','GitHub Pages показывает базу; новый сбор работает локально / в Colab.']);
}
{
 const s=slide('Результат и дальнейшее развитие','16:20–17:30. Показать файлы этапа 4, финальный Colab и неизменённую демонстрацию этапа 3. Следующий шаг — независимый эталон по ассортименту и коммуникации, повторное сравнение моделей, визуальные источники и расширение адаптеров. Публичный production с аккаунтами и многопользовательскими заданиями — отдельное внедрение. '+repo);
 body(s,['Приложение соединяет сбор, подтверждения и отчёт с источниками.','Оригинальный этап 3 сохранён отдельно и проверяется по хэшам.','Эксперименты воспроизводимы; факты и ограничения доступны для разбора.','Следующие проверки: смысловая разметка, визуал и дополнительные площадки.']);
}
const draft=path.join(build,'defense-draft.pptx');
if(!process.argv.includes('--finalize-only')){
await (await PresentationFile.exportPptx(p)).save(draft);
for(let index=0;index<p.slides.items.length;index++){
 const image=await p.export({slide:p.slides.items[index],format:'png',scale:1});
 await fs.writeFile(path.join(build,`slide-${String(index+1).padStart(2,'0')}.png`),new Uint8Array(await image.arrayBuffer()));
}
}
const finalPath=path.join(output,'Нейроаналитик_защита_20261107_v4.pptx');
const result=await finalizePresentation({workspaceDir:root,candidatePath:draft,finalPath,
 pythonExecutable:runtime+'/python/python.exe',integrityValidatorPath:skill+'/container_tools/inspect_presentation_package_integrity.py',
 layoutValidatorPath:skill+'/container_tools/inspect_presentation_layout_geometry.py',
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
 explicitTotalSlideCount:14,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
 fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation-v4.json')});
console.log(JSON.stringify({slides:p.slides.items.length,font,finalPath,result}));

