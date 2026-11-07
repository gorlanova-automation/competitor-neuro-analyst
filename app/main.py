import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4
from threading import RLock

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'stage_3' / 'code'))
import analyst
from stage_4.workflow import run_project, WorkflowError


class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    country: Literal['Portugal', 'Spain'] = 'Portugal'
    competitors: list[str] | None = Field(default=None, max_length=100)


class ProjectRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action: Literal['start','confirm_profile','search','confirm_competitors','collect']='start'
    website_url: str=Field(default='',max_length=2000)
    profile: dict[str,str] | None=None
    competitor_urls: list[str] | None=Field(default=None,max_length=10)
    uploads: dict[str,dict[str,str]] | None=None
    max_pages: int=Field(default=4,ge=1,le=8)


def now():
    return datetime.now(timezone.utc).isoformat()


def create_app(data_dir=None, stage_root=None):
    storage = Path(data_dir) if data_dir else PROJECT / 'var'
    stage = Path(stage_root) if stage_root else PROJECT / 'stage_3'
    storage.mkdir(parents=True, exist_ok=True)
    db = storage / 'history.sqlite3'
    project_lock=RLock()
    @contextmanager
    def connect():
        conn = sqlite3.connect(db, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()
    with connect() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at TEXT, completed_at TEXT, status TEXT, config TEXT, summary TEXT, error TEXT)')

    api = FastAPI(title='Нейро-аналитик конкурентов — локальный API', version='1.0')
    api.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', 'testserver'])

    @api.middleware('http')
    async def same_origin(request: Request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and origin != str(request.base_url).rstrip('/'):
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Cross-origin writes are disabled'}, status_code=403)
        return await call_next(request)

    def lookup(run_id):
        with connect() as conn:
            row = conn.execute('SELECT * FROM runs WHERE id=?', (str(run_id),)).fetchone()
        if row is None:
            raise HTTPException(404, 'Run not found')
        item = dict(row)
        for key in ('config', 'summary'):
            item[key] = json.loads(item[key]) if item[key] else None
        return item

    @api.get('/health')
    def health():
        return {'status': 'ok', 'mode': 'local_application', 'live_llm_enabled': False,'workflow_available':True}

    def project_action(body,project_id=None):
        try:
            with project_lock:
                return run_project(**body.model_dump(),output_dir=storage/'projects',project_id=project_id)
        except WorkflowError as error:
            raise HTTPException(422,str(error)) from None
        except Exception:
            raise HTTPException(500,'Операция не завершена. Предыдущие результаты сохранены; проверьте данные и подключение.') from None

    @api.post('/projects',status_code=201)
    def start_project(body:ProjectRequest):
        if body.action!='start':raise HTTPException(422,'Новый проект начинается с действия start.')
        return project_action(body)

    @api.get('/projects')
    def project_history():
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((storage/'projects').glob('*/state.json'),reverse=True)]

    @api.get('/projects/{project_id}')
    def project_detail(project_id:UUID):
        try:return run_project(project_id=str(project_id),output_dir=storage/'projects',action='read')
        except WorkflowError as error:raise HTTPException(404,str(error)) from None

    @api.post('/projects/{project_id}')
    def advance_project(project_id:UUID,body:ProjectRequest):
        if body.action=='start':raise HTTPException(422,'Создайте новый проект через /projects.')
        return project_action(body,str(project_id))

    @api.get('/projects/{project_id}/reports/{report_id}')
    def project_report(project_id:UUID,report_id:UUID,format:Literal['html','json']='html'):
        path=storage/'projects'/str(project_id)/'runs'/str(report_id)/('report.html' if format=='html' else 'result.json')
        if not path.is_file():raise HTTPException(404,'Отчёт не найден.')
        return FileResponse(path,filename=path.name,content_disposition_type='inline' if format=='html' else 'attachment')

    @api.get('/companies')
    def companies():
        return analyst.read(stage / 'input/companies.json')

    @api.get('/runs')
    def history(limit: int = Query(20, ge=1, le=100)):
        with connect() as conn:
            ids = conn.execute('SELECT id FROM runs ORDER BY created_at DESC, id DESC LIMIT ?', (limit,)).fetchall()
        return [lookup(row['id']) for row in ids]

    @api.get('/runs/{run_id}')
    def detail(run_id: UUID):
        return lookup(run_id)

    @api.post('/runs', status_code=201)
    def execute(body: RunRequest):
        config = analyst.read(stage / 'config.json')
        if body.competitors is not None:
            allowed = set(config['competitors'])
            if len(set(body.competitors)) != len(body.competitors) or not set(body.competitors) <= allowed:
                raise HTTPException(422, 'Competitors must be unique IDs from /companies')
            config['competitors'] = body.competitors
        config.update(country=body.country, live_llm_enabled=False)
        run_id = str(uuid4())
        with connect() as conn:
            conn.execute('INSERT INTO runs VALUES (?, ?, NULL, ?, ?, NULL, NULL)',
                         (run_id, now(), 'running', json.dumps(config, ensure_ascii=False)))
        try:
            result = analyst.run(stage, config, storage / 'runs' / run_id)
            summary = {key: len(result[field]) for key, field in
                       [('criteria', 'criteria'), ('evidence', 'evidence'), ('hypotheses', 'recommendations')]}
            summary.update(new_llm_calls=0, new_api_cost=0,
                           input_manifest_sha256=analyst.digest(stage / 'input/manifest.json'))
        except Exception:
            # Do not expose exception text, local paths or possible credentials.
            with connect() as conn:
                conn.execute('UPDATE runs SET status=?, completed_at=?, error=? WHERE id=?',
                             ('failed', now(), 'analysis_failed_check_inputs', run_id))
            raise HTTPException(500, {'run_id': run_id, 'error': 'analysis_failed_check_inputs'}) from None
        with connect() as conn:
            conn.execute('UPDATE runs SET status=?, completed_at=?, summary=? WHERE id=?',
                         ('succeeded', now(), json.dumps(summary), run_id))
        return lookup(run_id)

    @api.get('/runs/{run_id}/report')
    def report(run_id: UUID, format: Literal['html', 'json', 'csv', 'md'] = 'html'):
        row = lookup(run_id)
        if row['status'] != 'succeeded':
            raise HTTPException(409, 'Run has no completed report')
        filename = {'html': 'report.html', 'json': 'result.json', 'csv': 'comparison.csv', 'md': 'report.md'}[format]
        path = storage / 'runs' / str(run_id) / filename
        if not path.is_file():
            raise HTTPException(404, 'Report file not found')
        return FileResponse(path, filename=filename)

    @api.get('/', include_in_schema=False)
    def home():
        return RedirectResponse('/stand/workspace.html')

    if (PROJECT/'docs').is_dir():
        api.mount('/stand', StaticFiles(directory=PROJECT/'docs', html=True), name='stand')
    return api
