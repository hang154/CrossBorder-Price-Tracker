#!/usr/bin/env python3
"""Install verified replacement backgrounds as immutable assets with edit history."""
import argparse,copy,json,shutil,sys
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.text_edit_agent import read,revision,save_edit,digest
from app.qwen_image_api import atomic

def install(project,run,source,evidence_root):
 before=read(project);doc=copy.deepcopy(before);jobs=[json.loads(s) for s in (source/'cut-jobs.jsonl').read_text().splitlines() if s.strip()];byid={c['id']:c for c in doc['cuts']};receipts=[]
 for j in jobs:
  c=byid[j['job_id']];assert c['approved_copy']==j['cut']['이미지 내 삽입 문구']
  folder=run/j['product_id']/j['job_id'];receipt=json.loads((folder/'job.json').read_text());data=(folder/'image.png').read_bytes();sha=digest(data)
  assert receipt['state']=='SUCCEEDED' and receipt['output_sha256']==sha
  with Image.open(folder/'image.png') as im:assert im.format=='PNG' and im.size==(doc['width'],doc['height']);im.verify()
  name=f"{j['job_id']}-repair-{sha[:12]}";target=project.parent/'assets'/f'{name}.png'
  if target.exists():assert digest(target.read_bytes())==sha
  else:target.write_bytes(data)
  doc['assets'][name]={'path':'assets/'+target.name,'sha256':sha};c['background']=name
  evidence=evidence_root/j['job_id'];evidence.mkdir(parents=True,exist_ok=True)
  for f in ['job.json','cut.json','layout.json','generation-plan.json']:
   if (folder/f).exists():shutil.copyfile(folder/f,evidence/f)
  receipts.append({'cut_id':c['id'],'id':receipt['id'],'sha256':sha,'asset':name})
 assert [c['texts'] for c in doc['cuts']]==[c['texts'] for c in before['cuts']]
 result=save_edit(project,doc,revision(before),'Replace only failed generated background assets; preserve approved copy, panels and original assets')
 atomic(evidence_root/'installed.json',{'revision':result['revision'],'repairs':receipts,'copy_changed':False});return receipts
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--evidence-root',type=Path,required=True);a=p.parse_args();print(json.dumps(install(a.project,a.run,a.source,a.evidence_root)))
