#!/usr/bin/env python3
"""Qwen-Image submit once or resume an authenticated asynchronous image job."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.qwen_image_api import ImageAPI,headers,atomic

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prompt');p.add_argument('--image',action='append',default=[])
    p.add_argument('--size',default='2048x2048');p.add_argument('--steps',type=int,default=50)
    p.add_argument('--seed',type=int,default=42);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--job-id');p.add_argument('--key-file');p.add_argument('--poll-seconds',type=float,default=8)
    a=p.parse_args();journal=Path(str(a.output)+'.job.json')
    if a.output.exists() and not journal.exists():raise FileExistsError('Output exists without matching journal')
    api=ImageAPI(auth=headers(a.key_file))
    if a.job_id:
        api.job_id(a.job_id)
        if journal.exists():
            if json.loads(journal.read_text()).get('id')!=a.job_id:raise ValueError('Journal ID differs')
        else:atomic(journal,{'id':a.job_id,'state':'RESUMING','automatic_post_retry':False})
    elif not journal.exists() or a.prompt:
        if not a.prompt:p.error('--prompt or --job-id is required')
        api.submit(a.prompt,journal,a.image,a.size,a.steps,a.seed)
    while True:
        saved=api.poll(journal);print(json.dumps({'id':saved['id'],'state':saved['state']}),flush=True)
        if saved['state']=='SUCCEEDED':
            api.download(journal,a.output);api.client.close();return 0
        if saved['state'] in ['FAILED','CANCELLED']:api.client.close();return 1
        time.sleep(a.poll_seconds)
if __name__=='__main__':raise SystemExit(main())
