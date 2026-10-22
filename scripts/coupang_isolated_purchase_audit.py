"""Run the existing paired detail/review crawler in an isolated local Chrome.
Home -> visible search -> exact observed product link. Keep successful stages;
retry only unfinished products, without imposed request spacing.
"""
import argparse,datetime as dt,hashlib,json,os,shutil,tempfile,time
from pathlib import Path
import setuptools
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from app import coupang_reviews as reviews
from app.coupang_purchase_audit import capture_detail,monthly_metrics
from app.sourcing_pipeline import atomic_json
from app.isolated_display import virtual_display

HOME='https://www.coupang.com/'
OriginalBrowser=reviews.Browser
class IsolatedBrowser(OriginalBrowser):
 def __init__(self,driver,coordinator=None):self.driver=driver;self.coordinator=coordinator;self.access_gate=None
 def call(self,action,*args,**kwargs):
  d=self.driver
  if action=='open':
   if args[0]!=HOME:raise ValueError('Home-first entry required')
   d.get(HOME);return {'url':d.current_url}
  if action=='eval':
   # Resolve async extraction promises and synchronous expressions alike.
   return d.execute_async_script('const done=arguments[arguments.length-1];Promise.resolve().then(()=>('+args[0]+')).then(done,e=>done({error:String(e)}));')
  if action=='tab':
   if args[0]=='list':return [{'page':d.current_window_handle,'active':True}]
   if args[0]=='select':d.switch_to.window(args[1]);return None
  if action=='fill':
   el=d.find_element(By.CSS_SELECTOR,args[0]);el.clear();el.send_keys(args[1]);return {'verified':el.get_attribute('value')==args[1]}
  if action=='click':
   if args[0]=='--role':
    name=args[args.index('--name')+1];elements=d.find_elements(By.CSS_SELECTOR,'button,[role="button"]');targets=[e for e in elements if e.is_displayed() and e.text.strip()==name]
    if len(targets)!=1:raise ValueError('Visible button not uniquely found: '+name)
    element=targets[0]
   else:element=d.find_element(By.CSS_SELECTOR,args[0])
   element.click();return None
  if action=='scroll':d.execute_script('window.scrollBy(0,800)');return None
  if action=='close':return None  # Keep this owned Chrome for the next queued product.
  raise ValueError('Unsupported browser operation: '+action)

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--queue',required=True,type=Path);ap.add_argument('--out',required=True,type=Path);ap.add_argument('--profile-dir',type=Path);ap.add_argument('--max-products',type=int,default=137);ap.add_argument('--attempts',type=int,choices=range(1,4),default=3);ap.add_argument('--max-pages',type=int,default=100);args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
 source_bytes=args.queue.read_bytes();queue=json.loads(source_bytes)['products'][:args.max_products];as_of=dt.datetime.now(reviews.KST).date();manifest=out/'manifest.json';state=json.loads(manifest.read_text()) if manifest.exists() else {'products':{}};state.update(source_sha256=hashlib.sha256(source_bytes).hexdigest(),as_of=as_of.isoformat(),started_at_kst=dt.datetime.now(reviews.KST).isoformat(),total=len(queue),processed=0,artificial_delay_seconds=0,engine='isolated local Chrome143 / undetected_chromedriver3.5.5',navigation='home search then exact source product link',llm_calls=0)
 driver=None;display=None
 if args.profile_dir:
  args.profile_dir.mkdir(mode=0o700);profile=str(args.profile_dir.resolve())
 else:profile=tempfile.mkdtemp(prefix='cpvb-profile-',dir='/tmp')
 state['profile_path']=profile;state['phase']='starting_virtual_browser';atomic_json(manifest,state);started=time.monotonic()
 try:
  os.nice(19);display=virtual_display();state['virtual_display']=display.__enter__()
  options=uc.ChromeOptions();options.add_argument('--disable-dev-shm-usage');options.add_argument('--no-first-run');options.add_argument('--no-default-browser-check');options.add_argument('--ozone-platform=x11');options.add_argument('--window-size=1280,900')
  driver=uc.Chrome(options=options,browser_executable_path='/usr/bin/google-chrome',version_main=143,user_data_dir=profile,headless=False,use_subprocess=True);driver.set_page_load_timeout(25);driver.set_script_timeout(25);driver.command_executor._client_config.timeout=30
  reviews.Browser=lambda prefix,session,coordinator=None:IsolatedBrowser(driver,coordinator)
  # Small local contract check before any expensive public traversal.
  driver.get('data:text/html,<input id="x"><button>OK</button>');check=IsolatedBrowser(driver);assert check.call('fill','#x','fixture')['verified'];assert check.call('eval','(async()=>({ok:true}))()')=={'ok':True};state['adapter_contract_check']='passed';state['phase']='crawling'
  for n,p in enumerate(queue,1):
   pid=str(p['product_id']);entry=state['products'].setdefault(pid,{'attempts':[],'detail_status':'pending','review_status':'pending'})
   if entry['detail_status']=='complete' and entry['review_status']=='complete':state['processed']=n;continue
   for attempt in range(args.attempts):
    if not driver.window_handles:raise RuntimeError('Owned virtual browser window closed; stopping instead of recording false access failures')
    def observe(b,product):
     # Original capture_detail -> original files/images/hashes, unchanged.
     if entry['detail_status']=='complete':return
     entry['detail_status']=capture_detail(b,product,out/'details')['status']
    report=reviews.crawl('https://www.coupang.com/vp/products/'+pid,out/'reviews'/pid,['isolated-chrome','143','uc3.5.5'],as_of,max_pages=args.max_pages,resume=(out/'reviews'/pid/'state.json').exists(),coordinator=reviews.CollectionCoordinator(0,'background'),navigation_query=(p.get('title') or p.get('group_name') or pid)[:150],detail_observer=observe,months_to_cover=1)
    report['navigation']='isolated local Chrome143; home search; exact observed product link; rendered reviews';atomic_json(out/'reviews'/pid/'report.json',report)
    metric=monthly_metrics(report);entry['monthly_metrics']=metric;entry['review_status']=metric['status'];entry['attempts'].append({'at_kst':dt.datetime.now(reviews.KST).isoformat(),'review_status':metric['status'],'error':report.get('coverage',{}).get('error')})
    trace=out/'reviews'/pid/'navigation.json'
    if trace.exists():shutil.copyfile(trace,trace.with_name('navigation-attempt-'+str(len(entry['attempts']))+'.json'))
    if any(marker in str(report.get('coverage',{}).get('error','')) for marker in ('NoSuchWindowException','InvalidSessionIdException','disconnected:','chrome not reachable')):raise RuntimeError('Owned virtual browser session lost; unfinished products remain unprocessed')
    if entry['review_status'] in ['complete','partial'] or entry['detail_status']=='complete':break
   state.update(processed=n,updated_at_kst=dt.datetime.now(reviews.KST).isoformat(),detail_complete=sum(x['detail_status']=='complete' for x in state['products'].values()),reviews_complete=sum(x['review_status']=='complete' for x in state['products'].values()),reviews_partial=sum(x['review_status']=='partial' for x in state['products'].values()));atomic_json(manifest,state);print(json.dumps({k:v for k,v in state.items() if k!='products'},ensure_ascii=False),flush=True)
 except Exception as exc:state['fatal_error']=type(exc).__name__+': '+str(exc)[:800]
 finally:
  reviews.Browser=OriginalBrowser
  if driver:
   try:driver.quit()
   except Exception as exc:state['cleanup_error']=str(exc)[:300]
  if display:
   try:display.__exit__(None,None,None);state['virtual_display_removed']=True
   except Exception as exc:state['display_cleanup_error']=str(exc)[:300]
  for _ in range(10):
   shutil.rmtree(profile,ignore_errors=True)
   if not Path(profile).exists():break
   time.sleep(.1)
  state.update(profile_removed=not Path(profile).exists(),finished_at_kst=dt.datetime.now(reviews.KST).isoformat(),elapsed_seconds=round(time.monotonic()-started,3));atomic_json(manifest,state)
 return 0 if state.get('reviews_complete',0)==len(queue) and state.get('detail_complete',0)==len(queue) else 3
if __name__=='__main__':raise SystemExit(main())
