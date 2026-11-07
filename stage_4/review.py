"""Apply human decisions to one exact report; never rewrite model originals."""
import copy
import re
from decimal import Decimal
from stage_4.workflow import WorkflowError,timestamp,digest


def numeric_tokens(text):
    return {format(Decimal(re.sub(r'\s','',value).replace(',','.')).normalize(),'f') for value in re.findall(r'(?<!\w)\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?',text)}


def audit_semantics(semantic):
    flags=[]
    for index,finding in enumerate(semantic['findings']):
        unsupported=sorted(numeric_tokens(finding['summary'])-numeric_tokens(finding['quote']))
        if unsupported:flags.append({'finding_index':index,'kind':'numbers_not_supported_by_quote','values':unsupported})
    counts={s['company_url']:0 for s in semantic['sources']}
    by_id={s['source_id']:s for s in semantic['sources']}
    for finding in semantic['findings']:counts[by_id[finding['source_id']]['company_url']]+=1
    return {'finding_flags':flags,'companies_without_findings':[url for url,count in counts.items() if not count],
            'prompt_count_limit_exceeded':len(semantic['findings'])>8,
            'limit':'Проверка чисел выявляет отдельные ошибки, но не доказывает смысловую полноту цитаты.'}


def apply_review(result,review,report_sha256,companies):
    if not result.get('semantic'):raise WorkflowError('В отчёте нет модельного черновика.')
    if not isinstance(review,dict) or review.get('source_run_id')!=result['run_id'] or review.get('report_sha256')!=report_sha256:
        raise WorkflowError('Проверка относится к другой версии отчёта. Откройте исходный JSON заново.')
    reviewer=review.get('reviewer','').strip()
    if not reviewer or len(reviewer)>200:raise WorkflowError('Укажите автора проверки.')
    semantic=result['semantic'];decisions=review.get('findings');hypotheses=review.get('hypotheses')
    if not isinstance(decisions,dict) or set(decisions)!={str(i) for i in range(len(semantic['findings']))}:
        raise WorkflowError('Проверьте каждый вывод модели.')
    if not isinstance(hypotheses,dict) or set(hypotheses)!={str(i) for i in range(len(semantic['hypotheses']))}:
        raise WorkflowError('Проверьте каждую гипотезу модели.')
    originals={}
    for company in companies:
        for source in company['sources']:
            if source['status']=='ok':
                if digest(source['text'])!=source['sha256_text']:raise WorkflowError('Исходный текст изменён.')
                originals[source['sha256_text']]=source['text']
    by_id={s['source_id']:s for s in semantic['sources']}
    updated=copy.deepcopy(result);value=updated['semantic'];accepted=set()
    for index,finding in enumerate(value['findings']):
        decision=decisions[str(index)]
        if not isinstance(decision,dict) or decision.get('decision') not in ('accept','reject','revise'):
            raise WorkflowError('Выберите: принять, отклонить или исправить.')
        finding['review_status']=decision['decision']
        if decision['decision']=='reject':continue
        if decision['decision']=='revise':
            summary=decision.get('summary','').strip();quote=decision.get('quote',finding['quote']).strip()
            if not summary or len(summary)>1200:raise WorkflowError('Введите исправленный вывод.')
            finding['original_model_summary']=finding['summary'];finding['summary']=summary
            finding['original_model_quote']=finding['quote'];finding['quote']=quote
        source=by_id[finding['source_id']]
        if len(finding['quote'])<15 or finding['quote'] not in originals.get(source['sha256_text'],''):
            raise WorkflowError('Исправленная цитата отсутствует в сохранённом тексте.')
        if numeric_tokens(finding['summary'])-numeric_tokens(finding['quote']):
            raise WorkflowError('В выводе F'+str(index)+' есть числа без основания в цитате. Исправьте вывод или цитату.')
        accepted.add(index)
    for index,hypothesis in enumerate(value['hypotheses']):
        decision=hypotheses[str(index)]
        if not isinstance(decision,dict) or decision.get('decision') not in ('accept','reject','revise'):
            raise WorkflowError('Укажите решение по каждой гипотезе.')
        hypothesis['review_status']=decision['decision']
        if decision['decision']=='reject':continue
        if decision['decision']=='revise':
            action=decision.get('action','').strip();indexes=decision.get('evidence_indexes')
            if not action or len(action)>1500:raise WorkflowError('Введите исправленную гипотезу.')
            hypothesis.update(original_model_action=hypothesis['action'],action=action,evidence_indexes=indexes)
        indexes=hypothesis['evidence_indexes']
        if not isinstance(indexes,list) or not indexes or any(type(i) is not int or i not in accepted for i in indexes):
            raise WorkflowError('Гипотеза ссылается на отклонённый или неизвестный вывод.')
    value.update(status='human_review_recorded',reviewer=reviewer,reviewed_at=timestamp(),
                 accepted_findings=len(accepted),accepted_hypotheses=sum(h['review_status']!='reject' for h in value['hypotheses']))
    updated['review_provenance']={'source_run_id':result['run_id'],'source_report_sha256':report_sha256,
                                'reviewer':reviewer,'new_llm_calls':0}
    return updated
