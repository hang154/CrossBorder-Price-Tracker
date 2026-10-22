"""Retry source-pinned Coupang products over the installed historical HTTP routes.

No artificial sleeps, proxies or CAPTCHA handling. HTTP 200 is insufficient:
validate the canonical product ID, BTF identity, and public review envelope.
This records independently obtained stage payloads; shell/BTF observations are
not full detail archives and first review pages are not complete monthly totals.
"""
import argparse
import datetime as dt
import gzip
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from urllib.parse import urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.coupang_fastpath import FastSession, HOME, classify, is_expected
from app.sourcing_pipeline import atomic_json

KST=dt.timezone(dt.timedelta(hours=9))

class Canonical(HTMLParser):
 def __init__(self):super().__init__();self.urls=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='link' and a.get('rel')=='canonical':self.urls.append(a.get('href',''))

def validate_payload(kind,body,product):
 pid=str(product['product_id'])
 if kind=='detail_shell':
  parser=Canonical();parser.feed(body)
  return is_expected('detail',body) and any(urlsplit(u).hostname=='www.coupang.com' and urlsplit(u).path.rstrip('/')=='/vp/products/'+pid for u in parser.urls)
 try:data=json.loads(body)
 except (ValueError,TypeError):return False
 if not isinstance(data,dict):return False
 if kind=='detail_btf':
  return all(str(data.get(k))==str(product.get(field)) for k,field in [('productId','product_id'),('itemId','item_id'),('vendorItemId','vendor_item_id')]) and bool(product.get('item_id')) and bool(product.get('vendor_item_id'))
 if kind=='reviews':
  if data.get('rCode')!='RET0000':return False
  payload=data.get('rData');paging=payload.get('paging') if isinstance(payload,dict) else None
  if not isinstance(paging,dict) or not isinstance(paging.get('contents'),list):return False
  # Empty error-like envelopes are not proof of a zero-review product.
  if not isinstance(paging.get('totalCount'),int) or isinstance(paging.get('totalCount'),bool):return False
  return all(str(r.get('productId'))==pid and r.get('reviewId') is not None for r in paging['contents'])
 return False

def public_review_projection(body):
 d=json.loads(body)['rData'];p=d['paging']
 return {'source':'public_next_api_review','paging':{k:p.get(k) for k in ['currentPage','page','totalPage','totalCount']},'ratingSummaryTotal':d.get('ratingSummaryTotal'),
 'records':[{k:r.get(k) for k in ['reviewId','productId','itemId','vendorItemId','createdAt','reviewAt','rating']}|{'has_text':bool((r.get('title') or '').strip() or (r.get('content') or '').strip()),'has_media':bool(r.get('attachments') or r.get('videoAttachments'))} for r in p['contents']]}

def stage_urls(p):
 pid=str(p['product_id']);url=p['url'];u=urlsplit(url)
 if u.scheme!='https' or u.hostname!='www.coupang.com' or u.path!='/vp/products/'+pid:raise ValueError('Source product URL mismatch')
 result=[('detail_shell',url)]
 if p.get('item_id') and p.get('vendor_item_id'):
  result.append(('detail_btf','https://www.coupang.com/next-api/products/btf?'+urlencode({'productId':pid,'vendorItemId':p['vendor_item_id'],'itemId':p['item_id']})))
 result.append(('reviews','https://www.coupang.com/next-api/review?'+urlencode({'productId':pid,'page':1,'size':10,'sortBy':'DATE_DESC','ratingSummary':'true','ratings':''})))
 return result

def run(queue_path,out,interfaces=(),rounds=1,limit=137,stage_names=None):
 out.mkdir(parents=True,exist_ok=True);products=json.loads(queue_path.read_text())['products'][:limit]
 manifest_path=out/'manifest.json';prior=json.loads(manifest_path.read_text()) if manifest_path.exists() else {};items=prior.get('items',{})
 profiles=[('chrome',None)]+[('chrome124',i) for i in interfaces]+[('chrome124',None)]+[('chrome',i) for i in interfaces]
 profiles=list(dict.fromkeys(profiles));sessions=[FastSession(impersonate=p,interface=i) for p,i in profiles];warmed=set();requests=0;started=dt.datetime.now(KST).isoformat()
 def evidence(row):
  nonlocal requests
  requests+=1;row['at_kst']=dt.datetime.now(KST).isoformat()
  with (out/'evidence.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
 def get(session,url,referer,kind,pid,round_no):
  try:
   code,body=session.get(url,referer=referer);row={'profile':session.name,'kind':kind,'product_id':pid,'round':round_no,'url':url,'http_status':code,'classification':classify(code,body),'bytes':len(body.encode()),'sha256':hashlib.sha256(body.encode()).hexdigest()};return row,body
  except Exception as e:return {'profile':session.name,'kind':kind,'product_id':pid,'round':round_no,'url':url,'classification':'transport_error','error':type(e).__name__+': '+str(e)},''
 for round_no in range(1,rounds+1):
  for n,p in enumerate(products,1):
   pid=str(p['product_id']);entry=items.setdefault(pid,{'product_id':pid,'stages':{}})
   for kind,url in stage_urls(p):
    if stage_names and kind not in stage_names:continue
    old=entry['stages'].get(kind,{})
    if old.get('status')=='observed':
     dest=out/old['file']
     if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest()==old['file_sha256']:continue
    stage={'status':'unavailable','attempts':[]}
    for session in sessions:
     if session.name not in warmed:
      row,body=get(session,HOME,None,'home',None,round_no);evidence(row);warmed.add(session.name)
     # One immediate same-session refetch only for the legacy transient classes.
     for attempt in range(2):
      row,body=get(session,url,HOME,kind,pid,round_no);valid=row.get('http_status')==200 and row.get('classification')=='ready' and validate_payload(kind,body,p)
      row['payload_valid']=valid;evidence(row);stage['attempts'].append({'profile':session.name,'http_status':row.get('http_status'),'classification':row['classification'],'payload_valid':valid})
      if valid:
       dest=out/pid/(kind+('.json' if kind in ['reviews','detail_btf'] else '.html.gz'));dest.parent.mkdir(exist_ok=True)
       if kind=='reviews':atomic_json(dest,public_review_projection(body))
       elif kind=='detail_btf':dest.write_text(body)
       else:dest.write_bytes(gzip.compress(body.encode()))
       stage.update(status='observed',profile=session.name,file=str(dest.relative_to(out)),file_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),source_body_sha256=row['sha256'],observed_at_kst=row['at_kst']);break
      if row['classification'] not in ['soft_challenge','branded_denied']:break
     if stage['status']=='observed':break
    if old:stage['previous']=old
    entry['stages'][kind]=stage
   summary={'started_at_kst':started,'updated_at_kst':dt.datetime.now(KST).isoformat(),'round':round_no,'processed_this_round':n,'products':len(products),'profiles':[s.name for s in sessions],'artificial_delay_seconds':0,'requests_this_execution':requests,'observed_stages':sum(s.get('status')=='observed' for e in items.values() for s in e['stages'].values()),'detail_archives_complete':0,'monthly_sales_complete':0,'items':items}
   atomic_json(manifest_path,summary)
   print(json.dumps({k:v for k,v in summary.items() if k!='items'},ensure_ascii=False),flush=True)
 summary['finished_at_kst']=dt.datetime.now(KST).isoformat();atomic_json(manifest_path,summary)
 return summary

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--queue',required=True,type=Path);ap.add_argument('--out',required=True,type=Path);ap.add_argument('--interfaces',default='');ap.add_argument('--rounds',type=int,choices=range(1,4),default=1);ap.add_argument('--max-products',type=int,default=137);ap.add_argument('--stages',nargs='+',choices=['detail_shell','detail_btf','reviews']);a=ap.parse_args()
 r=run(a.queue,a.out,tuple(x.strip() for x in a.interfaces.split(',') if x.strip()),a.rounds,a.max_products,set(a.stages) if a.stages else None)
 return 0 if r['observed_stages'] else 3
if __name__=='__main__':raise SystemExit(main())
