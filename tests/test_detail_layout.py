import copy,json,subprocess,sys
from pathlib import Path
import pytest
from app.detail_layout import plan_layout,background_prompt,text_layers,validate_layout
from app.text_edit_agent import init

@pytest.fixture
def job():return {'job_id':'sample-cut-01','product_id':'sample','product_name':'상품','cut':{'이미지 구성':'중앙 상품과 상하 문구 영역','이미지 내 삽입 문구':'정확한 제목 / 50% 그대로 / 띄어쓰기 유지'}}

def test_background_never_receives_approved_copy(job):
 layout=plan_layout(job)
 prompt=background_prompt(job,{'sample-cut-01':'简洁白色背景的产品摄影'},layout)
 assert all(s['text'] not in prompt for s in layout['slots'])
 assert [t['text'] for t in text_layers(layout)]==['정확한 제목','50% 그대로','띄어쓰기 유지']
 with pytest.raises(ValueError):background_prompt(job,{job['job_id']:'商品 '+layout['slots'][0]['text']},layout)
 assert layout['slots'][0]['y']<2304*.25 and layout['slots'][1]['y']>=2304*.7

@pytest.mark.parametrize('change',['copy','bounds','overlap','nan'])
def test_bad_layout_rejected(job,change):
 layout=plan_layout(job)
 if change=='copy':layout['slots'][0]['text']='임의 수정'
 elif change=='bounds':layout['slots'][0]['x']=1536
 elif change=='overlap':layout['slots'][1]['y']=layout['slots'][0]['y']
 else:layout['slots'][0]['width']=float('nan')
 with pytest.raises(ValueError):validate_layout(layout,job,1536,2304)

def test_plan_only_and_import_exact_layers(job,tmp_path):
 from PIL import Image
 source=tmp_path/'source';source.mkdir();(source/'cut-jobs.jsonl').write_text(json.dumps(job,ensure_ascii=False)+'\n')
 run=tmp_path/'run';run.mkdir();(run/'visual-directions.json').write_text(json.dumps({job['job_id']:'白色背景产品摄影'}))
 script=Path(__file__).resolve().parents[1]/'scripts/generate_detail_images.py'
 args=[sys.executable,str(script),'--source',str(source),'--output-dir',str(run),'--plan-only']
 result=subprocess.run(args,capture_output=True,text=True)
 assert result.returncode==0,result.stderr
 assert json.loads(result.stdout)['api_called'] is False
 folder=run/job['product_id']/job['job_id'];assert not (folder/'job.json').exists()
 layout=json.loads((folder/'layout.json').read_text());assert layout==plan_layout(job)
 # Pre-submit edits are accepted, then imported as exact editable text layers.
 layout['slots'][0]['x']+=1;overrides=tmp_path/'layouts.json';overrides.write_text(json.dumps({job['job_id']:layout}))
 result=subprocess.run(args+['--layouts',str(overrides)],capture_output=True,text=True);assert result.returncode==0,result.stderr
 Image.new('RGB',(1536,2304),'white').save(folder/'image.png')
 doc=init(source,run,tmp_path/'editor')
 assert doc['cuts'][0]['texts'][0]['x']==layout['slots'][0]['x']
 assert doc['cuts'][0]['approved_copy']==job['cut']['이미지 내 삽입 문구']
 assert [t['text'] for t in doc['cuts'][0]['texts']]==[s['text'] for s in layout['slots']]
 (folder/'job.json').write_text('{}')
 result=subprocess.run(args,capture_output=True,text=True);assert result.returncode!=0 and 'Frozen layout changed' in result.stderr


def test_blank_background_qa_and_portable_package(job,tmp_path,monkeypatch):
 import hashlib,importlib.util
 from PIL import Image
 scripts=Path(__file__).resolve().parents[1]/'scripts'
 def load(name):
  spec=importlib.util.spec_from_file_location(name,scripts/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 review=load('review_detail_images');pack=load('package_qwen_detail_images')
 source=tmp_path/'source';source.mkdir();(source/'cut-jobs.jsonl').write_text(json.dumps(job,ensure_ascii=False)+'\n')
 run=tmp_path/'run';folder=run/job['product_id']/job['job_id'];folder.mkdir(parents=True)
 image=folder/'image.png';Image.new('RGB',(1536,2304),'white').save(image)
 (folder/'cut.json').write_text(json.dumps(job));(folder/'layout.json').write_text(json.dumps(plan_layout(job)))
 (folder/'job.json').write_text(json.dumps({'state':'SUCCEEDED','id':'fixture-no-api','output_sha256':hashlib.sha256(image.read_bytes()).hexdigest()}))
 requests=[]
 def fake_qwen(directory,name,messages,schema):
  requests.append(messages)
  return {'visible_text':'','unapproved_text':[],'product_match':True,'blank_zones_clear':True,'pass':True,'notes':'fixture only'}
 monkeypatch.setattr(review,'qwen',fake_qwen)
 qa=review.review(folder);assert qa['pass'] and qa['mode']=='blank-background-v1'
 assert 'Missing sales copy is intentional' in requests[0][0]['content'][0]['text']
 for text in ['정확한 제목','50% 그대로','띄어쓰기 유지']:assert text not in requests[0][0]['content'][0]['text']
 assert review.review(folder)==qa and len(requests)==1
 result=pack.package(source,run,tmp_path/'delivery',expected=1)
 assert result['images'][0]['mode']=='blank-background-v1'
 editable=json.loads((tmp_path/'delivery/editable-project/project.json').read_text())
 assert len(editable['cuts'][0]['texts'])==3
 assert (tmp_path/'delivery/evidence'/job['job_id']/'layout.json').exists()
 assert (tmp_path/'delivery.zip').exists()
