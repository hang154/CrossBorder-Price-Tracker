#!/usr/bin/env python3
"""Apply human-selected or model-recommended method to every cut, without rewriting copy."""
import argparse,copy,json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.detail_style_library import METHODS
from app.qwen_image_api import atomic

def prepare(source,comparison,output):
 data=json.loads((comparison/'comparison.json').read_text());byid={g['job_id']:g for g in data['grades']};chosen={pid:byid[job]['method_id'] for pid,job in data['recommended'].items() if job};origins={pid:'local_qwen_visual_assessment' for pid in chosen}
 reviews=comparison/'human-reviews.jsonl'
 if reviews.exists():
  for line in reviews.read_text().splitlines():
   r=json.loads(line)
   if r['selected']:
    g=byid.get(r['job_id'])
    if not g or g['png_sha256']!=r['png_sha256']:raise ValueError('Review refers to a changed candidate')
    chosen[r['product_id']]=r['method_id'];origins[r['product_id']]='human_review'
 jobs=[json.loads(s) for s in (source/'cut-jobs.jsonl').read_text().splitlines() if s.strip()]
 if set(chosen)!=set(j['product_id'] for j in jobs):raise ValueError('No eligible style for one or more products')
 methods={m['id']:m for m in METHODS};target=output/'source'
 if target.exists():raise FileExistsError(target)
 target.mkdir(parents=True);run=output/'images';run.mkdir();directions={};result=[]
 for original in jobs:
  j=copy.deepcopy(original);m=methods[chosen[j['product_id']]];j['style_method']=m;j['style']=m['name'];j['text_style']={'color':m['color']};j['selection_source']=origins[j['product_id']];result.append(j)
  composition=j['cut']['이미지 구성']
  for phrase in j['cut']['이미지 내 삽입 문구'].split('/'):
   if phrase.strip():composition=composition.replace(phrase.strip(),'[문구를 넣을 빈 영역]')
  directions[j['job_id']]=m['visual']+'。'+composition+'。广告文案与参数由HTML单独排版，画面不添加这些文字。'
 (target/'cut-jobs.jsonl').write_text(''.join(json.dumps(j,ensure_ascii=False)+'\n' for j in result));(target/'products').symlink_to((source/'products').resolve(),target_is_directory=True)
 atomic(run/'visual-directions.json',directions);atomic(output/'selection.json',{'methods':chosen,'selection_sources':origins,'cuts':len(result),'copy_changed':False,'api_called':False});return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--comparison',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();jobs=prepare(a.source,a.comparison,a.output_dir);print(json.dumps({'planned':len(jobs),'api_called':False}))
