"""Package existing detail plans and references without calling a model or image tool."""
import argparse
import hashlib
import html
import json
import shutil
import zipfile
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_file(root, relative):
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Missing or unsafe asset: '+str(relative))
    return path


def package(source, skill, output):
    source,skill,output=map(lambda p:Path(p).resolve(),(source,skill,output))
    if output.exists():
        raise ValueError('Output must be a fresh directory')
    plans=sorted(source.glob('*/plan.json'))
    if not plans:raise ValueError('No product plans')
    output.mkdir(parents=True)
    shutil.copytree(skill,output/'skill/ecommerce-detail-page')
    esc=lambda s:html.escape(str(s),quote=True)
    cards=[];jobs=[];proof=[]
    css='body{font:16px/1.8 system-ui;background:#f5f4ef;color:#23313a;margin:0}main,header{max-width:1040px;margin:auto;padding:24px}article{background:white;margin:24px 0;padding:24px}h1{font-size:30px}h2{font-size:23px}a{color:#225d73}dl{display:grid;grid-template-columns:160px 1fr;gap:14px}dt{font-weight:bold}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f1;padding:16px}.photos{display:flex;flex-wrap:wrap;gap:20px}.photos img{width:220px;height:250px;object-fit:contain}nav{display:flex;gap:12px;flex-wrap:wrap}@media(max-width:600px){dl{display:block}dt{margin-top:18px}article{padding:18px}main,header{padding:18px}}'
    def document(title,body):
        return '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+css+'</style>'+body+'</html>'
    for p in plans:
        original=json.loads(p.read_text());v=json.loads(p.read_text());pid=p.parent.name
        if not pid.isdigit():raise ValueError('Unsafe product ID')
        dest=output/'products'/pid;dest.mkdir(parents=True)
        if len(v['cuts'])!=12:raise ValueError('Expected twelve cuts for '+pid)
        references=[]
        for asset in v['assets']:
            name=Path(asset['file']).name
            original_asset=safe_file(p.parent,'references/'+name)
            if sha(original_asset)!=asset['sha256']:raise ValueError('Asset hash mismatch')
            (dest/'references').mkdir(exist_ok=True)
            shutil.copyfile(original_asset,dest/'references'/name)
            asset['path']='references/'+name
            references.append('products/'+pid+'/references/'+name)
        v['status']='handoff_only_no_images_generated'
        (dest/'plan.json').write_text(json.dumps(v,ensure_ascii=False,indent=2))
        assert v['cuts']==original['cuts'],'Do not edit copy when packaging'
        proof.append({'product_id':pid,'source_plan_sha256':sha(p),'cut_content_sha256':hashlib.sha256(json.dumps(v['cuts'],sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'copy_changed':False,'cuts':len(v['cuts'])})
        photohtml='<div class="photos">'+''.join('<a href="references/'+esc(a['file'])+'"><img src="references/'+esc(a['file'])+'" alt="'+esc(a['file'])+'"></a>' for a in v['assets'])+'</div>'
        body='<header><a href="../../index.html">전체 목록</a><h1>'+esc(v['product']['name'])+'</h1><p>'+esc(v['product']['style'])+' · 12컷 기획 · 이미지 생성 전</p></header><main><h2>상품 맥락·전략</h2><p>'+esc(v['strategy'])+'</p><h2>참조 사진</h2>'+photohtml+'<ul>'+''.join('<li>'+esc(x)+'</li>' for x in v['photo_analysis'])+'</ul><nav>'+''.join('<a href="#cut-'+str(i)+'">'+str(i)+'컷</a>' for i in range(1,13))+'</nav>'
        for i,cut in enumerate(v['cuts'],1):
            job={'job_id':pid+'-cut-'+str(i).zfill(2),'product_id':pid,'product_name':v['product']['name'],'style':v['product']['style'],'output_filename':'generated/'+pid+'/cut-'+str(i).zfill(2)+'.png','reference_files':references,'cut':cut,'generation_executed':False}
            jobs.append(job)
            (dest/'cuts').mkdir(exist_ok=True)
            (dest/'cuts'/('cut-'+str(i).zfill(2)+'.json')).write_text(json.dumps(job,ensure_ascii=False,indent=2))
            fields=''.join('<dt>'+esc(k)+'</dt><dd>'+('<pre>'+esc(val)+'</pre>' if k=='ASCII 레이아웃' else esc(val))+'</dd>' for k,val in cut.items())
            body+='<article id="cut-'+str(i)+'"><h2>'+str(i)+'. '+esc(cut['헤드라인'])+'</h2><dl>'+fields+'</dl><a download href="cuts/cut-'+str(i).zfill(2)+'.json">이 컷 제작 지시 JSON</a></article>'
        body+='<h2>디자인 톤앤매너</h2><p>'+esc(v['tone'])+'</p><h2>기획 QA</h2><ul>'+''.join('<li>'+esc(x)+'</li>' for x in v['compliance'])+'</ul><a download href="plan.json">전체 기획 JSON</a></main>'
        (dest/'index.html').write_text(document(v['product']['name'],body))
        cards.append('<article><h2>'+esc(v['product']['name'])+'</h2><p>'+esc(v['product']['style'])+' · 12컷</p><a href="products/'+pid+'/index.html">기획·사진·컷별 제작 지시 열기</a></article>')
    (output/'cut-jobs.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in jobs))
    (output/'제작_인계서.txt').write_text('''상세페이지 제작 인계 자료

현재 포함: 상품 3종 × 12컷 기획, 참조 사진, 컷별 JSON, 정리된 제작 스킬.
현재 수행: 기획 자료 패키징. 이미지 생성은 실행하지 않았습니다.

1. 압축을 풀고 index.html을 열어 상품별 기획을 확인하세요.
2. 제작 에이전트에는 skill/ecommerce-detail-page/SKILL.md와 대상 상품의 plan.json, references 폴더를 함께 전달하세요.
3. cut-jobs.jsonl은 전체 컷의 작업 목록입니다. 각 JSON에 카피·구도·스타일·참조 사진·출력 파일명이 들어 있습니다. 경로는 이 폴더 기준입니다.
4. 이미지 제작을 의뢰할 때는 각 컷의 '이미지 내 삽입 문구'를 그대로 사용하고 사진의 상품 형태·배색·문양을 기준으로 제작하도록 지시하세요. 카피를 임의로 덧붙이거나 순화하지 마세요.
5. 최종 이미지에서는 이미지 모델이 비주얼과 한글을 함께 생성합니다. 텍스트 오류·상품 불일치는 해당 이미지 재생성으로 처리합니다.
6. 인계 자료의 내부 QA 정보와 확인 필요 항목은 판매 이미지 카피에 추가하지 마세요. 현재 컷 카피는 로컬 Qwen 기획과 원본 스킬 QA 결과를 유지했습니다.
7. 생성 후 스킬의 scripts/build-image-gallery.mjs로 순서별 HTML과 다운로드 페이지를 만들 수 있습니다.

이 파일이나 HTML을 여는 동작으로 모델/API가 실행되지 않습니다.
''')
    (output/'index.html').write_text(document('상세페이지 3종 제작 인계','<header><h1>상세페이지 3종 · 36컷 제작 인계</h1><p>기획·참조 사진·스킬·컷별 제작 지시를 포함합니다. 생성 이미지는 포함하지 않습니다.</p><a href="제작_인계서.txt">제작 인계서</a> · <a download href="cut-jobs.jsonl">전체 작업 JSONL</a></header><main>'+''.join(cards)+'</main>'))
    (output/'copy-verification.json').write_text(json.dumps({'manual_copy_changes':0,'products':proof,'generation_executed':False},ensure_ascii=False,indent=2))
    files=[{'file':str(f.relative_to(output)),'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(output.rglob('*')) if f.is_file()]
    manifest={'products':len(plans),'cuts':len(jobs),'reference_images':sum(len(list((output/'products'/p.parent.name/'references').glob('*'))) for p in plans),'generation_executed':False,'files':files}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    archive=output.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(output.rglob('*')):
            if f.is_file():z.write(f,str(f.relative_to(output.parent)))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for f in files:
            assert hashlib.sha256(z.read(output.name+'/'+f['file'])).hexdigest()==f['sha256']
    return {'zip':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive),'products':len(plans),'cuts':len(jobs),'reference_images':manifest['reference_images'],'file_count':len(files)+1}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--skill',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(package(args.source,args.skill,args.output),ensure_ascii=False))
