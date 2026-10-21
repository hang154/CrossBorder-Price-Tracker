"""Read-only OpenCLI discovery handoff. Missing fields remain unknown."""
import argparse
import datetime
import hashlib
import json
import math
import os
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
                       'search_type':row.get('search_type','keyword'),'query_image_sha256':row.get('query_image_sha256'),
                       'raw_listing':row})
    if not result: raise ValueError('No valid source-linked product rows; not a successful discovery')
    return result

def cli_prefix(args):
    return ['node',str(Path(args.opencli_main).resolve())] if args.opencli_main else ['opencli']

def commands(args):
    prefix=cli_prefix(args)
    sites=[getattr(args,'site','both')] if getattr(args,'site','both')!='both' else ['1688','alibaba']
    image=getattr(args,'image',None)
    return [(site,[*prefix,site,'image-search' if image else 'search',
                   str(Path(image).resolve()) if image else (args.query_zh if site=='1688' else args.query_en),
                   '--limit',str(args.limit),'-f','json']) for site in sites]

def image_provenance(path):
    path=Path(path).resolve()
    if not path.is_file() or path.stat().st_size>10*1024*1024:
        raise ValueError('image must be a regular file, at most 10 MiB')
    data=path.read_bytes()
    mime=('image/jpeg' if data.startswith(bytes.fromhex('ffd8ff')) else
          'image/png' if data.startswith(bytes.fromhex('89504e470d0a1a0a')) else
          'image/bmp' if data.startswith(b'BM') else
          'image/webp' if data[:4]==b'RIFF' and data[8:12]==b'WEBP' else None)
    extensions={'image/jpeg':{'.jpg','.jpeg'},'image/png':{'.png'},'image/bmp':{'.bmp'},'image/webp':{'.webp'}}
    if not mime or path.suffix.lower() not in extensions[mime]:
        raise ValueError('use a JPEG/PNG/BMP/WebP with matching signature and extension')
    return {'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'mime':mime}


def browser_ready(prefix):
    if os.environ.get('OPENCLI_CDP_ENDPOINT'):
        return {'ready':True,'method':'configured_cdp_not_yet_verified'}
    r=subprocess.run([*prefix,'doctor'],capture_output=True,text=True,timeout=20,check=False)
    try: data=json.loads(r.stdout).get('data',{})
    except ValueError: data={}
    return {'ready':r.returncode==0 and data.get('extensionConnected') is True,
            'method':'browser_bridge','extension_connected':data.get('extensionConnected',False)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['plan','run']);p.add_argument('--query-zh');p.add_argument('--query-en')
    p.add_argument('--image',type=Path,help='Upload this one local product image to the selected marketplace(s)')
    p.add_argument('--site',choices=['both','1688','alibaba'],default='both')
    p.add_argument('--limit',type=int,default=5);p.add_argument('--opencli-main');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not 1<=a.limit<=100:p.error('limit must be 1–100')
    if a.image and (a.query_zh or a.query_en):p.error('choose image search or keyword search; no implicit fallback')
    if not a.image and ((a.site in ('both','1688') and not a.query_zh) or (a.site in ('both','alibaba') and not a.query_en)):
        p.error('provide keywords for selected sites, or --image')
    try: image=image_provenance(a.image) if a.image else None
    except (ValueError,OSError) as e:p.error(str(e))
    report={'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'action':a.action,'search_type':'image' if image else 'keyword','query_image':image,'jobs':[],'model_api_calls':0,'supplier_messages_sent':0}
    failed=False
    jobs=commands(a);connection={'ready':True,'method':'not_needed_for_plan'}
    if a.action=='run':
        try: connection=browser_ready(cli_prefix(a))
        except (OSError,subprocess.TimeoutExpired) as e: connection={'ready':False,'error':type(e).__name__}
    report['browser_connection']=connection
    for site,argv in jobs:
        job={'site':site,'argv':argv,'state':'prepared'}
        if a.action=='run' and not connection['ready']:
            job.update(state='blocked_or_failed',error='Browser Bridge not connected; connect extension or configure existing CDP before retry');failed=True
        elif a.action=='run':
            try:
                r=subprocess.run(argv,capture_output=True,text=True,timeout=120,check=False)
                job['exit_code']=r.returncode
                if r.returncode:raise ValueError('OpenCLI nonzero exit '+str(r.returncode))
                rows=normalize_rows(site,json.loads(r.stdout))
                if image:
                    if image_provenance(a.image)!=image:raise ValueError('image changed during search')
                    if any(row['search_type']!='image' or row['query_image_sha256']!=image['sha256'] for row in rows):
                        raise ValueError('image query provenance missing/mismatched; refusing unrelated results')
                job.update(state='collected',products=rows,
                    response_sha256=hashlib.sha256(r.stdout.encode()).hexdigest())
            except (ValueError,OSError,subprocess.TimeoutExpired) as e:
                job.update(state='blocked_or_failed',error=str(e));failed=True
        report['jobs'].append(job)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'jobs':[{'site':j['site'],'state':j['state']} for j in report['jobs']], 'output':str(a.output)}))
    return 1 if failed else 0
if __name__=='__main__':raise SystemExit(main())
