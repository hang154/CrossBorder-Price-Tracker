#!/usr/bin/env python3
"""Import every tracked upstream file, retain MIT/provenance, index all text chunks."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
from html.parser import HTMLParser
class Text(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.skip=0
 def handle_starttag(self,tag,attrs):
  if tag in ['script','style']:self.skip+=1
 def handle_endtag(self,tag):
  if tag in ['script','style']:self.skip=max(0,self.skip-1)
 def handle_data(self,data):
  if not self.skip and data.strip():self.parts.append(data.strip())
def ingest(source,dest):
 commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
 files=subprocess.check_output(['git','-C',str(source),'ls-files','-z']).decode().split('\0');rows=[];chunks=[]
 for name in filter(None,files):
  p=source/name;target=dest/'upstream'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
  raw=p.read_bytes();record={'path':name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)};rows.append(record)
  if p.suffix in ['.md','.html','.json','.txt']:
   text=raw.decode('utf-8')
   if p.suffix=='.html':parser=Text();parser.feed(text);text='\n'.join(parser.parts)
   for n,start in enumerate(range(0,len(text),1200)):
    chunks.append({'id':f'{name}#{n}','path':name,'start_character':start,'text':text[start:start+1300],'source_sha256':record['sha256'],'evidence_type':'theory_or_design_example','conversion_effect':'not_established'})
 manifest={'upstream':'https://github.com/Banye0517/ecommerce-detail-page-skill','commit':commit,'license':'MIT','file_count':len(rows),'files':rows}
 for name,value in [('manifest.json',manifest),('chunks.json',chunks)]:
  (dest/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
 return manifest
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();r=ingest(a.source,a.output_dir);print(json.dumps({'files':r['file_count'],'commit':r['commit']}))
