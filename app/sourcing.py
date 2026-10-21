"""Read-only OpenCLI discovery handoff. Missing fields remain unknown."""
import argparse
import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
from app.models.product import detect_platform,extract_product_id

def normalize_rows(site,payload):
    if not isinstance(payload,dict) or payload.get('ok') is not True:
        raise ValueError('OpenCLI command failed: '+str(payload.get('error',{}) if isinstance(payload,dict) else 'invalid envelope'))
    rows=payload.get('data')
    if not isinstance(rows,list): raise ValueError('Expected OpenCLI result rows')
    result=[];seen=set()
    for row in rows:
        url=row.get('item_url','');pid=extract_product_id(url,site)
        if detect_platform(url)!=site or not pid: continue
        if pid in seen: continue
        seen.add(pid)
        price=row.get('price_min');currency=row.get('currency')
        known=isinstance(price,(int,float)) and not isinstance(price,bool) and math.isfinite(price) and price>0 and isinstance(currency,str) and len(currency)==3
        result.append({'platform':site,'product_id':pid,'url':url,'title':row.get('title'),
                       'price':price if known else None,'currency':currency if known else None,
                       'moq':row.get('moq_value'),'supplier':row.get('seller_name'),
                       'observed_at':row.get('fetched_at'),'source_url':row.get('source_url'),
                       'price_scope':'listing_not_landed_cost','identical_product_verified':False,
                       'raw_listing':row})
    if not result: raise ValueError('No valid source-linked product rows; not a successful discovery')
    return result

def commands(args):
    prefix=['node',str(Path(args.opencli_main).resolve())] if args.opencli_main else ['opencli']
    return [(site,[*prefix,site,'search',query,'--limit',str(args.limit),'-f','json'])
            for site,query in [('1688',args.query_zh),('alibaba',args.query_en)]]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['plan','run']);p.add_argument('--query-zh',required=True);p.add_argument('--query-en',required=True)
    p.add_argument('--limit',type=int,default=5);p.add_argument('--opencli-main');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not 1<=a.limit<=100:p.error('limit must be 1–100')
    report={'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'action':a.action,'jobs':[],'model_api_calls':0,'supplier_messages_sent':0}
    failed=False
    for site,argv in commands(a):
        job={'site':site,'argv':argv,'state':'prepared'}
        if a.action=='run':
            try:
                r=subprocess.run(argv,capture_output=True,text=True,timeout=120,check=False)
                job['exit_code']=r.returncode
                if r.returncode:raise ValueError('OpenCLI nonzero exit '+str(r.returncode))
                rows=normalize_rows(site,json.loads(r.stdout));job.update(state='collected',products=rows,
                    response_sha256=hashlib.sha256(r.stdout.encode()).hexdigest())
            except (ValueError,OSError,subprocess.TimeoutExpired) as e:
                job.update(state='blocked_or_failed',error=str(e));failed=True
        report['jobs'].append(job)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'jobs':[{'site':j['site'],'state':j['state']} for j in report['jobs']], 'output':str(a.output)}))
    return 1 if failed else 0
if __name__=='__main__':raise SystemExit(main())
