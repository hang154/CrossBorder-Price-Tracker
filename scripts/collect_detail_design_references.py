#!/usr/bin/env python3
"""Archive portfolio indexes and selected full-page examples with source hashes."""
import argparse,hashlib,json,re,time
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
import httpx
from PIL import Image
class Page(HTMLParser):
 def __init__(self):super().__init__();self.links=[];self.images=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='a' and a.get('data-full'):self.links.append({'title':a.get('data-cap',''),'url':urljoin('https://www.patools.kr',a['data-full']),'id':a.get('data-pid')})
  if tag=='img':
   for key in ['data-original','data-src','src']:
    if a.get(key):self.images.append(a[key]);break
CATEGORIES=['health','food-beverage','agriculture','pet','electronics','living','sports-leisure','beauty','kids','fashion','education','etc']
def collect(out):
 out.mkdir(parents=True,exist_ok=True)
 def one(cat):
  folder=out/cat;folder.mkdir(exist_ok=True);url='https://www.patools.kr/dpa/ad.html?cat='+cat
  try:
   r=httpx.get(url,timeout=30,follow_redirects=True);r.raise_for_status();(folder/'index.html').write_bytes(r.content);p=Page();p.feed(r.text)
   records=[]
   for n,item in enumerate(p.links[:1]):
    response=httpx.get(item['url'],timeout=60,follow_redirects=True);response.raise_for_status();target=folder/'reference.jpg';target.write_bytes(response.content)
    with Image.open(target) as im:
     dims=list(im.size);tiles=[]
     # Actual long-page head/middle/tail; no claim of full small-text OCR.
     for i,ratio in enumerate([0,.5,1]):
      top=round(max(0,im.height-im.width*1.5)*ratio);tile=im.crop((0,top,im.width,min(im.height,top+round(im.width*1.5))));tile.thumbnail((800,1200));path=folder/f'view-{i}.jpg';tile.convert('RGB').save(path,quality=90);tiles.append(str(path.resolve()))
    records.append(dict(item,path=str(target.resolve()),sha256=hashlib.sha256(response.content).hexdigest(),dimensions=dims,views=tiles))
   row={'category':cat,'url':url,'status':'complete','index_sha256':hashlib.sha256(r.content).hexdigest(),'candidate_count':len(p.links),'candidates':p.links,'examples':records,'evidence_type':'design_observation','conversion_effect':'not_established','observed_at':time.time()}
  except Exception as exc:row={'category':cat,'url':url,'status':'failed','error':str(exc)}
  (folder/'manifest.json').write_text(json.dumps(row,ensure_ascii=False,indent=2));return row
 with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(one,CATEGORIES))
 # Keep the supplied domestic merchant example separately from design portfolios.
 url='https://oddniss.com/shop_view/?idx=14';folder=out/'oddniss';folder.mkdir(exist_ok=True)
 try:
  r=httpx.get(url,timeout=30,follow_redirects=True);r.raise_for_status();(folder/'original.html').write_bytes(r.content);p=Page();p.feed(r.text)
  images=list(dict.fromkeys(urljoin(url,u) for u in p.images if 'imweb.me' in u))
  row={'category':'beauty','url':url,'status':'complete','image_candidates':images,'index_sha256':hashlib.sha256(r.content).hexdigest(),'evidence_type':'seller_page','conversion_effect':'not_established'}
 except Exception as exc:row={'url':url,'status':'failed','error':str(exc)}
 (folder/'manifest.json').write_text(json.dumps(row,ensure_ascii=False,indent=2));rows.append(row)
 result={'sources':rows,'unresolved':[{'title':'食品详情页设计两套 / 电商设计Alice / ZCOOL','reason':'No verifiable direct source URL found; excluded from observed evidence'}]}
 (out/'references.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'indexes':sum(r['status']=='complete' for r in rows),'portfolio_examples':sum(len(r.get('examples',[])) for r in rows),'candidates':sum(r.get('candidate_count',0) for r in rows)}));return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();collect(a.output_dir)
