"""Deterministic text-layer editing: explicit patches, immutable assets, pinned HTML/PNG."""
import argparse,copy,fcntl,hashlib,html,json,mimetypes,os,re,secrets,shutil,time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,unquote

class Conflict(ValueError):pass

def digest(data):return hashlib.sha256(data).hexdigest()
def canonical(doc):return json.dumps(doc,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def revision(doc):return digest(canonical(doc))
def atomic(path,doc):
    path=Path(path);tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w') as f:json.dump(doc,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def identifier(s):
    if not isinstance(s,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',s):raise ValueError('Invalid ID')
    return s

def number(value,low,high):
    if type(value) not in (int,float) or not low<=value<=high:raise ValueError('Number outside allowed range')

def color(value):
    if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value):raise ValueError('Use #RRGGBB color')

def local(root,path):
    target=(root/path).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():raise ValueError('Asset must be inside project')
    return target

def validate(doc,root=None):
    if set(doc)!={'schema_version','width','height','fonts','assets','cuts'} or doc['schema_version']!=1:raise ValueError('Invalid project schema')
    for n in ['width','height']:
        if type(doc[n]) is not int:raise ValueError('Integer artboard dimensions required')
        number(doc[n],256,4096)
    if set(doc['fonts'])!={'regular','bold'}:raise ValueError('Two pinned fonts required')
    for asset in list(doc['assets'].values())+list(doc['fonts'].values()):
        if set(asset)!={'path','sha256'} or not re.fullmatch('[0-9a-f]{64}',asset['sha256']):raise ValueError('Invalid asset record')
        if not isinstance(asset['path'],str) or not re.fullmatch(r'assets/[A-Za-z0-9_.-]+',asset['path']):raise ValueError('Invalid asset path')
        if root and digest(local(root,asset['path']).read_bytes())!=asset['sha256']:raise ValueError('Asset SHA mismatch')
    seen=set()
    for c in doc['cuts']:
        if set(c)!={'id','name','approved_copy','background','background_color','masks','texts'}:raise ValueError('Invalid cut schema')
        identifier(c['id'])
        if c['id'] in seen:raise ValueError('Duplicate cut ID')
        seen.add(c['id']);color(c['background_color'])
        if not isinstance(c['name'],str) or not isinstance(c['approved_copy'],str):raise ValueError('Invalid cut text')
        if c['background'] is not None and c['background'] not in doc['assets']:raise ValueError('Unknown background')
        layerids=set()
        for layer,typ in [(m,'mask') for m in c['masks']]+[(t,'text') for t in c['texts']]:
            identifier(layer['id'])
            if layer['id'] in layerids:raise ValueError('Duplicate layer ID')
            layerids.add(layer['id'])
            expected={'id','x','y','width','height','color'}
            if typ=='text':expected|={'text','font_size','min_font_size','weight','align','line_height','auto_fit'}
            if set(layer)!=expected:raise ValueError('Unknown or missing layer field')
            for k,lim in [('x',doc['width']),('y',doc['height'])]:number(layer[k],0,lim)
            for k,lim in [('width',doc['width']),('height',doc['height'])]:number(layer[k],1,lim)
            if layer['x']+layer['width']>doc['width'] or layer['y']+layer['height']>doc['height']:raise ValueError('Layer outside artboard')
            color(layer['color'])
            if typ=='text':
                if not isinstance(layer['text'],str) or len(layer['text'])>5000 or '\x00' in layer['text']:raise ValueError('Invalid literal text')
                number(layer['font_size'],8,500);number(layer['min_font_size'],8,layer['font_size']);number(layer['line_height'],1,2)
                if layer['weight'] not in [400,700] or layer['align'] not in ['left','center','right'] or type(layer['auto_fit']) is not bool:raise ValueError('Invalid text style')
    return doc

@contextmanager
def locked(root):
    with (root/'.edit.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        yield

def read(project):return validate(json.loads(Path(project).read_text()),Path(project).parent)

def save_edit(project,doc,base,reason):
    project=Path(project);root=project.parent
    with locked(root):
        before=read(project)
        if revision(before)!=base:raise Conflict('Project changed; reload before saving')
        validate(doc,root);old=revision(before);new=revision(doc)
        (root/'versions').mkdir(exist_ok=True)
        if not (root/'versions'/f'{old}.json').exists():atomic(root/'versions'/f'{old}.json',before)
        atomic(project,doc)
        with (root/'edits.jsonl').open('a') as f:
            f.write(json.dumps({'at':time.time(),'before':old,'after':new,'reason':reason},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    return {'revision':new,'project':doc}

def apply(project,patch):
    if set(patch)!={'base_revision','operations'} or not isinstance(patch['operations'],list):raise ValueError('Invalid patch')
    doc=copy.deepcopy(read(project))
    for op in patch['operations']:
        if set(op)!={'cut_id','collection','action','id','value'}:raise ValueError('Invalid operation')
        cut=next(c for c in doc['cuts'] if c['id']==op['cut_id']);collection=op['collection'];action=op['action'];identifier(op['id'])
        if collection not in ['texts','masks'] or action not in ['add','replace','remove']:raise ValueError('Invalid operation target')
        items=cut[collection];index=next((i for i,item in enumerate(items) if item['id']==op['id']),None)
        if action=='add':
            if index is not None:raise ValueError('Layer exists')
            if op['value'].get('id')!=op['id']:raise ValueError('Layer ID mismatch')
            items.append(op['value'])
        elif action=='replace':
            if index is None or op['value'].get('id')!=op['id']:raise ValueError('Unknown layer or ID mismatch')
            items[index]=op['value']
        else:
            if index is None or op['value'] is not None:raise ValueError('Invalid removal')
            items.pop(index)
    return save_edit(project,doc,patch['base_revision'],'explicit patch')

def make_html(doc,cut,web=False):
    style='''html,body{margin:0;padding:0}*{box-sizing:border-box}#artboard{position:relative;overflow:hidden}.background{position:absolute;inset:0;width:100%;height:100%;object-fit:fill;user-select:none}.mask,.text{position:absolute}.text{font-family:LayerSans;white-space:pre-wrap;overflow-wrap:anywhere;word-break:keep-all;overflow:hidden;font-synthesis:none}'''
    for key,weight in [('regular',400),('bold',700)]:style+=f"@font-face{{font-family:LayerSans;src:url('{doc['fonts'][key]['path']}');font-weight:{weight};font-display:block}}"
    data=json.dumps({'doc':doc,'cut':cut},ensure_ascii=False).replace('<','\\u003c')
    runtime=Path(__file__).with_name('text_layer_runtime.js').read_text()
    return '<!doctype html><html lang="ko"><meta charset="utf-8">'+('<base href="/">' if web else '')+'<style>'+style+'</style><div id="artboard"></div><script>'+runtime+'</script><script>const input='+data+';window.TextLayers.mount(input.doc,input.cut).catch(e=>window.renderError=String(e));</script></html>'

def render(project,cut_id=None):
    from playwright.sync_api import sync_playwright
    project=Path(project).resolve();root=project.parent;doc=read(project);rev=revision(doc)
    cuts=[c for c in doc['cuts'] if not cut_id or c['id']==cut_id]
    if not cuts:raise ValueError('Unknown cut')
    out=root/'exports'/rev;out.mkdir(parents=True,exist_ok=True);receipts=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for cut in cuts:
            preview=root/f"preview-{cut['id']}-{rev[:12]}.html";preview.write_text(make_html(doc,cut))
            page=browser.new_page(viewport={'width':doc['width'],'height':doc['height']},device_scale_factor=1)
            page.goto(preview.as_uri());page.wait_for_function('window.renderResult?.ready || window.renderError')
            error=page.evaluate('window.renderError || null')
            if error:raise ValueError(error)
            metrics=page.evaluate('window.renderResult.metrics')
            if any(m['overflow'] for m in metrics):raise ValueError('Text overflow: adjust layer box/font before export')
            output=out/f"{cut['id']}.png";page.locator('#artboard').screenshot(path=str(output),animations='disabled')
            editable=root/f"editable-{cut['id']}-{rev[:12]}.html"
            snapshot=page.evaluate('''() => {let clone=document.documentElement.cloneNode(true);clone.querySelectorAll('script').forEach(s=>s.remove());return '<!doctype html>'+clone.outerHTML}''')
            editable.write_text(snapshot)
            record={'html':editable.name,'html_sha256':digest(editable.read_bytes()),'cut_id':cut['id'],'revision':rev,'file':output.relative_to(root).as_posix(),'png_sha256':digest(output.read_bytes()),'text_sha256':digest(canonical([m['text'] for m in metrics])),'metrics':metrics,'browser':browser.version,'fonts':doc['fonts']}
            atomic(output.with_suffix('.json'),record);receipts.append(record);page.close()
        browser.close()
    return receipts

def render_html(source,output):
    """Render an explicitly edited static HTML with local resources only."""
    from playwright.sync_api import sync_playwright
    from urllib.parse import unquote,urlsplit
    source,output=Path(source).resolve(),Path(output).resolve();root=source.parent;resources={}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page(device_scale_factor=1)
        def route(request):
            url=urlsplit(request.request.url)
            if url.scheme=='file':
                target=Path(unquote(url.path)).resolve()
                if target.is_relative_to(root) and target.is_file():
                    resources[str(target.relative_to(root))]=digest(target.read_bytes());return request.continue_()
            request.abort()
        page.route('**/*',route);page.goto(source.as_uri())
        if page.locator('script').count():raise ValueError('Static editable HTML must contain no scripts')
        page.evaluate("async()=>{await document.fonts.load('24px LayerSans','한글');await document.fonts.load('700 24px LayerSans','한글');await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode()));}")
        metrics=page.evaluate("() => [...document.querySelectorAll('.text')].map(e=>({text:e.textContent,overflow:e.scrollHeight>e.clientHeight+1||e.scrollWidth>e.clientWidth+1}))")
        if any(m['overflow'] for m in metrics):raise ValueError('Text overflow')
        bounds=page.locator('#artboard').bounding_box()
        if not bounds or not 256<=bounds['width']<=4096 or not 256<=bounds['height']<=4096:raise ValueError('Invalid artboard')
        if not page.evaluate("document.fonts.check('24px LayerSans','한글')"):raise ValueError('Pinned font did not load')
        output.parent.mkdir(parents=True,exist_ok=True);page.locator('#artboard').screenshot(path=str(output),animations='disabled')
        result={'html_sha256':digest(source.read_bytes()),'png_sha256':digest(output.read_bytes()),'resources':resources,'metrics':metrics,'browser':browser.version};browser.close()
    atomic(output.with_suffix('.json'),result);return result

def init(source,run,out,font_dir=None):
    source,run,out=map(Path,(source,run,out))
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True);(out/'assets').mkdir();fonts={}
    font_dir=Path(font_dir) if font_dir else Path('/usr/share/fonts/opentype/noto')
    for key,name in [('regular','NotoSansCJK-Regular.ttc'),('bold','NotoSansCJK-Bold.ttc')]:
        target=out/'assets'/name;shutil.copyfile(font_dir/name,target);fonts[key]={'path':'assets/'+name,'sha256':digest(target.read_bytes())}
    license=Path('/usr/share/doc/fonts-noto-cjk/copyright')
    if license.exists():shutil.copyfile(license,out/'assets/FONT-LICENSE.txt')
    doc={'schema_version':1,'width':1536,'height':2304,'fonts':fonts,'assets':{},'cuts':[]}
    for line in (source/'cut-jobs.jsonl').read_text().splitlines():
        if not line.strip():continue
        job=json.loads(line);identifier(job['job_id']);image=run/job['product_id']/job['job_id']/'image.png';target=out/'assets'/(job['job_id']+'.png');shutil.copyfile(image,target)
        doc['assets'][job['job_id']]={'path':'assets/'+target.name,'sha256':digest(target.read_bytes())}
        layout_path=run/job['product_id']/job['job_id']/'layout.json'
        texts=[]
        if layout_path.exists():
            from app.detail_layout import validate_layout,text_layers
            from PIL import Image
            with Image.open(target) as im:w,h=im.size
            if doc['cuts'] and (w,h)!=(doc['width'],doc['height']):raise ValueError('Mixed artboard dimensions')
            doc['width'],doc['height']=w,h
            texts=text_layers(validate_layout(json.loads(layout_path.read_text()),job,w,h))
            text_style=job.get('text_style',{})
            if set(text_style)-{'color'}:raise ValueError('Unsupported imported text style')
            for text in texts:text.update(text_style)
        doc['cuts'].append({'id':job['job_id'],'name':job['product_name'],'approved_copy':job['cut']['이미지 내 삽입 문구'],'background':job['job_id'],'background_color':'#ffffff','masks':[],'texts':texts})
    validate(doc,out);atomic(out/'project.json',doc);shutil.copyfile(source/'cut-jobs.jsonl',out/'original-cut-jobs.jsonl');return doc

def serve(project,port=8774):
    project=Path(project).resolve();root=project.parent;token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,status,data,mime='application/json; charset=utf-8'):
            raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
        def allowed(self):return self.headers.get('Host') in [f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}']
        def do_GET(self):
            if not self.allowed():return self.send(403,{'error':'Loopback host required'})
            path=unquote(urlsplit(self.path).path)
            try:
                if path=='/':return self.send(200,Path(__file__).with_name('text_edit_agent.html').read_bytes(),'text/html; charset=utf-8')
                if path=='/text-layer-controls.js':return self.send(200,Path(__file__).with_name('text_layer_controls.js').read_bytes(),'text/javascript; charset=utf-8')
                if path in ['/vendor/fabric-6.9.0.min.js','/vendor/fabric-LICENSE.txt','/vendor/fabric-provenance.json']:
                    f=Path(__file__).parent/path[1:];return self.send(200,f.read_bytes(),mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
                if path=='/api/project':
                    d=read(project);return self.send(200,{'project':d,'revision':revision(d),'token':token})
                if path.startswith('/preview/'):
                    d=read(project);c=next(c for c in d['cuts'] if c['id']==path.split('/')[-1]);return self.send(200,make_html(d,c,True).encode(),'text/html; charset=utf-8')
                if re.fullmatch(r'/editable-[A-Za-z0-9_-]+\.html',path):
                    return self.send(200,local(root,path[1:]).read_bytes(),'text/html; charset=utf-8')
                if path.startswith('/assets/') or path.startswith('/exports/'):
                    f=local(root,path.lstrip('/'));return self.send(200,f.read_bytes(),mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
                return self.send(404,{'error':'Not found'})
            except (ValueError,StopIteration):return self.send(400,{'error':'Invalid asset or cut'})
        def do_POST(self):
            if not self.allowed() or self.headers.get('X-Edit-Token')!=token:return self.send(403,{'error':'Reload editor to authenticate'})
            if self.headers.get('Origin') not in [None,f'http://{self.headers.get("Host")}']:return self.send(403,{'error':'Origin mismatch'})
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=4_000_000:raise ValueError('Invalid body size')
                body=json.loads(self.rfile.read(n));route=urlsplit(self.path).path
                if route=='/api/save':return self.send(200,save_edit(project,body['project'],body['base_revision'],'browser edit'))
                if route=='/api/apply':return self.send(200,apply(project,body))
                if route=='/api/render':return self.send(200,{'exports':render(project,body.get('cut_id'))})
                return self.send(404,{'error':'Not found'})
            except Conflict as e:return self.send(409,{'error':str(e)})
            except (ValueError,KeyError,TypeError,StopIteration) as e:return self.send(400,{'error':str(e)})
            except Exception as e:return self.send(500,{'error':type(e).__name__+': '+str(e)})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);print(f'문구 편집기 http://127.0.0.1:{server.server_port}',flush=True);server.serve_forever()

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('init');a.add_argument('--source',required=True,type=Path);a.add_argument('--run',required=True,type=Path);a.add_argument('--output-dir',required=True,type=Path);a.add_argument('--font-dir',type=Path)
    for cmd in ['inspect','apply','render','serve']:
        a=sub.add_parser(cmd);a.add_argument('--project',required=True,type=Path)
        if cmd=='apply':a.add_argument('--patch',required=True,type=Path)
        if cmd=='render':a.add_argument('--cut')
        if cmd=='serve':a.add_argument('--port',type=int,default=8774)
    a=sub.add_parser('render-html');a.add_argument('--html',required=True,type=Path);a.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.command=='render-html':print(json.dumps(render_html(a.html,a.output),ensure_ascii=False))
    elif a.command=='init':d=init(a.source,a.run,a.output_dir,a.font_dir);print(json.dumps({'cuts':len(d['cuts']),'revision':revision(d)}))
    elif a.command=='inspect':d=read(a.project);print(json.dumps({'revision':revision(d),'project':d},ensure_ascii=False,indent=2))
    elif a.command=='apply':print(json.dumps(apply(a.project,json.loads(a.patch.read_text())),ensure_ascii=False))
    elif a.command=='render':print(json.dumps(render(a.project,a.cut),ensure_ascii=False))
    else:serve(a.project,a.port)
if __name__=='__main__':main()
