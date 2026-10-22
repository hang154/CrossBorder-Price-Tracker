#!/usr/bin/env python3
"""Package completed blank backgrounds, exact HTML text layers and composited PNGs."""
import argparse,hashlib,html,json,shutil,sys,time,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.text_edit_agent import render,read
from app.qwen_image_api import atomic
from package_qwen_detail_images import package

def finalize(source,run,dest,refresh=False):
    if not refresh:package(source,run,dest)
    project=dest/'editable-project/project.json';doc=read(project)
    exports=render(project)
    jobs=[json.loads(s) for s in (source/'cut-jobs.jsonl').read_text().splitlines() if s.strip()]
    cards=[]
    for job,cut,receipt in zip(jobs,doc['cuts'],exports,strict=True):
        assert job['job_id']==cut['id']==receipt['cut_id']
        expected=[s.strip() for s in job['cut']['이미지 내 삽입 문구'].split('/') if s.strip()]
        assert expected==[t['text'] for t in cut['texts']]==[m['text'] for m in receipt['metrics']]
        assert not any(m['overflow'] for m in receipt['metrics'])
        rel='editable-project/'+receipt['file'];edit='editable-project/'+receipt['html']
        qa=run/job['product_id']/job['job_id']/'qa.json'
        result=json.loads(qa.read_text()) if qa.exists() else None
        repaired=(dest/'evidence/background-repairs'/job['job_id']/'job.json').exists()
        badge='배경 교체됨 · 이전 검수 기록' if repaired else ('자동 배경 검수 통과' if result and result.get('pass') else '배경 검토 필요')
        background='editable-project/'+doc['assets'][cut['background']]['path']
        cards.append('<article><h2>'+html.escape(job['product_name'])+' · '+html.escape(cut['id'])+'</h2><img loading="lazy" src="'+rel+'"><p><a download href="'+rel+'">문구 포함 PNG</a> · <a href="'+edit+'" target="_blank">편집 가능한 HTML</a> · <a href="'+background+'" target="_blank">글자 없는 배경</a></p><details><summary>'+badge+'</summary><pre>'+html.escape(json.dumps(result,ensure_ascii=False,indent=2))+'</pre></details></article>')
    (dest/'index.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>편집 가능한 상세페이지 36컷</title><style>body{margin:0;font:14px system-ui;background:#f4f3ef;color:#242721}header{padding:24px;background:white}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px;padding:24px;max-width:1600px;margin:auto}article{min-width:0;background:white;padding:16px}h2{font-size:16px}img{width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{line-height:2}</style><header><h1>편집 가능한 상품 상세페이지 · 36컷</h1><p>Qwen-Image-2.1 배경 + 원문 그대로의 HTML 문구 레이어</p><a href="manifest.json">작업·검증 기록</a></header><main>'+''.join(cards)+'</main></html>')
    # The background-only package is upgraded in place before rebuilding its ZIP.
    from bundle_detail_editor import bundle
    bundle(dest)
    repo=Path(__file__).resolve().parents[1]
    for skill in ['ecommerce-detail-page','qwen-image-api','deterministic-text-editor']:shutil.copytree(repo/'skills'/skill,dest/'skills'/skill,dirs_exist_ok=True)
    manifest=json.loads((dest/'manifest.json').read_text());manifest.update(layered=True,composited_cuts=len(exports),exports=exports,finalized_at=time.time(),current_backgrounds=[{'cut_id':c['id'],'asset':doc['assets'][c['background']]} for c in doc['cuts']])
    repairs=dest/'evidence/background-repairs/installed.json'
    if repairs.exists():manifest['background_repairs']=json.loads(repairs.read_text())
    manifest['files']=[{'path':f.relative_to(dest).as_posix(),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(dest.rglob('*')) if f.is_file() and f.name!='manifest.json' and '__pycache__' not in f.parts]
    atomic(dest/'manifest.json',manifest)
    (dest/'사용법.txt').write_text('index.html을 여세요. 문구 포함 PNG와 편집 가능한 HTML, 글자 없는 배경을 각각 제공합니다.\nHTML의 실제 텍스트와 CSS를 수정할 수 있습니다.\n좌표 편집기: 저장소에서 python -m app.text_edit_agent serve --project <이폴더>/editable-project/project.json --port 8774\n확정 문구는 원문 그대로이며 자동 배경 검수는 사람 검수를 대신하지 않습니다.\n')
    # Include final instructions in the file manifest as well.
    manifest['files']=[{'path':f.relative_to(dest).as_posix(),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(dest.rglob('*')) if f.is_file() and f.name!='manifest.json' and '__pycache__' not in f.parts];atomic(dest/'manifest.json',manifest)
    archive=dest.with_suffix('.zip');temp=archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(dest.rglob('*')):
            if f.is_file() and '__pycache__' not in f.parts:z.write(f,str(Path(dest.name)/f.relative_to(dest)))
    with zipfile.ZipFile(temp) as z:
        assert z.testzip() is None
        for entry in manifest['files']:assert hashlib.sha256(z.read(str(Path(dest.name)/entry['path']))).hexdigest()==entry['sha256']
    temp.replace(archive)
    result={'cuts':len(exports),'exact_copy':True,'text_overflow':0,'zip':str(archive),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()};atomic(run/'layered-delivery.json',result);print(json.dumps(result,ensure_ascii=False));return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--refresh',action='store_true');a=p.parse_args();finalize(a.source,a.run,a.output_dir,a.refresh)
