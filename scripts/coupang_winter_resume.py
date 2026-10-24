"""Supervise existing home-search route, reusing Qwen/source evidence for failures only."""
import argparse,datetime as dt,json,os,subprocess,time
from pathlib import Path
from app.sourcing_pipeline import atomic_json
from scripts.coupang_virtual_batch import kill_owned


def run(source,out):
 out.mkdir(parents=True,exist_ok=True)
 base=json.loads((source/'config.json').read_text());manifest=json.loads((source/'manifest.json').read_text())
 matches=json.loads((source/'matches.json').read_text());done={x['offer_id'] for x in matches if x['status']=='compared'}
 pending=[x for c in manifest['categories'] for x in c.get('selected',[]) if x['offer_id'] not in done]
 categories={x['offer_id']:c for c in manifest['categories'] for x in c.get('selected',[])}
 plan=[pending[i:i+4] for i in range(0,len(pending),4)];retried=set();results={};batches=[]
 state=dict(status='running',source=str(source),total=len(pending),prior_completed=len(done),route='existing private-Xvfb home -> visible search -> observed DOM products',artificial_delay_seconds=0,desktop_attached=False,started_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat())
 def save():
  state.update(batches=batches,attempted=len(results),completed=sum(x.get('status')=='compared' for x in results.values()),domestic_rows=sum(len(x.get('products',[])) for x in results.values()),results=results)
  atomic_json(out/'manifest.json',state)
  (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>겨울 공산품 쿠팡 재개</title><h1>쿠팡 미완료 검색 재개</h1><p>기존 성공 8건 유지 · 실패 '+str(len(pending))+'건 대상</p><p>재개 비교 완료 '+str(state['completed'])+' / 확보 목록 '+str(state['domestic_rows'])+'</p><p><a href="manifest.json">원본 진행 자료</a></p>'+''.join('<p><a href="batches/'+str(i+1).zfill(3)+'/result/index.html">묶음 '+str(i+1)+' 결과·엑셀</a></p>' for i in range(len(batches))))
 save()
 for group in plan:
  folder=out/'batches'/str(len(batches)+1).zfill(3);folder.mkdir(parents=True,exist_ok=True)
  cfg=dict(base);cfg['searches']=[];cfg['cached_offers']={};cfg['preselected']={};cfg['selection_source']=str(source)
  for x in group:
   c=categories[x['offer_id']];k=c['keyword']
   if k not in cfg['cached_offers']:cfg['searches'].append(dict(label=c['label'],keyword=k))
   cfg['cached_offers'][k]=str(source/'categories'/c['id']/'offers.json');cfg['preselected'].setdefault(k,[]).append(x)
  atomic_json(folder/'config.json',cfg)
  record=dict(offers=[x['offer_id'] for x in group],started=time.time())
  with (folder/'execution.log').open('w') as log:
   proc=subprocess.Popen([os.sys.executable,'-u','scripts/1688_first_discovery.py','--config',str(folder/'config.json'),'--out',str(folder/'result')],stdout=log,stderr=subprocess.STDOUT)
   try:record['exit_code']=proc.wait(timeout=240)
   except subprocess.TimeoutExpired:record.update(timeout=True,cleaned_owned_processes=kill_owned(proc),exit_code=proc.returncode)
  f=folder/'result/matches.json';rows=json.loads(f.read_text()) if f.exists() else []
  for x in rows:results[x['offer_id']]=x
  f=folder/'result/manifest.json';child=json.loads(f.read_text()) if f.exists() else {}
  record.update(seconds=round(time.time()-record.pop('started'),2),error=child.get('error'),completed=sum(x['status']=='compared' for x in rows));batches.append(record)
  if child.get('coupang_restriction') or 'verification' in str(child.get('error','')).lower():
   state.update(status='partial_restriction');save();break
  incomplete=[x for x in group if results.get(x['offer_id'],{}).get('status')!='compared' and x['offer_id'] not in retried]
  for x in incomplete:retried.add(x['offer_id']);plan.append([x])
  save()
 state.update(status=state['status'] if state['status']=='partial_restriction' else ('complete' if state['completed']==len(pending) else 'partial'),finished_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat());save()
 return 0 if state['status']=='complete' else 3

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();raise SystemExit(run(a.source.resolve(),a.out.resolve()))
