#!/usr/bin/env python3
"""Build offline comparison HTML, full licensed knowledge bundle and verified ZIP."""
import argparse,hashlib,json,shutil,sys,time,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.qwen_image_api import atomic

def build(expansion,delivery):
 comparison=json.loads((delivery/'comparison.json').read_text());catalog=json.loads((expansion/'method-catalog.json').read_text());repo=Path(__file__).resolve().parents[1]
 for src,dst in [(repo/'skills/ecommerce-detail-page/references/banye',delivery/'knowledge/banye'),(expansion/'observations',delivery/'knowledge/portfolio-observations')]:
  shutil.copytree(src,dst,dirs_exist_ok=True)
 selected=expansion/'selected-methods'
 if selected.exists():
  shutil.copyfile(selected/'selection.json',delivery/'selected-methods.json')
  shutil.copyfile(selected/'source/cut-jobs.jsonl',delivery/'selected-cut-jobs.jsonl')
 for name in ['method-catalog.json','recommendations.json','reference-observations.json']:shutil.copyfile(expansion/name,delivery/name)
 shutil.copyfile(expansion/'references/references.json',delivery/'reference-index.json')
 jobs=[json.loads(s) for s in (expansion/'variant-source/cut-jobs.jsonl').read_text().splitlines() if s.strip()]
 atomic(delivery/'variant-jobs.json',jobs)
 for job in jobs:
  folder=expansion/'variant-images'/job['product_id']/job['job_id'];dest=delivery/'evidence'/job['job_id'];dest.mkdir(parents=True,exist_ok=True)
  for name in ['job.json','cut.json','layout.json','generation-plan.json']:shutil.copyfile(folder/name,dest/name)
 shutil.copytree(expansion/'variant-source/products',delivery/'source-products',dirs_exist_ok=True)
 prepared=expansion/'variant-images/prepared-references'
 if prepared.exists():shutil.copytree(prepared,delivery/'source-prepared-references',dirs_exist_ok=True)
 payload={'comparison':comparison,'catalog':catalog,'jobs':jobs,'knowledge':json.loads((delivery/'knowledge/banye/manifest.json').read_text())}
 template=Path(__file__).resolve().parents[1]/'app/detail_style_comparison.html'
 (delivery/'index.html').write_text(template.read_text().replace('__DATA__',json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')))
 (delivery/'실행.txt').write_text('index.html을 열어 3상품×8스타일을 비교하세요.\n리뷰 저장 서버: python -m app.detail_style_review --root <이폴더> --port 8775\n레이어 좌표 편집: python -m app.text_edit_agent serve --project <이폴더>/editable-project/project.json --port 8777\nknowledge/banye/upstream에 원본 저장소의 전체 31개 파일을 MIT 고지와 함께 보존했습니다.\n로컬 Qwen 점수는 디자인 평가이며 실구매 성과가 아닙니다.\n')
 from bundle_detail_editor import bundle
 bundle(delivery,8777)
 files=[{'path':f.relative_to(delivery).as_posix(),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(delivery.rglob('*')) if f.is_file() and f.name!='manifest.json']
 atomic(delivery/'manifest.json',{'created_at':time.time(),'variants':len(jobs),'knowledge_files':payload['knowledge']['file_count'],'source_commit':payload['knowledge']['commit'],'files':files,'conversion_effect':'not_established'})
 archive=delivery.with_suffix('.zip');temp=archive.with_suffix('.zip.tmp')
 with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
  for f in delivery.rglob('*'):
   if f.is_file():z.write(f,str(Path(delivery.name)/f.relative_to(delivery)))
 with zipfile.ZipFile(temp) as z:
  assert z.testzip() is None
  for f in files:assert hashlib.sha256(z.read(str(Path(delivery.name)/f['path']))).hexdigest()==f['sha256']
 temp.replace(archive);result={'zip':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size,'variants':len(jobs)};atomic(expansion/'comparison-delivery.json',result);print(json.dumps(result,ensure_ascii=False));return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--expansion',type=Path,required=True);p.add_argument('--delivery',type=Path,required=True);a=p.parse_args();build(a.expansion,a.delivery)
