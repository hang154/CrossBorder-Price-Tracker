#!/usr/bin/env python3
"""Archive public reference pages/images with provenance, never reuse as product photos."""
import argparse
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
from urllib.parse import urljoin,urlsplit
import httpx
from PIL import Image


class Page(HTMLParser):
    def __init__(self):super().__init__();self.images=[];self.links=[];self.text=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='img' and a.get('src'):self.images.append({'src':a['src'],'alt':a.get('alt','')})
        if tag=='a' and a.get('href'):self.links.append(a['href'])
    def handle_data(self,data):
        if data.strip():self.text.append(data.strip())


def archive(urls,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);records=[]
    with httpx.Client(timeout=25,follow_redirects=True) as client:
        for i,url in enumerate(urls):
            if urlsplit(url).scheme not in ('http','https'):raise ValueError('HTTP(S) only')
            response=client.get(url);page=Page();page.feed(response.text)
            file=out/f'{i:02d}.html';file.write_text(response.text)
            (out/f'{i:02d}.txt').write_text('\n'.join(page.text))
            record={'url':url,'http':response.status_code,'file':file.name,'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'images':[],'links':page.links,'purpose':'reference research; not product imagery or reusable templates'}
            selected=[x for x in page.images if any(s in x['alt'] for s in ['샘플','예시','실제 화면','타임라인','향수','고객 리뷰','블럭'])][:12]
            for j,item in enumerate(selected):
                image_url=urljoin(url,item['src']);item=dict(item,url=image_url)
                try:
                    r=client.get(image_url);r.raise_for_status()
                    with Image.open(io.BytesIO(r.content)) as image:
                        ext=image.format.lower();dest=out/f'{i:02d}-{j:02d}.{ext}';dest.write_bytes(r.content)
                        item.update(file=dest.name,sha256=hashlib.sha256(r.content).hexdigest(),dimensions=list(image.size))
                except Exception as e:item['error']=type(e).__name__
                record['images'].append(item)
            records.append(record)
            (out/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    return records

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('urls',nargs='+');a=p.parse_args()
    result=archive(a.urls,a.output);print(json.dumps([{'url':r['url'],'http':r['http'],'images':len(r['images'])} for r in result],ensure_ascii=False))
