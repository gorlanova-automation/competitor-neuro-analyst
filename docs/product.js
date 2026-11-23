'use strict';
const $=id=>document.getElementById(id);let state=null,report=null,uploads={},busy=false,exportUrl=null;
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const link=(text,url)=>{const a=el('a',text);try{const u=new URL(url);if(u.protocol==='https:'&&!u.username&&!u.password){a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}}catch{}return a;};
function error(message){$('error').textContent=message;$('error').hidden=!message;}
const appBase=location.pathname.includes('/stand/')?location.pathname.split('/stand/')[0]:'';
async function api(path,body){const r=await fetch(appBase+'/api/'+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});let value;try{value=await r.json();}catch{throw Error('Сервер исследования недоступен. Обновите страницу через минуту.');}if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:'Проверьте заполненные поля и адреса сайтов.');return value;}
function panel(name){for(const id of ['profile-panel','competitor-panel','collect-panel','busy','results'])$(id).hidden=id!==name;}
async function history(){const list=await api('research');$('history').replaceChildren();if(!list.length)$('history').append(el('p','Пока нет исследований. Начните с сайта компании.','hint'));for(const p of list){const b=el('button',p.profile?.company_name||p.url);b.append(el('small',new Date(p.updated_at||p.created_at).toLocaleString('ru-RU')));b.onclick=()=>openProject(p.id);$('history').append(b);}}
async function openProject(id){if(busy)return;try{state=await api('research/'+id);location.hash=id;render();}catch(e){error(e.message);}}
function render(){
 $('intro').hidden=true;$('project').hidden=false;$('project-name').textContent=state.profile?.company_name||state.url;$('saved').textContent='Сохранено';
 if(!state.profile){panel('profile-panel');$('profile-form').hidden=true;error('Страница не получена. Начните новое исследование и предоставьте её текст, либо проверьте адрес сайта.');return;}
 $('profile-form').hidden=false;
 if(!state.profile_confirmed){showProfile();return;}
 if(!state.competitors_confirmed){showCompetitors();return;}
 if(state.report){loadReport();return;}
 showCollect();
}
function showProfile(){panel('profile-panel');for(const key of ['company_name','summary','market_scope','search_terms'])$('profile-form').elements[key].value=state.profile[key]||'';$('profile-source').replaceChildren(link('Профиль собран по сайту '+state.url,state.url));}
function row(candidate={}){
 const node=el('div',undefined,'competitor-row');
 for(const [name,title,value] of [['name','Название компании',candidate.name||''],['url','Сайт компании',candidate.url||'']]){
  const label=el('label',title),input=el('input');input.name=name;input.value=value;input.required=true;input.type=name==='url'?'url':'text';if(name==='name')input.maxLength=200;label.append(input);node.append(label);
 }
 const find=el('button','Найти сайт по названию','secondary');find.type='button';
 const results=el('div',undefined,'lookup-results');
 find.onclick=async()=>{
  const name=node.querySelector('[name=name]').value.trim();if(name.length<2){error('Введите название компании.');return;}
  find.disabled=true;results.replaceChildren(el('p','Ищем сайт…','hint'));
  try{const value=await api('research/'+state.id+'/lookup',{name});results.replaceChildren();
   if(!value.candidates.length)results.append(el('p','Подходящий сайт в этой выдаче не найден. Можно указать адрес вручную.','hint'));
   for(const c of value.candidates){const option=el('button',c.label+' · '+new URL(c.url).hostname,'secondary');option.type='button';option.onclick=()=>{node.querySelector('[name=url]').value=c.url;results.replaceChildren(el('p','Выбран сайт: '+c.url,'hint'));};results.append(option);}
  }catch(e){results.replaceChildren(el('p',e.message,'hint'));}finally{find.disabled=false;}
 };
 const remove=el('button','Удалить','quiet');remove.type='button';remove.onclick=()=>node.remove();
 node.append(find,remove,el('small',candidate.origin||'Добавлено вручную'),results);$('competitor-list').append(node);
}
function showCompetitors(){panel('competitor-panel');$('competitor-list').replaceChildren();const candidates=state.competitors_confirmed?state.competitors:state.suggestions||state.competitors||[];const seen=new Set();for(const c of candidates){if(seen.has(c.url))continue;seen.add(c.url);row(c);}if(!seen.size)row();$('browser-search').href='https://duckduckgo.com/?q='+encodeURIComponent(state.search?.query||state.search_queries?.[0]||state.profile.search_terms);const search=state.search;const searchMessages={budget_exhausted:'Лимит поисковых запросов приложения исчерпан. Используйте поиск в браузере.',not_configured:'Поиск Tavily ещё не подключён. Можно открыть поиск в браузере или добавить компании вручную.',authentication_failed:'Поиск не принял ключ доступа. Обратитесь к владельцу приложения; ручной список доступен.',rate_limited:'Поисковый сервис временно ограничил запросы. Повторите позднее или используйте браузер.',quota_exhausted:'Кредиты поиска закончились. Платное пополнение автоматически не включается; используйте ручной поиск.',timeout:'Поиск не ответил вовремя. Повторите позднее или добавьте сайты вручную.'};$('search-state').textContent=searchMessages[search?.status]||(search?.status==='ok'?(state.suggestions?.length?'Проверьте предложенных конкурентов. Вы можете добавить компанию по названию или сайту.':'В полученной выдаче подходящие компании не подтверждены. Добавьте известного конкурента по названию или сайту.'):(search?'Свежий поиск сейчас недоступен. Можно проверить сохранённые предложения или добавить сайты вручную. Подробная причина сохранена в истории исследования.':'Проверьте список и добавьте известные компании.'));}
function showCollect(){panel('collect-panel');$('collect-summary').textContent='Ваша компания. Конкурентов: '+state.competitors.length+'. Соберём сайты и публичные Telegram-публикации, выполним ИИ-сравнение и проверим рекомендации. Результат сохранится здесь автоматически.';}
async function command(body,id=state?.id){
 if(busy)return;error('');busy=true;$('intro').hidden=true;$('project').hidden=false;panel('busy');$('job-step').textContent='Запускаем задание';$('job-time').textContent='';const started=Date.now();
 try{let job=body?await api(id?'research/'+id:'research',body):await api('jobs/'+id);sessionStorage.setItem('neuro-job',job.id);while(['queued','running'].includes(job.status)){$('job-step').textContent=job.step;$('job-time').textContent='Прошло '+Math.round((Date.now()-started)/1000)+' сек. Повторы загрузки ограничены; недоступные сайты не останавливают весь отчёт.';await new Promise(r=>setTimeout(r,1200));job=await api('jobs/'+job.id);}sessionStorage.removeItem('neuro-job');if(job.project_id)state=await api('research/'+job.project_id);if(job.status==='failed')throw Error(job.error);location.hash=state.id;render();await history();}
 catch(e){error(e.message);if(state&&body?.action==='confirm_competitors')panel('competitor-panel');else if(state&&body?.action==='confirm_profile')panel('profile-panel');else if(state)render();else{$('intro').hidden=false;$('project').hidden=true;}}
 finally{busy=false;}
}
function evidence(parent,e){const box=el('div',undefined,'evidence');box.append(el('small',e.company||''),el('blockquote',e.quote),link('Источник ↗',e.url));if(e.source_method==='user_uploaded_text')box.append(el('small',' · Текст предоставлен пользователем'));parent.append(box);}
function showResult(value,saved=false){report=value;comparisonSelection=[];panel('results');$('rerun').hidden=saved;$('result-summary').textContent=(saved?'Загруженный результат · ':'')+'Компаний: '+report.companies.length+' · '+report.companies.reduce((n,c)=>n+c.pages_ok,0)+' полученных страниц. Предварительный обзор: проверьте смысл цитат и актуальность предложений.';if(exportUrl)URL.revokeObjectURL(exportUrl);exportUrl=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));$('download').href=exportUrl;$('download').download='research-result.json';$('download').textContent='Скачать копию результата';comparison();companyCards();actions();if(!saved&&report.ai_analysis?.synthesis_error){const retry=el('button','Повторить итоговый анализ','secondary');retry.onclick=()=>command({action:'analyze'});$('actions').append(retry);}if(report.ai_analysis)$('result-summary').textContent='Компаний: '+report.companies.length+' · '+report.companies.reduce((n,c)=>n+c.pages_ok,0)+' страниц · '+report.companies.reduce((n,c)=>n+c.posts_collected,0)+' публикаций Telegram. Источники раскрываются под выводами.';}
async function loadReport(){try{showResult(await api('research/'+state.id+'/result'));}catch(e){error(e.message);showCollect();}}
async function openExample(){try{error('');const response=await fetch('product-example.json?v=20261122-plan');if(!response.ok)throw Error('Сохранённый пример недоступен.');const value=await response.json();$('intro').hidden=true;$('project').hidden=false;$('project-name').textContent=value.profile.company_name;$('saved').textContent='Пример исследования';location.hash='example';showResult(value,true);}catch(e){error(e.message);}}
function publishedMode(){
    const notice=$('connection');
    const launch=el('a','Открыть приложение','secondary');
    launch.href='https://neuroanalyst.fghk.ru/';
    notice.replaceChildren(el('p','Исследование от начала до результата — в одном приложении.'),launch,
        el('p','Введите сайт, подтвердите профиль и выберите конкурентов. Анализ и сохранение результата выполняются автоматически.','hint'));
    notice.className='notice';
    $('start-form').hidden=true;
    $('new').textContent='На главную';
    $('history-section').hidden=true;$('logout').hidden=true;
}
function aiEvidence(parent,cell){if(!cell.refs?.length)return;const d=el('details');d.append(el('summary','Основания · '+cell.refs.length));cell.refs.forEach(r=>evidence(d,r));parent.append(d);}
function telegramCoverage(parent,c){const samples=c.publication_samples||[];parent.append(el('p','Прочитано сообщений: '+c.posts_collected+'. Частота и эффективность по неполному превью не оцениваются.','hint'));if(!samples.length)parent.append(el('p','Telegram-ссылка не обнаружена в полученных страницах. Это не доказательство отсутствия канала.','hint'));const labels={sample_collected:'Публикации получены',not_a_public_feed:'Контакт, приглашение или бот',no_public_messages_observed:'В превью нет доступных сообщений',not_sampled_limit:'Не проверено: лимит выборки',robots_disallowed:'Загрузка ограничена robots.txt',challenge_page:'Защитная проверка'};for(const f of samples){const box=el('div',undefined,'evidence');box.append(link(f.url,f.url),el('p',(labels[f.status]||'Источник недоступен: '+f.status)+' · сообщений: '+f.posts));if(f.first_published_at)box.append(el('p','Период полученной выборки: '+f.first_published_at.slice(0,10)+' — '+f.last_published_at.slice(0,10)));if(f.found_on)box.append(link('Ссылка найдена на сайте ↗',f.found_on));parent.append(box);}if(c.telegram_discovery){const d=c.telegram_discovery;parent.append(el('p','Дополнительный поиск: публичные t.me-страницы через Tavily. Это не поиск внутри приложения Telegram.','hint'));for(const r of d.ai_review||[]){const box=el('div',undefined,'evidence');box.append(link(r.url,r.url),el('p',({likely:'Вероятный кандидат · подтвердите принадлежность',uncertain:'Принадлежность не установлена',reject:'ИИ отклонил совпадение'})[r.verdict]),el('p',r.reason));parent.append(box);}const details=el('details');details.append(el('summary','Вся поисковая выдача · '+d.candidates.length));for(const x of d.candidates){details.append(link(x.label,x.url),el('p',x.snippet||''));}parent.append(details);if(!d.candidates.length)parent.append(el('p','В этой проверенной выдаче кандидатов нет. Канал может существовать.'));}}

let comparisonSelection=[];
function comparison(){
    if(!comparisonSelection.length){
        const own=report.companies.findIndex(c=>c.role==='own');
        const preferred=report.companies.map((c,i)=>i).filter(i=>i!==own)
            .sort((a,b)=>(report.companies[b].analysis?.status==='ai_draft')-(report.companies[a].analysis?.status==='ai_draft'));
        comparisonSelection=[...(own>=0?[own]:[]),...preferred].slice(0,3);
    }
    const count=comparisonSelection.length;
    const controls=el('div',undefined,'comparison-selectors');
    for(let slot=0;slot<count;slot++){
        const label=el('label','Компания '+(slot+1));
        const select=el('select');select.setAttribute('aria-label','Компания '+(slot+1));
        report.companies.forEach((company,index)=>{
            const option=el('option',company.name);
            option.value=String(index);
            option.disabled=comparisonSelection.includes(index)&&comparisonSelection[slot]!==index;
            option.selected=comparisonSelection[slot]===index;
            select.append(option);
        });
        select.onchange=()=>{
            const index=Number(select.value);
            if(comparisonSelection.includes(index))return;
            comparisonSelection[slot]=index;comparison();
        };
        label.append(select);
        if(count>1){
            const remove=el('button','Убрать','quiet');remove.type='button';
            remove.setAttribute('aria-label','Убрать компанию '+(slot+1));
            remove.onclick=()=>{comparisonSelection.splice(slot,1);comparison();};
            label.append(remove);
        }
        controls.append(label);
    }
    const add=el('button','+ Добавить компанию','secondary');add.type='button';
    add.disabled=count===report.companies.length;
    add.onclick=()=>{
        const next=report.companies.findIndex((_,index)=>!comparisonSelection.includes(index));
        if(next<0)return;
        comparisonSelection.push(next);comparison();
    };
    const selected=comparisonSelection.map(i=>report.companies[i]);
    const wrap=el('div',undefined,'table-wrap'),table=el('table',undefined,'selected-comparison'),head=el('tr');
    table.style.minWidth=Math.max(760,145+count*280)+'px';
    head.append(el('th','Критерий'));
    comparisonSelection.forEach(i=>{
        const c=report.companies[i],th=el('th'),button=el('button',c.name,'quiet');
        button.onclick=()=>companyDetails(i);
        th.append(button,el('small',c.role==='own'?'Ваша компания':'Конкурент'));head.append(th);
    });
    table.append(head);
    for(const [key,label] of Object.entries(report.dimensions)){
        const tr=el('tr');tr.append(el('th',label));
        for(const company of selected){
            const td=el('td'),cell=company.analysis?.dimensions?.[key];
            td.append(el('p',cell?.summary||'Смысловой анализ не выполнен.'));
            if(cell?.status==='insufficient')td.append(el('small','Недостаточно данных для вывода'));
            if(cell)aiEvidence(td,cell);
            tr.append(td);
        }
        table.append(tr);
    }
    wrap.append(table);wrap.tabIndex=0;wrap.setAttribute('aria-label','Таблица сравнения компаний');
    const tableBlock=el('section',undefined,'comparison-table-block');tableBlock.append(wrap);
    const overview=el('div',undefined,'cards');
    const ids=new Set(selected.map(c=>c.analysis?.id).filter(Boolean));
    for(const row of report.ai_analysis?.comparisons||[]){
        if(!row.evidence_ids?.every(id=>ids.has(id.split(':')[0])))continue;
        const card=el('article',undefined,'card');
        card.append(el('h3',report.dimensions[row.category]),el('p',row.summary));overview.append(card);
    }
    $('comparison').replaceChildren(
        el('h2','Сравнение компаний'),controls,add,
        el('p','В базе '+report.companies.length+' компаний. Одновременно показано '+count+'. Выберите компании в списках. Переключение использует уже собранные данные.','hint'),
        overview,tableBlock
    );
    const tg=el('div',undefined,'cards');
    for(const company of report.companies){
        const card=el('article',undefined,'card');card.append(el('h3',company.name));
        telegramCoverage(card,company);
        const cell=company.analysis?.dimensions?.editorial;
        if(cell){card.append(el('p',cell.summary));aiEvidence(card,cell);}tg.append(card);
    }
    $('telegram').replaceChildren(el('h2','Telegram: ссылки, доступ и прочитанные публикации'),tg);
}
function companyCards(){const cards=el('div',undefined,'cards');report.companies.forEach((c,i)=>{const box=el('article',undefined,'card');box.append(el('span',c.role==='own'?'Ваша компания':'Конкурент','tag'),el('h3',c.name),el('p',c.pages_ok+' страниц · '+c.posts_collected+' сообщений'),el('p',c.pages_ok?'Данные получены частично; проверьте разделы.':'Источник не получен. Оценка предложения невозможна.','hint'));const b=el('button','Открыть компанию','secondary');b.onclick=()=>companyDetails(i);box.append(b);cards.append(box);});$('companies').replaceChildren(cards);}
function companyDetails(i){const c=report.companies[i];$('dialog-title').textContent=c.name;const area=$('dialog-content');area.replaceChildren(link(c.url,c.url),el('p','Получено страниц: '+c.pages_ok+' · сообщений Telegram: '+c.posts_collected));for(const [key,label] of Object.entries(report.dimensions)){const section=el('section');section.append(el('h3',label));const cell=c.analysis?.dimensions?.[key];section.append(el('p',cell?.summary||'Смысловой анализ не выполнен.'));if(cell)aiEvidence(section,cell);area.append(section);}area.append(el('h3','Telegram'));telegramCoverage(area,c);area.append(el('h3','Пробелы'));for(const gap of c.analysis?.gaps||c.gaps)if(!gap.startsWith('Визуал:'))area.append(el('p',gap,'hint'));for(const f of c.failures)area.append(el('p',f.url+' · '+f.status+' · '+(f.next_action||'Проверьте страницу или предоставьте текст.')));$('company-dialog').showModal();}
function actions(){
 const area=$('actions');area.replaceChildren(el('h2','Итог и дальнейшие действия'));
 const assessment=report.assessment;
 if(assessment?.criteria?.length){
  area.append(el('h3',assessment.title),el('p',assessment.scope,'hint'));
  const labels={own_strength:'Ваше преимущество',parity:'На уровне конкурентов',competitor_strength:'Преимущество конкурента',different_focus:'Разный фокус'};
  const cards=el('div',undefined,'cards');
  for(const row of assessment.criteria){const card=el('article',undefined,'card');card.append(el('span',labels[row.verdict],'tag'),el('h3',report.dimensions[row.category]),el('p',row.summary));const details=el('details');details.append(el('summary','Основания'));row.evidence.forEach(ref=>evidence(details,ref));card.append(details);cards.append(card);}area.append(cards);
 }else{
  for(const row of report.ai_analysis?.comparisons||[]){const card=el('article',undefined,'card');card.append(el('h3',report.dimensions[row.category]),el('p',row.summary));area.append(card);}
 }
 if(!report.recommendations.length&&assessment?.criteria?.some(r=>r.verdict==='own_strength')&&!assessment.criteria.some(r=>r.verdict==='competitor_strength'))area.append(el('p','По сопоставленным предложениям менять свой подход вслед за конкурентами не требуется. Сохраняйте отмеченные преимущества.','notice'));
 if(report.recommendations.length)area.append(el('h3','Приоритетные действия'));
 const groups={adapt:'Адаптировать подход конкурента',keep:'Сохранить и усилить своё',check:'Проверить и при необходимости исправить',market:'Проверить возможность отстройки'};for(const [kind,label] of Object.entries(groups)){const items=report.recommendations.filter(r=>r.kind===kind);if(!items.length)continue;const section=el('section',undefined,'action-group');section.append(el('h3',label));const cards=el('div',undefined,'cards');for(const r of items){const box=el('article',undefined,'card');box.append(el('h3',r.title),el('p',r.action),el('p',r.reason||'','hint'),el('p','Проверка результата: '+r.success_check,'hint'));if(r.priority)box.append(el('p','Приоритет: '+r.priority+' · Срок: '+(r.timeframe||'уточнить'),'hint'));
if(r.deliverable)box.append(el('p','Результат работы: '+r.deliverable));
if(r.steps?.length){const steps=el('ol');r.steps.forEach(step=>steps.append(el('li',step)));box.append(steps);}
if(r.owner_role)box.append(el('p','Ответственный: '+r.owner_role,'hint'));
if(r.decision_rule)box.append(el('p','Решение после проверки: '+r.decision_rule,'hint'));
if(r.evidence.length){box.append(el('p','Основания: '+[...new Set(r.evidence.map(e=>e.company))].join(' · '),'hint'));const details=el('details');details.append(el('summary','Основания · '+r.evidence.length));r.evidence.forEach(e=>evidence(details,e));box.append(details);}else box.append(el('p','Данных для вывода пока нет; сначала собрать подтверждения.','hint'));cards.append(box);}section.append(cards);area.append(section);}}
$('start-form').onsubmit=e=>{e.preventDefault();uploads={};const url=$('website').value.trim();if($('own-text').value.trim())uploads[url]={text:$('own-text').value.trim()};state=null;command({action:'start',website_url:url,uploads},null);};
$('profile-form').onsubmit=e=>{e.preventDefault();command({action:'confirm_profile',profile:Object.fromEntries(new FormData(e.target))});};
$('competitor-form').onsubmit=e=>{e.preventDefault();const competitors=[...$('competitor-list').children].map(n=>({name:n.querySelector('[name=name]').value.trim(),url:n.querySelector('[name=url]').value.trim()}));if(!competitors.length){error('Добавьте хотя бы одного конкурента.');return;}command({action:'confirm_competitors',competitors});};
$('add-competitor').onclick=()=>row();$('edit-profile').onclick=showProfile;$('edit-competitors').onclick=showCompetitors;$('rerun').onclick=showCollect;
$('retry-search').onclick=()=>command({action:'search'});
$('import-search').onclick=()=>command({action:'import_search',search_text:$('browser-results').value});
$('add-source').onclick=()=>{try{const u=new URL($('source-url').value);if(u.protocol!=='https:'||$('source-text').value.trim().length<200)throw Error();uploads[u.href]={text:$('source-text').value.trim()};$('source-count').textContent='Добавлено источников: '+Object.keys(uploads).length;error('');}catch{error('Укажите HTTPS-адрес и текст от 200 символов.');}};
$('collect').onclick=()=>command({action:'investigate',uploads,max_pages:Number($('depth').value)});$('close-dialog').onclick=()=>$('company-dialog').close();
for(const b of document.querySelectorAll('[data-view]'))b.onclick=()=>{for(const id of ['comparison','companies','actions','telegram'])$(id).hidden=id!==b.dataset.view;for(const other of document.querySelectorAll('[data-view]'))other.classList.toggle('selected',other===b);$('results').scrollIntoView({block:'start'});};
$('new').onclick=()=>{if(busy)return;state=null;report=null;uploads={};location.hash='';$('intro').hidden=false;$('project').hidden=true;error('');};
$('open-example').onclick=openExample;
$('logout').onclick=async()=>{await fetch(appBase+'/auth/logout',{method:'POST'});location.href=appBase+'/auth/login';};
$('result-file').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>10000000)throw Error('Файл больше 10 МБ.');const value=JSON.parse(await file.text());validateImportedResult(value);error('');$('intro').hidden=true;$('project').hidden=false;$('project-name').textContent=value.profile.company_name;$('saved').textContent='Локальный файл · не загружен на сервер';location.hash='';showResult(value,true);}catch(e){error('Не удалось открыть результат: '+e.message);}finally{e.target.value='';}};
function validateImportedResult(v){
 const text=x=>typeof x==='string', array=(x,max=2000)=>Array.isArray(x)&&x.length<=max;
 if(!v||!v.profile||!text(v.profile.company_name)||!v.dimensions||typeof v.dimensions!=='object'||Array.isArray(v.dimensions)||Object.keys(v.dimensions).length>30||!Object.values(v.dimensions).every(text)||!array(v.companies,21)||!v.companies.length||!array(v.recommendations,200))throw Error('Нужен файл результата исследования в формате JSON.');
 const evidence=e=>e&&text(e.quote)&&text(e.category)&&text(e.url);
 for(const c of v.companies)if(!c||!text(c.name)||!text(c.url)||!text(c.role)||!Number.isInteger(c.pages_ok)||c.pages_ok<0||!Number.isInteger(c.posts_collected)||!array(c.evidence)||!c.evidence.every(evidence)||!array(c.channels)||!c.channels.every(x=>x&&text(x.url))||!array(c.gaps)||!c.gaps.every(text)||!array(c.failures)||!c.failures.every(x=>x&&text(x.url)&&text(x.status))||c.sections&&(!array(c.sections)||!c.sections.every(x=>x&&text(x.title)&&text(x.url))))throw Error('Некорректная структура карточек компаний.');
 for(const r of v.recommendations)if(!r||!text(r.kind)||!text(r.status)||!text(r.title)||!text(r.action)||!text(r.success_check)||!array(r.evidence)||!r.evidence.every(evidence))throw Error('Некорректная структура рекомендаций.');
}

(async()=>{if(location.hostname.endsWith('.github.io')){publishedMode();if(location.hash==='#example')await openExample();return;}try{await history();$('connection').textContent='';if(location.hash==='#example'){await openExample();return;}if(/^#[0-9a-f-]{36}$/.test(location.hash))await openProject(location.hash.slice(1));const previous=sessionStorage.getItem('neuro-job');if(previous){const job=await api('jobs/'+previous);if(job.project_id&&job.status==='succeeded')await openProject(job.project_id);else if(['queued','running'].includes(job.status)){await command(null,previous);}else if(job.status==='failed')error(job.error);}}catch(e){error('Не удалось связаться с сервером. Обновите страницу через минуту. Ваши сохранённые исследования не удалены.');if(location.hash==='#example')await openExample();}})();






