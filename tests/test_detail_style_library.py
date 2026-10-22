import copy,hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
import httpx
from app.detail_style_library import ROOT,METHODS,knowledge,match_methods

def module(name):
 spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_full_knowledge_import_and_balanced_context():
 root=ROOT/'skills/ecommerce-detail-page/references/banye';manifest=json.loads((root/'manifest.json').read_text())
 assert manifest['file_count']==31
 for r in manifest['files']:assert hashlib.sha256((root/'upstream'/r['path']).read_bytes()).hexdigest()==r['sha256']
 selected=knowledge(24)
 assert any(c['path'].endswith('daily-use.md') for c in selected)
 assert any(c['path'].endswith('fbe-sellpoint-model.md') for c in selected)
 assert len({c['id'] for c in selected})==len(selected)
 assert (root/'upstream/LICENSE').exists()
 assert match_methods(traffic='gift_search')[0]['method']['id']=='gift_narrative'


def test_variant_contracts_same_copy_and_eight_methods():
 root=ROOT/'sourcing-runs/detail-reference-expansion-20261022'
 jobs=[json.loads(s) for s in (root/'variant-source/cut-jobs.jsonl').read_text().splitlines()]
 assert len(jobs)==24
 for pid in {j['product_id'] for j in jobs}:
  group=[j for j in jobs if j['product_id']==pid]
  assert {j['style_method']['id'] for j in group}=={m['id'] for m in METHODS}
  assert len({j['cut']['이미지 내 삽입 문구'] for j in group})==1
  assert all(j['knowledge_refs'] for j in group)


def test_human_selection_overrides_model_and_keeps_copy(tmp_path):
 source=tmp_path/'source';source.mkdir();(source/'products').mkdir();comparison=tmp_path/'comparison';comparison.mkdir()
 job={'job_id':'p1-cut-01','product_id':'p1','cut':{'이미지 내 삽입 문구':'원문 그대로','이미지 구성':'제품 중앙'}}
 (source/'cut-jobs.jsonl').write_text(json.dumps(job)+'\n')
 grades=[{'job_id':'a','product_id':'p1','method_id':'clean_information','png_sha256':'hasha'},{'job_id':'b','product_id':'p1','method_id':'gift_narrative','png_sha256':'hashb'}]
 (comparison/'comparison.json').write_text(json.dumps({'grades':grades,'recommended':{'p1':'a'}}))
 (comparison/'human-reviews.jsonl').write_text(json.dumps({'selected':True,'job_id':'b','product_id':'p1','method_id':'gift_narrative','png_sha256':'hashb'})+'\n')
 prepared=module('prepare_selected_detail_style').prepare(source,comparison,tmp_path/'out')
 assert prepared[0]['style_method']['id']=='gift_narrative'
 assert prepared[0]['cut']==job['cut'] and prepared[0]['selection_source']=='human_review'
 assert not list((tmp_path/'out').rglob('job.json'))


def test_review_server_auth_persistence_and_browser(tmp_path):
 from playwright.sync_api import sync_playwright
 grade={'job_id':'a','product_id':'p1','method_id':'clean_information','method_name':'정보형','png_sha256':'abc','weighted_score':4.2,'image':'blank.svg','editable_html':'blank.svg','reason':'기획 근거','strengths':'명확함','weaknesses':'보완점','scores':{'visual_quality':4}}
 (tmp_path/'comparison.json').write_text(json.dumps({'grades':[grade],'recommended':{'p1':'a'}}))
 payload={'comparison':{'grades':[grade],'recommended':{'p1':'a'}},'catalog':{'methods':METHODS},'jobs':[{'product_id':'p1','product_name':'상품'}],'knowledge':{'file_count':31,'files':[]}}
 (tmp_path/'index.html').write_text((ROOT/'app/detail_style_comparison.html').read_text().replace('__DATA__',json.dumps(payload,ensure_ascii=False)))
 (tmp_path/'blank.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="450"/>')
 proc=subprocess.Popen([sys.executable,'-u','-m','app.detail_style_review','--root',str(tmp_path),'--port','0'],stdout=subprocess.PIPE,text=True)
 try:
  url=proc.stdout.readline().strip().split()[-1]
  assert httpx.post(url+'/api/review',json={}).status_code==403
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(url);page.wait_for_function('session!==null');page.locator('textarea').fill('사람이 선택한 이유');page.locator('article button').click();page.wait_for_function("document.querySelector('#status').textContent.includes('저장했습니다')")
   row=json.loads((tmp_path/'human-reviews.jsonl').read_text());assert row['notes']=='사람이 선택한 이유' and row['png_sha256']=='abc'
   page.reload();page.wait_for_function("document.querySelector('#status').textContent.includes('저장된 평가 1건')")
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors;b.close()
 finally:proc.terminate();proc.wait(timeout=10)


def test_grading_prompt_separates_weights_from_observed_scores(tmp_path,monkeypatch):
 from PIL import Image
 from app.detail_layout import plan_layout
 monkeypatch.syspath_prepend(str(ROOT/'scripts'));evaluator=module('evaluate_detail_variants')
 source=tmp_path/'source';source.mkdir();run=tmp_path/'run';jobs=[]
 for n,method in enumerate(METHODS[:2]):
  job={'job_id':f'p1-style-{n}','product_id':'p1','product_name':'테스트 상품','style_method':method,'cut':{'이미지 내 삽입 문구':'동일 원문','이미지 구성':'상품 중앙'}};jobs.append(job)
  folder=run/'p1'/job['job_id'];folder.mkdir(parents=True);Image.new('RGB',(1536,2304),'white').save(folder/'image.png');(folder/'layout.json').write_text(json.dumps(plan_layout(job)))
 (source/'cut-jobs.jsonl').write_text(''.join(json.dumps(j)+'\n' for j in jobs))
 monkeypatch.setattr(evaluator,'references',lambda *a:[])
 def fake_qwen(folder,tag,messages,schema):
  prompt=json.loads(messages[0]['content'][0]['text'])
  assert all(isinstance(v,str) for v in prompt['criteria'].values())
  assert 'criteria_weights' not in prompt
  score=5 if prompt['method']['id']=='premium_gallery' else 2
  return {'scores':{k:score for k in evaluator.CRITERIA},'unapproved_text':False,'product_match':True,'text_readable':True,'product_unobscured':True,'strengths':'근거','weaknesses':'근거','reason':'이미지에 따른 판정'}
 monkeypatch.setattr(evaluator,'qwen',fake_qwen)
 result=evaluator.evaluate(source,run,tmp_path/'delivery')
 assert result['recommended']['p1']=='p1-style-1'
 assert {g['weighted_score'] for g in result['grades']}=={2,5}
 assert all(g['grading_version']==3 for g in result['grades'])


def test_copy_reflow_preserves_literal_text_and_versions(tmp_path):
 from PIL import Image
 from app.detail_layout import plan_layout
 from app.text_edit_agent import init,read,revision
 source=tmp_path/'source';source.mkdir();run=tmp_path/'run';job={'job_id':'p1-cut-01','product_id':'p1','product_name':'상품','cut':{'이미지 내 삽입 문구':'띄어쓰기 그대로 / 50% 유지 / 끝 문구','이미지 구성':'중앙 상품'}}
 (source/'cut-jobs.jsonl').write_text(json.dumps(job)+'\n');folder=run/'p1'/job['job_id'];folder.mkdir(parents=True);Image.new('RGB',(1536,2304),'white').save(folder/'image.png');(folder/'layout.json').write_text(json.dumps(plan_layout(job)))
 project=tmp_path/'editor/project.json';before=init(source,run,project.parent);old=revision(before)
 module('reflow_detail_copy').reflow(project);after=read(project);cut=after['cuts'][0]
 assert [t['text'] for t in cut['texts']]==[t['text'] for t in before['cuts'][0]['texts']]
 assert cut['approved_copy']==job['cut']['이미지 내 삽입 문구']
 assert after['assets']==before['assets'] and (project.parent/'versions'/f'{old}.json').exists()
 assert len(cut['masks'])==2
 for t in cut['texts']:
  assert any(t['x']>=m['x'] and t['y']>=m['y'] and t['x']+t['width']<=m['x']+m['width'] and t['y']+t['height']<=m['y']+m['height'] for m in cut['masks'])


def test_replacement_background_verifies_receipt_and_preserves_copy(tmp_path):
 from PIL import Image
 from app.text_edit_agent import init,read
 from app.detail_layout import plan_layout
 import pytest
 source=tmp_path/'source';source.mkdir();run=tmp_path/'run';job={'job_id':'p1-cut-01','product_id':'p1','product_name':'상품','cut':{'이미지 내 삽입 문구':'원문 그대로','이미지 구성':'중앙 상품'}}
 (source/'cut-jobs.jsonl').write_text(json.dumps(job)+'\n');folder=run/'p1'/job['job_id'];folder.mkdir(parents=True);Image.new('RGB',(1536,2304),'white').save(folder/'image.png');(folder/'layout.json').write_text(json.dumps(plan_layout(job)))
 project=tmp_path/'editor/project.json';before=init(source,run,project.parent);oldsha=next(iter(before['assets'].values()))['sha256']
 Image.new('RGB',(1536,2304),'beige').save(folder/'image.png');sha=hashlib.sha256((folder/'image.png').read_bytes()).hexdigest();receipt={'state':'SUCCEEDED','id':'fixture-no-api','output_sha256':'bad'};(folder/'job.json').write_text(json.dumps(receipt))
 installer=module('install_detail_background_repairs')
 with pytest.raises(AssertionError):installer.install(project,run,source,tmp_path/'evidence')
 assert read(project)==before
 receipt['output_sha256']=sha;(folder/'job.json').write_text(json.dumps(receipt));installer.install(project,run,source,tmp_path/'evidence');after=read(project)
 assert after['cuts'][0]['texts']==before['cuts'][0]['texts'] and after['cuts'][0]['approved_copy']==before['cuts'][0]['approved_copy']
 assert any(a['sha256']==oldsha for a in after['assets'].values()) and any(a['sha256']==sha for a in after['assets'].values())
 assert (tmp_path/'evidence/installed.json').exists()
