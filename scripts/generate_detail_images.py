#!/usr/bin/env python3
"""Resume-safe Qwen-Image detail cut production from portable cut-jobs.jsonl."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.qwen_image_api import ImageAPI,atomic

def legacy_prompt(job,directions):
    if job['job_id']=='8413135628-cut-01':
        return '高端韩国电商竖版详情页海报，纯白色背景，参考图中的金色陶瓷小猪储蓄罐放在画面中央，保持产品外观。精美简洁的排版，顶部只写第一行韩文，底部只写第二行和第三行韩文，文字清晰准确，不要其他任何文字。第一行：재물운을 부르는 황금 돼지。第二行：특대형 도자기 저금통。第三行：집안 곳곳에 복을 모으세요。'
    phrases=[t.strip() for t in job['cut']['이미지 내 삽입 문구'].split('/')]
    return '高端韩国电商竖版详情页海报。'+directions[job['job_id']]+'。保持参考图片的产品外观，不复制参考图中的广告文字。画面中只能出现以下韩文，逐字准确排版，不添加或修改，不出现其他文字：'+ '；'.join('第'+str(i+1)+'行：'+text for i,text in enumerate(phrases))+'。'

def prompt(job,directions,layout=None):
    from app.detail_layout import plan_layout,background_prompt
    return background_prompt(job,directions,layout or plan_layout(job))

def references(job,root,out):
    # Product-only crops keep merchant banners from competing with approved copy.
    from PIL import Image
    pid=job['product_id'];source=root/'products'/pid/'references';dest=out/'prepared-references'/pid;dest.mkdir(parents=True,exist_ok=True)
    if pid=='8413135628':return [source/'007.jpg']
    if pid=='9174439527':
        target=dest/'product.jpg'
        if not target.exists():
            with Image.open(source/'006.jpg') as im:im.crop((0,1400,780,2099)).save(target,quality=95)
        return [source/'013.jpg'] if any(x in job['cut']['이미지 구성'] for x in ['013.jpg','착용']) else [target]
    if pid=='9747637805':
        target=dest/'card-frame.png';pouch=dest/'pouch.png'
        if not target.exists():
            with Image.open(source/'009.png') as im:
                im.crop((29,161,235,374)).save(target)
                im.crop((267,151,489,320)).save(pouch)
        prepared=[]
        for ref in [target,pouch]:
            safe=ref.with_stem(ref.stem+'-512')
            if not safe.exists():
                with Image.open(ref) as im:
                    scale=max(512/im.width,512/im.height)
                    dims=tuple(((round(n*scale)+31)//32)*32 for n in im.size)
                    im.resize(dims,Image.Resampling.LANCZOS).save(safe)
            prepared.append(safe)
        return prepared
    return [root/f for f in job['reference_files']]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path);p.add_argument('--output-dir',required=True,type=Path)
    p.add_argument('--max',type=int,default=36);p.add_argument('--inflight',type=int,default=2)
    p.add_argument('--poll-seconds',type=float,default=8);p.add_argument('--size',default='1536x2304')
    p.add_argument('--plan-only',action='store_true',help='Write blank layout contracts and prompts without API calls')
    p.add_argument('--legacy-rendered-text',action='store_true',help='Explicit old-mode resume only; copy is drawn into pixels')
    p.add_argument('--layouts',type=Path,help='Optional JSON mapping job IDs to exact layout contracts')
    p.add_argument('--steps',type=int,default=50);p.add_argument('--key-file');args=p.parse_args()
    from app.qwen_image_api import headers
    from app.detail_layout import plan_layout
    root=args.source.resolve();out=args.output_dir.resolve()
    jobs=[json.loads(s) for s in (root/'cut-jobs.jsonl').read_text().splitlines() if s.strip()][:args.max]
    pending=list(jobs);active=[];done=[];failed=[];start=time.time()
    out.mkdir(parents=True,exist_ok=True)
    directions=json.loads((out/'visual-directions.json').read_text())
    width,height=map(int,args.size.split('x'));overrides=json.loads(args.layouts.read_text()) if args.layouts else {}
    layouts={j['job_id']:plan_layout(j,width,height,overrides.get(j['job_id'])) for j in jobs}
    # Preflight every job before the first POST; never mix old jobs and blank-mode contracts.
    for j in jobs:
        folder=out/j['product_id']/j['job_id'];lp=folder/'layout.json'
        if not args.legacy_rendered_text:
            if (folder/'job.json').exists() and not lp.exists():raise ValueError('Existing legacy run: use a new output directory or explicit --legacy-rendered-text')
            if (folder/'job.json').exists() and lp.exists() and json.loads(lp.read_text())!=layouts[j['job_id']]:raise ValueError('Frozen layout changed: use a new output directory')
            atomic(lp,layouts[j['job_id']])
        atomic(folder/'generation-plan.json',{'mode':'legacy-rendered-text' if args.legacy_rendered_text else 'blank-background-v1','prompt':legacy_prompt(j,directions) if args.legacy_rendered_text else prompt(j,directions,layouts[j['job_id']]),'size':args.size,'steps':args.steps})
    if args.plan_only:
        print(json.dumps({'planned':len(jobs),'mode':'legacy-rendered-text' if args.legacy_rendered_text else 'blank-background-v1','api_called':False}));return 0
    api=ImageAPI(auth=headers(args.key_file))
    while pending or active:
        while pending and len(active)<args.inflight:
            job=pending.pop(0);folder=out/job['product_id']/job['job_id'];journal=folder/'job.json';output=folder/'image.png'
            atomic(folder/'cut.json',job)
            try:
                saved=api.submit(legacy_prompt(job,directions) if args.legacy_rendered_text else prompt(job,directions,layouts[job['job_id']]),journal,images=references(job,root,out),size=args.size,steps=args.steps,seed=14200+jobs.index(job))
                active.append((job,journal,output))
                print(json.dumps({'event':'submitted_or_resumed','cut':job['job_id'],'id':saved['id']},ensure_ascii=False),flush=True)
            except Exception as exc:
                failed.append({'cut':job['job_id'],'error':str(exc)});print(json.dumps({'event':'submission_stopped',**failed[-1]},ensure_ascii=False),flush=True)
                # Ambiguous or rejected submissions stop new production; inspect before continuing.
                atomic(out/'progress.json',{'completed':done,'failed':failed,'pending':[j['job_id'] for j in pending],'elapsed_seconds':time.time()-start})
                raise
        for item in active[:]:
            job,journal,output=item
            try:saved=api.poll(journal)
            except Exception as exc:
                print(json.dumps({'event':'status_get_error','cut':job['job_id'],'error':type(exc).__name__}),flush=True);continue
            state=saved['state']
            if state=='SUCCEEDED':
                try:saved=api.download(journal,output)
                except Exception as exc:
                    print(json.dumps({'event':'download_get_error','cut':job['job_id'],'error':type(exc).__name__}),flush=True);continue
                done.append({'cut':job['job_id'],'id':saved['id'],'sha256':saved['output_sha256'],'output':str(output),'seconds':saved['downloaded_at']-saved['submitted_at']})
                active.remove(item);print(json.dumps({'event':'completed',**done[-1],'count':len(done)},ensure_ascii=False),flush=True)
            elif state in ['FAILED','CANCELLED']:
                failed.append({'cut':job['job_id'],'id':saved['id'],'state':state,'details':saved.get('last_status')});active.remove(item)
                print(json.dumps({'event':'failed',**failed[-1]},ensure_ascii=False),flush=True)
        atomic(out/'progress.json',{'completed':done,'failed':failed,'pending':[j['job_id'] for j in pending],'active':[j[0]['job_id'] for j in active],'elapsed_seconds':time.time()-start})
        if active:time.sleep(args.poll_seconds)
    api.client.close()
    return 1 if failed else 0
if __name__=='__main__':raise SystemExit(main())
