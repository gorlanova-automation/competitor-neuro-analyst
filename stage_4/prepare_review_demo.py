"""Prepare a reviewable real model draft, without new network/model calls."""
import json
import shutil
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
from stage_4.workflow import save,render_report,timestamp
from stage_4.review import audit_semantics


def prepare(case_dir='stage_4/results/live_colab_20261107',storage_dir='var/projects',public_file='docs/demo-report.json'):
    source=Path(case_dir);original=json.loads((source/'state.json').read_text(encoding='utf-8'))
    identifier=str(uuid5(NAMESPACE_URL,'competitor-neuro-analyst/review-demo/'+original['id']))
    run_id=str(uuid5(NAMESPACE_URL,'competitor-neuro-analyst/audit/'+original['report']['run_id']))
    target=Path(storage_dir)/identifier;created=not target.exists()
    if created:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,target)
    run_folder=target/'runs'/run_id
    if not run_folder.exists():
        previous=source/'runs'/original['report']['run_id']
        result=json.loads((previous/'result.json').read_text(encoding='utf-8'))
        result['semantic']['audit']=audit_semantics(result['semantic'])
        result['semantic']['source_model_run_id']=result['run_id']
        result.update(run_id=run_id,new_llm_calls=0,new_api_cost=0,generated_at=timestamp(),
            analysis_method='Сохранённый модельный черновик и офлайн-проверка чисел/покрытия. Проверка смысла ещё не выполнена.',
            demo_provenance='Реальный корпус и модельный ответ. Подготовлено помощником для проверки интерфейса; не приёмка Еленой.')
        run_folder.mkdir(parents=True)
        save(run_folder/'result.json',result)
        shutil.copyfile(previous/'sources.json',run_folder/'sources.json')
        (run_folder/'report.html').write_bytes(render_report(result).encode('utf-8'))
    if created:
        original.update(id=identifier,origin={'case_id':original['id'],'method':'copied_for_review_demonstration'},status='report_ready')
        original['report'].update(run_id=run_id,new_llm_calls=0,semantic_status='model_draft_pending_semantic_review')
        save(target/'state.json',original)
    Path(public_file).write_bytes((run_folder/'result.json').read_bytes())
    print(json.dumps({'project_id':identifier,'run_id':run_id,'url':'http://127.0.0.1:18105/stand/review.html?project='+identifier+'&run='+run_id},ensure_ascii=False))
    return identifier,run_id


if __name__=='__main__':prepare()
