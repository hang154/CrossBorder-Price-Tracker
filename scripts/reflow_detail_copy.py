#!/usr/bin/env python3
"""Move approved copy onto separate solid panels; preserve pixels and all literal copy."""
import argparse,copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.text_edit_agent import read,revision,save_edit

def reflow(project):
 before=read(project);doc=copy.deepcopy(before);w,h=doc['width'],doc['height']
 for c in doc['cuts']:
  dark=all(t['color'].lower()=='#ffffff' for t in c['texts'])
  bg='#161616' if dark else '#faf8f3';fg='#ffffff' if dark else '#202820'
  c['masks']=[m for m in c['masks'] if not m['id'].startswith('copy-panel-')]
  c['masks'] += [{'id':'copy-panel-top','x':0,'y':0,'width':w,'height':round(h*.19),'color':bg},{'id':'copy-panel-bottom','x':0,'y':round(h*.82),'width':w,'height':h-round(h*.82),'color':bg}]
  n=max(1,len(c['texts'])-1)
  for i,t in enumerate(c['texts']):
   y=round(h*.055) if i==0 else round(h*(.835+(i-1)*.15/n))
   t.update(x=round(w*.07),y=y,width=round(w*.86),height=round(h*(.115 if i==0 else .14/n)),color=fg,font_size=68 if i==0 else 54,min_font_size=28,auto_fit=True)
  assert c['approved_copy']==before['cuts'][doc['cuts'].index(c)]['approved_copy']
 return save_edit(project,doc,revision(before),'Separate approved copy into opaque top/bottom panels; no copy or background pixel changes')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('project',type=Path);a=p.parse_args();print(reflow(a.project)['revision'])
