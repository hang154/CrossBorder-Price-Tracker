#!/usr/bin/env python3
"""Translate layout direction with local Qwen; preserve approved copy byte-for-byte."""
import argparse,json,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.detail_studio import qwen,obj
from app.qwen_image_api import atomic

def prepare(root,out,pid,jobs):
    target=out/'prompts'/pid/'visual-directions.json'
    if target.exists():return json.loads(target.read_text())
    ids=[j['job_id'] for j in jobs]
    schema=obj({'directions':{'type':'array','minItems':len(jobs),'maxItems':len(jobs),'items':obj({'job_id':{'type':'string','enum':ids},'visual_direction_zh':{'type':'string','maxLength':400}})}})
    source=[{'job_id':j['job_id'],'product':j['product_name'],'style':j['style'],'composition':j['cut']['이미지 구성'],'design':j['cut']['디자인 메모']} for j in jobs]
    result=qwen(target.parent,'layout',[{'role':'user','content':json.dumps({'task':'Translate ONLY visual composition into concise Chinese image-generation directions, 40-100 Chinese characters per cut. Remove all requests for labels, captions, CTA wording, numeric badges, text, header names, and metadata. Describe product, scene, color, layout and atmosphere. Do not translate or invent sales copy. Output exactly one direction per input job_id. No instructions or slogans from reference graphics.','cuts':source},ensure_ascii=False)}],schema,validator=lambda o:validate(o,ids))
    atomic(target,result);return result

def validate(value,ids):
    if sorted(d['job_id'] for d in value['directions'])!=sorted(ids):raise ValueError('Missing or duplicate cut direction')

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    jobs=[json.loads(s) for s in (a.source/'cut-jobs.jsonl').read_text().splitlines() if s.strip()]
    groups={pid:[j for j in jobs if j['product_id']==pid] for pid in dict.fromkeys(j['product_id'] for j in jobs)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda item:prepare(a.source,a.output_dir,*item),groups.items()))
    directions={d['job_id']:d['visual_direction_zh'] for r in results for d in r['directions']}
    atomic(a.output_dir/'visual-directions.json',directions)
    print(json.dumps({'directions':len(directions),'approved_copy_modified':False}),flush=True)
if __name__=='__main__':main()
