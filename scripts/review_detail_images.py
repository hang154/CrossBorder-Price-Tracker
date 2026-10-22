#!/usr/bin/env python3
"""Local Qwen vision checks against immutable approved copy and product reference."""
import argparse,base64,hashlib,json,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.detail_studio import qwen,obj,string,array
from app.qwen_image_api import atomic

def review(folder,source=None):
    image=folder/'image.png';cutfile=folder/'cut.json';saved=folder/'qa.json'
    digest=hashlib.sha256(image.read_bytes()).hexdigest()
    lp=folder/'layout.json';layout=json.loads(lp.read_text()) if lp.exists() else None
    mode=layout['mode'] if layout else 'legacy-rendered-text'
    layout_sha=hashlib.sha256(lp.read_bytes()).hexdigest() if layout else None
    if saved.exists() and json.loads(saved.read_text()).get('image_sha256')==digest and json.loads(saved.read_text()).get('reference_comparison')==bool(source) and json.loads(saved.read_text()).get('mode','legacy-rendered-text')==mode and json.loads(saved.read_text()).get('layout_sha256')==layout_sha:return json.loads(saved.read_text())
    job=json.loads(cutfile.read_text());copy=job['cut']['이미지 내 삽입 문구']
    schema=obj({'visible_text':{'type':'string'},'missing_or_changed_phrases':array(string()),'unapproved_text':array(string()),'product_match':{'type':'boolean'},'readable':{'type':'boolean'},'pass':{'type':'boolean'},'notes':string()})
    if layout:
        schema=obj({'visible_text':string(),'unapproved_text':array(string()),'product_match':{'type':'boolean'},'blank_zones_clear':{'type':'boolean'},'pass':{'type':'boolean'},'notes':string()})
    data='data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode()
    content=[{'type':'text','text':json.dumps({'task':'Inspect this finished Korean product detail image. Transcribe every visible phrase verbatim. Compare with approved copy exactly; slash separators represent line breaks and may be omitted. Whitespace and typographic punctuation may differ. List missing/reworded phrases and added promotional text. Product intrinsic Chinese markings are not added advertising copy. Do not rewrite copy. Set pass true only if all approved phrases are present, no extra advertising labels, product matches description, and text readable. Korean output.','product':job['product_name'],'approved_copy':copy,'composition':job['cut']['이미지 구성']},ensure_ascii=False)},{'type':'image_url','image_url':{'url':data}}]
    if layout:
        zones=[{k:v for k,v in slot.items() if k!='text'} for slot in layout['slots']]
        content[0]['text']=json.dumps({'task':'Inspect a background-only Korean commerce image, not a finished text-composited cut. Added sales copy, placeholder bars and visible guide boxes are forbidden. Product intrinsic markings must remain. Check that reserved zones are clear low-detail areas with no product, person or ornament overlap. Missing sales copy is intentional and MUST NOT fail QA. Transcribe intrinsic marks separately; do not infer product facts. Korean output.','product':job['product_name'],'width':layout['width'],'height':layout['height'],'reserved_zones':zones},ensure_ascii=False)
    if source:
        from generate_detail_images import references
        from app.detail_studio import preview
        content.append({'type':'text','text':'The image above is the GENERATED OUTPUT (background-only if requested). Following images are product appearance references only, not output text. Compare product appearance against them.'})
        for reference in references(job,source,folder.parents[1]):content.append({'type':'image_url','image_url':{'url':preview(reference)}})
    result=qwen(folder/'qa-evidence','qa',[{'role':'user','content':content}],schema)
    result.update(image_sha256=digest,cut=job['job_id'],approved_copy=copy,qa_method='local_qwen_vision_not_human_certification',reference_comparison=bool(source),mode=mode,layout_sha256=layout_sha)
    if layout:
        result['missing_or_changed_phrases']=[];result['readable']=True
        if not result['blank_zones_clear']:result['pass']=False
    if result['missing_or_changed_phrases'] or result['unapproved_text'] or not result['product_match'] or not result['readable']:result['pass']=False
    atomic(saved,result);print(json.dumps({'cut':job['job_id'],'qa_pass':result['pass'],'issues':result['missing_or_changed_phrases']+result['unapproved_text']},ensure_ascii=False),flush=True);return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True,type=Path);p.add_argument('--workers',type=int,default=2);p.add_argument('--source',type=Path);a=p.parse_args()
    folders=sorted(p.parent for p in a.run.glob('*/*/image.png'))
    with ThreadPoolExecutor(max_workers=a.workers) as pool:results=list(pool.map(lambda folder:review(folder,a.source),folders))
    atomic(a.run/'qa-summary.json',{'reviewed':len(results),'passed':sum(r['pass'] for r in results),'results':results})
if __name__=='__main__':main()
