"""Package only useful project artifacts, with hashes; exclude local deps and caches."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def package(root):
    root=Path(root).resolve()
    output=root.parent/'Этап_2_код_и_пилот.zip'
    files=[p for p in root.rglob('*') if p.is_file() and not any(part.startswith('.') or part=='__pycache__' for part in p.relative_to(root).parts) and p.name not in ('manifest.json','course_review_source.json','inspect_course.py')]
    manifest=[{'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        for path in files+[root/'manifest.json']:
            archive.write(path,Path('stage_2')/path.relative_to(root))
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Повреждённый архив')
    print(output,output.stat().st_size,len(files))


if __name__=='__main__':
    package(Path(__file__).resolve().parents[1])
