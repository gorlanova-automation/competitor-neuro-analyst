"""Upload only this stage's outputs under the user-supplied folder."""
from pathlib import Path
import mimetypes


def sync_stage(local_root, parent_id, expected_email, folder_name):
    from google.colab import auth
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    import google.auth
    auth.authenticate_user()
    credentials, _ = google.auth.default()
    service = build('drive','v3',credentials=credentials,cache_discovery=False)
    identity = service.about().get(fields='user(emailAddress)').execute()['user']['emailAddress']
    if identity.lower() != expected_email.lower():
        raise ValueError('Выбран другой Google-аккаунт. Нужен '+expected_email)
    parent = service.files().get(fileId=parent_id,fields='id,name,mimeType,capabilities(canAddChildren)').execute()
    if parent['mimeType'] != 'application/vnd.google-apps.folder' or not parent.get('capabilities',{}).get('canAddChildren'):
        raise ValueError('Папка недоступна для добавления файлов')
    # New export folder per sync; never replace a user's existing file.
    destination = service.files().create(body={'name':folder_name,'mimeType':'application/vnd.google-apps.folder','parents':[parent_id]},fields='id,webViewLink').execute()
    directories = {Path('.'):destination['id']}
    outputs = []
    for path in sorted(Path(local_root).rglob('*')):
        relative = path.relative_to(local_root)
        if any(part.startswith('.') or part=='__pycache__' for part in relative.parts):
            continue
        if path.is_dir():
            folder = service.files().create(body={'name':path.name,'mimeType':'application/vnd.google-apps.folder','parents':[directories[relative.parent]]},fields='id').execute()
            directories[relative] = folder['id']
        elif path.is_file():
            item = service.files().create(body={'name':path.name,'parents':[directories[relative.parent]]},media_body=MediaFileUpload(str(path),mimetype=mimetypes.guess_type(path.name)[0] or 'application/octet-stream',resumable=True),fields='id,name,webViewLink,size').execute()
            verified = service.files().get(fileId=item['id'],fields='id,name,size,parents').execute()
            if int(verified.get('size',-1)) != path.stat().st_size:
                raise RuntimeError('Размер загруженного файла не совпал: '+path.name)
            outputs.append({'relative_path':str(relative),**item})
    return {'account':identity,'folder':destination,'files':outputs}
