"""Supervise small private-Xvfb batches; bound driver hangs and preserve results."""
import argparse,datetime as dt,hashlib,json,os,shutil,signal,subprocess,tempfile,time
from pathlib import Path
from app.sourcing_pipeline import atomic_json
from app.coupang_reviews import KST

def descendants(root):
 parents={}
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   s=(p/'stat').read_text().rsplit(')',1)[1].split();parents[int(p.name)]=int(s[1])
  except (OSError,ValueError,IndexError):pass
 found={root}
 while True:
  new={pid for pid,parent in parents.items() if parent in found}
  if new<=found:return found
  found|=new

def kill_owned(process):
 owned=descendants(process.pid)
 # Remember the exact child tree before its parent disappears.
 for sig in (signal.SIGTERM,signal.SIGKILL):
  for pid in sorted(owned,reverse=True):
   try:os.kill(pid,sig)
   except ProcessLookupError:pass
  if sig==signal.SIGTERM:time.sleep(.3)
 process.wait(timeout=10)
 return len(owned)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--queue',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--resume-from',type=Path);ap.add_argument('--batch-size',type=int,default=4);ap.add_argument('--batch-timeout',type=int,default=90);args=ap.parse_args()
 if not 1<=args.batch_size<=4 or not 30<=args.batch_timeout<=180:raise ValueError('Invalid batch limits')
 out=args.out;out.mkdir(parents=True,exist_ok=True);raw=args.queue.read_bytes();source=json.loads(raw);products=source['products'];started=time.monotonic();os.nice(19)
 state=dict(source_sha256=hashlib.sha256(raw).hexdigest(),as_of=source['as_of'],started_at_kst=dt.datetime.now(KST).isoformat(),engine='owned Xvfb / Chrome143 / supervised batches',navigation='home search then exact observed product link',total=len(products),processed=0,products={},batches=[],detail_complete=0,reviews_complete=0,reviews_partial=0,artificial_delay_seconds=0,llm_calls=0,virtual_display={'kind':'private_xvfb','desktop_display_reused':False,'desktop_dbus_reused':False})
 if source.get('parent_source_sha256'):state['parent_source_sha256']=source['parent_source_sha256']
 if args.resume_from:
  old=json.loads((args.resume_from/'manifest.json').read_text())
  if not old.get('finished_at_kst') or old.get('parent_source_sha256')!=state['source_sha256'] or old.get('as_of')!=state['as_of']:raise ValueError('Resume input is not a terminal subset of this frozen source')
  known={str(p['product_id']) for p in products}
  for pid,entry in old['products'].items():
   if pid not in known or not entry.get('attempts'):raise ValueError('Resume product missing evidence or absent from source')
   state['products'][pid]=entry
   for kind in ('reviews','details'):
    src=args.resume_from/kind/pid;target=out/kind/pid
    if src.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(src,target,dirs_exist_ok=True)
 remaining=[p for p in products if str(p['product_id']) not in state['products']]
 try:
  plan=[remaining[start:start+args.batch_size] for start in range(0,len(remaining),args.batch_size)]
  for batch in plan:
   folder=out/'batches'/f'{len(state["batches"])+1:03d}';folder.mkdir(parents=True,exist_ok=True);runtime=Path(tempfile.mkdtemp(prefix='cpvb-',dir='/tmp'));queue=folder/'queue.json';atomic_json(queue,dict(as_of=source['as_of'],products=batch))
   env=dict(os.environ,TMPDIR=str(runtime.resolve()),PYTHONPATH=os.getcwd());record=dict(products=[str(p['product_id']) for p in batch],started_at_kst=dt.datetime.now(KST).isoformat())
   with (folder/'execution.log').open('w') as log:
    child=subprocess.Popen([os.sys.executable,'scripts/coupang_isolated_purchase_audit.py','--queue',str(queue),'--out',str(folder/'result'),'--profile-dir',str(runtime/'profile')],env=env,stdout=log,stderr=subprocess.STDOUT)
    try:record['exit_code']=child.wait(timeout=args.batch_timeout)
    except subprocess.TimeoutExpired:record.update(timed_out=True,owned_processes_terminated=kill_owned(child),exit_code=child.returncode)
   manifest=folder/'result/manifest.json';observed=json.loads(manifest.read_text()) if manifest.exists() else {};record['fatal_error']=observed.get('fatal_error');record['runtime_path']=str(runtime)
   profile=Path(observed['profile_path']) if observed.get('profile_path') else None
   if profile and profile.resolve().parent==Path('/tmp') and profile.name.startswith('cpvb-profile-'):shutil.rmtree(profile,ignore_errors=True)
   record['profile_removed']=not profile or not profile.exists()
   for p in batch:
    pid=str(p['product_id']);entry=observed.get('products',{}).get(pid)
    if entry and entry.get('attempts'):
     state['products'][pid]=entry
     for kind in ('reviews','details'):
      src=folder/'result'/kind/pid;target=out/kind/pid
      if src.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(src,target,dirs_exist_ok=True)
    else:state['products'][pid]=dict(attempts=[],detail_status='pending',review_status='pending',execution_error='Batch driver unavailable before product reached')
   if len(batch)>1:
    plan.extend([[p] for p in batch if not state['products'][str(p['product_id'])].get('attempts')])
   # A killed driver cannot clean its private profile/display. Remove only this batch's runtime.
   shutil.rmtree(runtime,ignore_errors=True);record.update(profile_removed=not profile or not profile.exists(),runtime_removed=not runtime.exists(),finished_at_kst=dt.datetime.now(KST).isoformat());state['batches'].append(record)
   state.update(processed=len(state['products']),actually_attempted=sum(bool(p.get('attempts')) for p in state['products'].values()),detail_complete=sum(p.get('detail_status')=='complete' for p in state['products'].values()),reviews_complete=sum(p.get('review_status')=='complete' for p in state['products'].values()),reviews_partial=sum(p.get('review_status')=='partial' for p in state['products'].values()),updated_at_kst=dt.datetime.now(KST).isoformat());atomic_json(out/'manifest.json',state)
   if len(state['batches'])>=2 and all(b.get('fatal_error') and 'SessionNotCreatedException' in b['fatal_error'] for b in state['batches'][-2:]):raise RuntimeError('Repeated virtual Chrome startup failure; stopping unproductive retries')
 except Exception as exc:state['fatal_error']=type(exc).__name__+': '+str(exc)[:600]
 finally:
  state.update(profile_removed=all(b.get('runtime_removed') and b.get('profile_removed') for b in state['batches']),virtual_display_removed=all(b.get('runtime_removed') for b in state['batches']),finished_at_kst=dt.datetime.now(KST).isoformat(),elapsed_seconds=round(time.monotonic()-started,3));atomic_json(out/'manifest.json',state)
 return 0 if state['detail_complete']==len(products) and state['reviews_complete']==len(products) else 3
if __name__=='__main__':raise SystemExit(main())
