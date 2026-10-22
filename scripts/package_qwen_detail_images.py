#!/usr/bin/env python3
"""Verify image receipts, make portable gallery and archive without credentials."""
import argparse,hashlib,html,json,shutil,sys,time,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.qwen_image_api import atomic
from PIL import Image

def package(source,run,dest,expected=36):
    jobs=[json.loads(s) for s in (source/'cut-jobs.jsonl').read_text().splitlines() if s.strip()]
    if len(jobs)!=expected:raise ValueError('Unexpected source count')
    if dest.exists():raise FileExistsError(dest)
    dest.mkdir(parents=True);rows=[];cards=[];products={};qa_pass=0
    for job in jobs:
        folder=run/job['product_id']/job['job_id'];receipt=json.loads((folder/'job.json').read_text());im=folder/'image.png';qa=json.loads((folder/'qa.json').read_text()) if (folder/'qa.json').exists() else None
        digest=hashlib.sha256(im.read_bytes()).hexdigest()
        if receipt.get('state')!='SUCCEEDED' or receipt.get('output_sha256')!=digest:raise ValueError('Missing/mismatched receipt: '+job['job_id'])
        with Image.open(im) as picture:
            dims=list(picture.size);picture.verify()
        if dims!=[1536,2304]:raise ValueError('Unexpected image dimensions')
        if json.loads((folder/'cut.json').read_text())['cut']!=job['cut']:raise ValueError('Approved plan was changed')
        rel=Path('images')/job['product_id']/(job['job_id']+'.png');target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(im,target)
        evidence=dest/'evidence'/job['job_id'];evidence.mkdir(parents=True)
        for name in ['job.json','cut.json','qa.json','layout.json','generation-plan.json']:
            if (folder/name).exists():shutil.copyfile(folder/name,evidence/name)
        if (folder/'qa-evidence').exists():shutil.copytree(folder/'qa-evidence',evidence/'qa-evidence')
        mode='blank-background-v1' if (folder/'layout.json').exists() else 'legacy-rendered-text'
        good=bool(qa and qa['pass']);qa_pass+=good
        rows.append({'cut':job['job_id'],'product_id':job['product_id'],'file':rel.as_posix(),'sha256':digest,'dimensions':dims,'api_job_id':receipt['id'],'qa_pass':good,'mode':mode,'approved_copy':job['cut']['이미지 내 삽입 문구']})
        card=f'''<article data-product="{html.escape(job['product_id'])}"><p>{'글자 없는 배경 · HTML 문구 조판 전' if mode=='blank-background-v1' else '문구 포함 이미지'}</p><h2>{html.escape(job['product_name'])} · {job['job_id'].split('-')[-1]}</h2><a href="{rel.as_posix()}" target="_blank"><img loading="lazy" src="{rel.as_posix()}" alt="{html.escape(job['job_id'])}"></a><p><a download href="{rel.as_posix()}">PNG 다운로드</a> · <a href="evidence/{job['job_id']}/job.json">API 기록</a></p><details><summary>확정 문구·검수</summary><p>{html.escape(job['cut']['이미지 내 삽입 문구'])}</p><pre>{html.escape(json.dumps(qa,ensure_ascii=False,indent=2))}</pre></details></article>'''
        cards.append(card);products[job['product_id']]=job['product_name']
    options=''.join(f'<option value="{pid}">{html.escape(name)}</option>' for pid,name in products.items())
    page='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>상세페이지 36컷</title><style>body{font-family:system-ui,sans-serif;margin:0;background:#f5f3ef;color:#25251f}header{padding:24px;position:sticky;top:0;background:#fffef8ed;z-index:2;border-bottom:1px solid #ddd}h1{font-size:24px;margin:0 0 12px}select,a{padding:6px}main{max-width:1600px;margin:20px auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:20px;padding:12px}article{background:white;padding:14px;border-radius:12px;min-width:0}h2{font-size:17px}img{width:100%;height:auto;border:1px solid #eee}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}p{line-height:1.65}article[hidden]{display:none}</style><header><h1>상품 상세페이지 · 3종 36컷</h1><p>Qwen-Image-2.1 · 1536 × 2304 · 50 steps · 실제 상품 참조 편집</p><label>상품 <select id="filter"><option value="">전체 36컷</option>'''+options+'''</select></label><a href="manifest.json">검증 manifest</a></header><main>'''+''.join(cards)+'''</main><script>document.getElementById('filter').addEventListener('change',e=>document.querySelectorAll('article').forEach(a=>a.hidden=!!e.target.value&&a.dataset.product!==e.target.value));</script></html>'''
    (dest/'index.html').write_text(page)
    shutil.copyfile(source/'cut-jobs.jsonl',dest/'cut-jobs.jsonl')
    repo=Path(__file__).resolve().parents[1]
    for skill in ['ecommerce-detail-page','qwen-image-api','deterministic-text-editor']:shutil.copytree(repo/'skills'/skill,dest/'skills'/skill)
    for name in ['qwen_image_client.py']: (dest/'client/scripts').mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/'scripts'/name,dest/'client/scripts'/name)
    (dest/'client/app').mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/'app/qwen_image_api.py',dest/'client/app/qwen_image_api.py');(dest/'client/app/__init__.py').write_text('')
    shutil.copyfile(repo/'docs/QWEN_IMAGE_API.md',dest/'QWEN_IMAGE_API.md')
    (dest/'사용법.txt').write_text('index.html을 브라우저로 여세요. images에 상품별 12컷이 있습니다.\n확정 기획은 cut-jobs.jsonl, API 작업 ID·입력·PNG SHA는 evidence에 있습니다.\n로컬 Qwen 시각 검수는 자동 평가이며 qa.json과 원응답을 함께 제공합니다.\n재생성 시 기존 카피를 임의 수정하지 마세요.\nAPI 클라이언트: pip install httpx Pillow 이후 client/scripts/qwen_image_client.py 실행. 기존 키는 환경변수나 --key-file로 공급합니다. 키는 포함하지 않았습니다.\n')
    if any(r['mode']=='blank-background-v1' for r in rows):
        from app.text_edit_agent import init
        init(source,run,dest/'editable-project')
        shutil.copyfile(repo/'docs/LOCAL_DETAIL_STUDIO.md',dest/'LOCAL_DETAIL_STUDIO.md')
    manifest={'created_at':time.time(),'count':len(rows),'api_model':'Qwen/Qwen-Image-2.1','endpoint':'https://hang010412.tail144a38.ts.net/qwen-image-api/v1','automatic_qa_passed':qa_pass,'approved_copy_modified':False,'images':rows,'files':[]}
    for f in sorted(dest.rglob('*')):
        if f.is_file() and '__pycache__' not in f.parts:manifest['files'].append({'path':f.relative_to(dest).as_posix(),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size})
    atomic(dest/'manifest.json',manifest)
    z=dest.with_suffix('.zip')
    if z.exists():raise FileExistsError(z)
    with zipfile.ZipFile(z,'x',zipfile.ZIP_DEFLATED) as archive:
        for f in dest.rglob('*'):
            if f.is_file() and '__pycache__' not in f.parts:archive.write(f,str(Path(dest.name)/f.relative_to(dest)))
    with zipfile.ZipFile(z) as archive:
        if archive.testzip():raise ValueError('ZIP integrity failed')
        for f in manifest['files']:
            if hashlib.sha256(archive.read(str(Path(dest.name)/f['path']))).hexdigest()!=f['sha256']:raise ValueError('ZIP SHA mismatch')
    print(json.dumps({'images':len(rows),'qa_passed':qa_pass,'zip':str(z),'bytes':z.stat().st_size,'sha256':hashlib.sha256(z.read_bytes()).hexdigest()},ensure_ascii=False));return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path);p.add_argument('--run',required=True,type=Path);p.add_argument('--output-dir',required=True,type=Path);a=p.parse_args();package(a.source,a.run,a.output_dir)
