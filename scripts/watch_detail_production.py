#!/usr/bin/env python3
"""Observe an existing producer, review completed cuts, package, then publish outcome."""
import argparse,json,os,sys,time,traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.qwen_image_api import atomic
from review_detail_images import review
from package_qwen_detail_images import package

def alive(pid):
    try:
        state=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[0]
        return state!='Z'
    except FileNotFoundError:return False

def main():
    p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--signal',type=Path,required=True);p.add_argument('--work-id',required=True);a=p.parse_args()
    start=time.time();state='failed';exitcode=1;summary='';reviewed=set();errors=[]
    try:
        while True:
            fresh=[im.parent for im in sorted(a.run.glob('*/*/image.png')) if im.parent.name not in reviewed]
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[(folder,pool.submit(review,folder,a.source)) for folder in fresh]
                for folder,f in futures:
                    try:f.result();reviewed.add(folder.name)
                    except Exception as exc:errors.append({'cut':folder.name,'error':type(exc).__name__});print(json.dumps(errors[-1]),flush=True)
            running=alive(a.pid)
            atomic(a.run/'watch-status.json',{'reviewed':len(reviewed),'images':len(list(a.run.glob('*/*/image.png'))),'producer_running':running,'qa_errors':errors,'elapsed_seconds':time.time()-start})
            if not running:break
            if time.time()-start>10800:raise TimeoutError('Producer still active after monitoring limit; inspect saved IDs')
            time.sleep(12)
        progress=json.loads((a.run/'progress.json').read_text())
        if len(progress.get('completed',[]))!=36 or progress.get('failed') or progress.get('pending') or progress.get('active'):raise RuntimeError('Producer ended without 36 complete cuts')
        # Retry only failed text/vision QA requests once after producer is terminal, not image submissions.
        for im in sorted(a.run.glob('*/*/image.png')):
            if im.parent.name not in reviewed:review(im.parent,a.source);reviewed.add(im.parent.name)
        result=package(a.source,a.run,a.output_dir)
        summary=f"36 PNG, Qwen QA pass {result['automatic_qa_passed']}/36; HTML and ZIP ready"
        state='succeeded';exitcode=0
    except BaseException as exc:
        summary=type(exc).__name__+': '+str(exc);traceback.print_exc()
    atomic(a.run/'production-outcome.json',{'state':state,'summary':summary,'exitCode':exitcode,'elapsed_seconds':time.time()-start,'qa_errors':errors})
    atomic(a.signal,{'workId':a.work_id,'state':state,'summary':summary,'exitCode':exitcode})
    return exitcode
if __name__=='__main__':raise SystemExit(main())
