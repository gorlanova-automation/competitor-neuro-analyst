"""Copy the approved research package and create a static review UI snapshot."""
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'stage_2'

def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    copied=[]
    for path in SOURCE.rglob('*'):
        if not path.is_file(): continue
        relative=path.relative_to(SOURCE)
        if any(part.startswith('.') or part=='__pycache__' for part in relative.parts): continue
        if path.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.pem','.key'): continue
        if path.name in ('manifest.json','memory.md'): continue
        target=ROOT/'stage_2'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        if path.resolve()!=target.resolve(): shutil.copy2(path,target)
        copied.append(target)
    stage=ROOT/'stage_2'
    cards=read(stage/'research/audit.json')['experiments']
    labels={'20261022T111947Z_adab53':'baseline_v1','20261022T112126Z_2421a6':'evidence_v2','20261022T112655Z_3a2e17':'evidence_v2','20261022T112655Z_fabfd2':'evidence_v2','20261022T113037Z_be7ea6':'atomic_coverage_v3'}
    cards=[{**card,'label':labels[card['experiment']]} for card in cards]
    snapshot={'facts':read(stage/'knowledge_base/facts_draft.json')['facts'],'sources':read(stage/'knowledge_base/sources.json'),'quarantine':read(stage/'knowledge_base/quarantine.json'),'posts':read(stage/'knowledge_base/social_posts.json')['posts'],'experiments':cards,'dataset_card':read(stage/'knowledge_base/dataset_card.json'),'candidates':read(stage/'competitor_candidates.json'),'company_catalog':read(stage/'code/companies.json')}
    (ROOT/'docs/data.js').write_text('window.RESEARCH_DATA = '+json.dumps(snapshot,ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')
    # Report only paths, never a matched credential value.
    patterns=[re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}'),re.compile(r'github_pat_[A-Za-z0-9_]{20,}'),re.compile(r'\bsk-[A-Za-z0-9_-]{24,}'),re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----')]
    bad=[]
    for path in ROOT.rglob('*'):
        if not path.is_file() or '.git' in path.parts: continue
        if path.suffix.lower() not in ('.py','.json','.ipynb','.js','.md','.txt','.html','.csv','.jsonl'): continue
        text=path.read_text(encoding='utf-8-sig',errors='replace')
        if any(pattern.search(text) for pattern in patterns): bad.append(path.relative_to(ROOT).as_posix())
    if bad: raise ValueError('Potential credentials in files: '+', '.join(bad))
    manifest=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(copied)]
    (ROOT/'research_manifest.json').write_text(json.dumps({'description':'Research files: sizes and SHA256 for reproducibility','facts':len(snapshot['facts']),'files':manifest},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Prepared public project:',len(copied),'research files;',len(snapshot['facts']),'facts;',len(cards),'experiments. Credential-pattern scan passed.')

if __name__=='__main__': main()
