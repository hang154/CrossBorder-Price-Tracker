"""Local comparison gallery with persistent human choices; no model or image submissions."""
import argparse,functools,json,secrets,time
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from app.text_edit_agent import locked

def serve(root,port=8775):
 root=Path(root).resolve();token=secrets.token_urlsafe(24)
 class Handler(SimpleHTTPRequestHandler):
  def __init__(self,*args,**kw):super().__init__(*args,directory=str(root),**kw)
  def log_message(self,*args):pass
  def send_json(self,code,obj):
   data=json.dumps(obj,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
  def allowed(self):return self.headers.get('Host') in [f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}']
  def do_GET(self):
   if not self.allowed():return self.send_json(403,{'error':'Loopback host required'})
   if urlsplit(self.path).path=='/api/session':return self.send_json(200,{'token':token,'reviews':[json.loads(s) for s in (root/'human-reviews.jsonl').read_text().splitlines()] if (root/'human-reviews.jsonl').exists() else []})
   path=Path(self.translate_path(self.path)).resolve()
   if not path.is_relative_to(root) or path.is_dir() and path!=root:return self.send_json(403,{'error':'Invalid path'})
   return super().do_GET()
  def do_POST(self):
   if not self.allowed() or self.headers.get('X-Edit-Token')!=token or self.headers.get('Origin') not in [None,'http://'+self.headers.get('Host','')]:return self.send_json(403,{'error':'Reload comparison page'})
   if urlsplit(self.path).path!='/api/review':return self.send_json(404,{'error':'Not found'})
   try:
    n=int(self.headers.get('Content-Length','0'))
    if not 0<n<10000:raise ValueError('Invalid size')
    data=json.loads(self.rfile.read(n));grades=json.loads((root/'comparison.json').read_text())['grades'];grade=next(g for g in grades if g['job_id']==data['job_id'])
    if set(data)!={'job_id','score','selected','notes'} or type(data['score']) is not int or data['score'] not in range(1,6) or type(data['selected']) is not bool or not isinstance(data['notes'],str) or len(data['notes'])>2000:raise ValueError('Invalid review')
    data.update(product_id=grade['product_id'],method_id=grade['method_id'],png_sha256=grade['png_sha256'],reviewed_at=time.time())
    with locked(root):
     with (root/'human-reviews.jsonl').open('a') as f:f.write(json.dumps(data,ensure_ascii=False)+'\n')
    return self.send_json(200,{'saved':True})
   except (ValueError,KeyError,StopIteration):return self.send_json(400,{'error':'Invalid review'})
 server=ThreadingHTTPServer(('127.0.0.1',port),Handler);print(f'스타일 비교 http://127.0.0.1:{server.server_port}',flush=True);server.serve_forever()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--port',type=int,default=8775);a=p.parse_args();serve(a.root,a.port)
