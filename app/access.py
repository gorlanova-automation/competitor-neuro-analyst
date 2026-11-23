"""Password gate for the owner's workspace, not a multi-user identity service."""
import hashlib
import hmac
import json
import secrets
import time
from threading import Lock
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse

COOKIE='neuro_workspace'
attempts={}
lock=Lock()

def signature(value,password):
    return hmac.new(password.encode(),value.encode(),hashlib.sha256).hexdigest()

def valid_cookie(request,password):
    try:
        stamp,mac=request.cookies.get(COOKIE,'').split('.',1)
        return 0<=time.time()-int(stamp)<43200 and secrets.compare_digest(mac,signature(stamp,password))
    except (ValueError,TypeError):return False

async def login(request,password):
    prefix=request.scope.get('root_path','')
    if request.method=='GET':
        return HTMLResponse('''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Вход — Нейроаналитик</title><link rel="stylesheet" href="'''+prefix+'''/stand/product.css"><main style="max-width:440px;padding-top:12vh"><h1>Нейроаналитик</h1><p>Рабочее пространство исследований</p><form id="login"><label>Пароль доступа<input id="password" type="password" autocomplete="current-password" required></label><button>Войти</button><p id="message" role="alert"></p></form><script>document.getElementById('login').onsubmit=async e=>{e.preventDefault();let r=await fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('password').value})});if(r.ok)location.href='''+json.dumps(prefix+'/stand/product.html')+''';else document.getElementById('message').textContent=r.status===429?'Слишком много попыток. Подождите 15 минут.':'Неверный пароль';};</script></main></html>''',headers={'Cache-Control':'no-store'})
    origin=request.headers.get('origin')
    if origin and origin!=str(request.url).split('/auth/')[0].removesuffix(prefix):
        return JSONResponse({'detail':'Недопустимый источник запроса.'},status_code=403)
    address=request.client.host if request.client else 'unknown'
    with lock:
        now=time.time()
        for key in list(attempts):
            attempts[key]=[t for t in attempts[key] if now-t<900]
            if not attempts[key]:del attempts[key]
        if len(attempts.get(address,[]))>=10:return JSONResponse({'detail':'Повторите позже.'},status_code=429)
        attempts.setdefault(address,[]).append(now)
    try:
        if int(request.headers.get('content-length','0'))>4096:raise ValueError()
        value=await request.json()
        supplied=value.get('password','')
        accepted=isinstance(supplied,str) and len(supplied)<=500 and secrets.compare_digest(supplied.encode(),password.encode())
    except Exception:accepted=False
    if not accepted:return JSONResponse({'detail':'Неверный пароль.'},status_code=401)
    with lock:attempts.pop(address,None)
    stamp=str(int(time.time()))
    response=JSONResponse({'status':'ok'})
    response.set_cookie(COOKIE,stamp+'.'+signature(stamp,password),max_age=43200,httponly=True,secure=request.url.scheme=='https',samesite='strict',path=prefix or '/')
    response.headers['Cache-Control']='no-store'
    return response
