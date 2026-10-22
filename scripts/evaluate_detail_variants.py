#!/usr/bin/env python3
"""Render exact copy and compare generated methods with local Qwen visual grading."""
import argparse,json,sys,shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.detail_studio import qwen,obj,string,preview
from app.text_edit_agent import init,read,render
from app.qwen_image_api import atomic
from generate_detail_images import references
CRITERIA={'first_impression':3,'product_clarity':3,'selling_point_expression':4,'decision_flow':3,'visual_quality':2}

def evaluate(source,run,out):
 out.mkdir(parents=True,exist_ok=True);project=out/'editable-project/project.json'
 if not project.exists():init(source,run,project.parent)
 doc=read(project);jobs=[json.loads(s) for s in (source/'cut-jobs.jsonl').read_text().splitlines() if s.strip()]
 receipts=render(project);atomic(out/'exports.json',receipts)
 for j,c,r in zip(jobs,doc['cuts'],receipts,strict=True):
  assert j['job_id']==c['id']==r['cut_id']
  assert [p.strip() for p in j['cut']['이미지 내 삽입 문구'].split('/') if p.strip()]==[m['text'] for m in r['metrics']]
 def one(item):
  job,receipt=item;folder=out/'evaluations'/job['job_id'];target=folder/'grade.json'
  if target.exists():
   existing=json.loads(target.read_text())
   if existing['png_sha256']==receipt['png_sha256'] and existing.get('grading_version')==3:return existing
   shutil.copyfile(target,folder/('grade-v'+str(existing.get('grading_version',1))+'.json'))
  score={'type':'integer','minimum':1,'maximum':5}
  schema=obj({'scores':obj({k:score for k in CRITERIA}),'unapproved_text':{'type':'boolean'},'product_match':{'type':'boolean'},'text_readable':{'type':'boolean'},'product_unobscured':{'type':'boolean'},'strengths':string(),'weaknesses':string(),'reason':string()})
  content=[{'type':'text','text':json.dumps({'task':'Grade this REAL rendered Korean product detail hero image, then compare product appearance with the original reference. Korean output. The finished image comes first. Evaluate 1..5 using the five supplied design-review criteria, not sales effectiveness. Do not reward unverified claims, imaginary certification or a product shape that differs from the reference. User approved copy is fixed; propose layout/design changes only. Product intrinsic motifs are not extra sales text.','product':job['product_name'],'approved_copy':job['cut']['이미지 내 삽입 문구'],'method':job['style_method'],'criteria':{'first_impression':'제품 가치의 첫눈 전달·시선 집중','product_clarity':'원본 상품의 형태·색·구성 식별','selling_point_expression':'확정 문구와 실제 사진의 연결','decision_flow':'시선·정보 위계의 흐름','visual_quality':'광원·질감·조판·색상 완성도'},'score_anchors':'1=심각한 실패, 2=큰 보완 필요, 3=보통, 4=좋음, 5=매우 좋음. 각 항목을 실제 이미지에 따라 독립적으로 평가. 항목 이름이나 가중치를 점수로 복사하지 말 것. boolean은 실제 이미지에서 문제가 관측된 경우에만 false로 한다. 상품 자체의 인쇄와 장식은 unapproved_text가 아니다. 상하단 불투명 문구 패널은 정상적인 조판이며 제품과 겹치지 않으면 가림으로 판정하지 않는다.','evidence_type':'model_design_assessment_not_conversion_test'},ensure_ascii=False)},{'type':'image_url','image_url':{'url':preview(project.parent/receipt['file'])}}]
  for ref in references(job,source,run)[:1]:content.append({'type':'image_url','image_url':{'url':preview(ref)}})
  result=qwen(folder,'design-grade',[{'role':'user','content':content}],schema)
  result['critical_issues']=[name for name,failed in [('product_mismatch',not result['product_match']),('unreadable_copy',not result['text_readable']),('copy_over_product',not result['product_unobscured']),('unapproved_text',result['unapproved_text'])] if failed]
  result.update(job_id=job['job_id'],product_id=job['product_id'],method_id=job['style_method']['id'],method_name=job['style_method']['name'],png_sha256=receipt['png_sha256'],image='editable-project/'+receipt['file'],editable_html='editable-project/'+receipt['html'],approved_copy=job['cut']['이미지 내 삽입 문구'],grading_version=3,evidence_type='local_qwen_visual_assessment',conversion_effect='not_established')
  result['eligible']=result['product_match'] and result['text_readable'] and result['product_unobscured'] and not result['critical_issues'];result['weighted_score']=round(sum(result['scores'][k]*w for k,w in CRITERIA.items())/sum(CRITERIA.values()),3)
  atomic(target,result);return result
 with ThreadPoolExecutor(max_workers=2) as pool:grades=list(pool.map(one,zip(jobs,receipts)))
 winners={}
 for pid in dict.fromkeys(j['product_id'] for j in jobs):
  candidates=[g for g in grades if g['product_id']==pid and g['eligible']];winners[pid]=max(candidates,key=lambda g:g['weighted_score'])['job_id'] if candidates else None
 ties={pid:[g['job_id'] for g in grades if g['product_id']==pid and g['eligible'] and g['weighted_score']==next(x['weighted_score'] for x in grades if x['job_id']==job)] if job else [] for pid,job in winners.items()}
 result={'criteria_weights':CRITERIA,'grades':grades,'recommended':winners,'recommended_ties':ties,'conversion_effect':'not_established'};atomic(out/'comparison.json',result);print(json.dumps({'rendered':len(receipts),'graded':len(grades),'recommended':winners},ensure_ascii=False),flush=True);return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();evaluate(a.source,a.run,a.output_dir)
