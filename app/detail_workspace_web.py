"""Loopback-only persistent detail-page workspace HTTP interface."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit,parse_qs
from app.detail_workspace import Conflict

MAX_BODY=30000000

def handler(store,token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,code,value,typ='application/json; charset=utf-8',extra=None):
            raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            for k,v in (extra or {}).items():self.send_header(k,v)
            self.end_headers();self.wfile.write(raw)
        def host_ok(self):return self.headers.get('Host') in ['127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)]
        def do_GET(self):
            if not self.host_ok():return self.send(403,{'error':'로컬 주소로 접속하세요.'})
            path=urlsplit(self.path).path
            try:
                if path=='/':return self.send(200,Path(__file__).with_name('detail_workspace.html').read_bytes(),'text/html; charset=utf-8')
                if path=='/api/state':return self.send(200,{**store.state(),'csrf':token})
                if path=='/api/export.xlsx':return self.send(200,store.export("http://"+self.headers["Host"]),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',{'Content-Disposition':'attachment; filename="detail-workspace.xlsx"'})
                parts=path.strip('/').split('/')
                if len(parts)==3 and parts[:2]==['api','pages']:return self.send(200,store.get_page(parts[2]))
                if len(parts)==4 and parts[:2]==['api','pages'] and parts[3]=='handoff':return self.send(200,store.handoff(parts[2]))
                if len(parts)==3 and parts[0]=='pages' and parts[2]=='preview':
                    p=store.get_page(parts[1]);return self.send(200,p['html'].encode(),'text/html; charset=utf-8',{'Content-Security-Policy':"default-src 'none'; img-src data: https: http:; style-src 'unsafe-inline' https:; font-src data: https:; script-src 'none'; base-uri 'none'; form-action 'none'"})
                return self.send(404,{'error':'주소를 찾지 못했습니다.'})
            except ValueError as e:return self.send(400,{'error':str(e)})
        def do_POST(self):
            if not self.host_ok() or self.headers.get('X-CSRF-Token')!=token:return self.send(403,{'error':'저장 인증이 만료됐습니다. 새로고침하세요.'})
            origin=self.headers.get('Origin')
            if origin and origin not in ['http://127.0.0.1:'+str(self.server.server_port),'http://localhost:'+str(self.server.server_port)]:return self.send(403,{'error':'출처가 다른 요청입니다.'})
            try:
                n=int(self.headers.get('Content-Length','0'))
                if n<1 or n>MAX_BODY:return self.send(413,{'error':'파일 또는 요청이 너무 큽니다.'})
                data=json.loads(self.rfile.read(n));parts=urlsplit(self.path).path.strip('/').split('/')
                if parts==['api','products']:return self.send(201,{'id':store.add_product(data)})
                if len(parts)==3 and parts[:2]==['api','products']:return self.send(200,store.update_product(parts[2],data))
                if parts==['api','pages']:return self.send(201,store.add_page(data['product_id'],data))
                if len(parts)>=3 and parts[:2]==['api','pages']:
                    pid=parts[2]
                    if len(parts)==3:return self.send(200,store.save_page(pid,data))
                    if parts[3]=='requests':return self.send(201,store.request(pid,data))
                    if parts[3]=='apply':return self.send(200,store.apply(pid,data))
                    if parts[3]=='restore':return self.send(200,store.restore(pid,data))
                if parts==['api','import','preview']:return self.send(200,store.import_excel(base64.b64decode(data['file'],validate=True),data.get('sheet'),data.get('header_row'),data.get('mapping')))
                if parts==['api','import','commit']:return self.send(200,store.import_rows(data['rows']))
                return self.send(404,{'error':'주소를 찾지 못했습니다.'})
            except Conflict as e:return self.send(409,{'error':str(e)})
            except (ValueError,KeyError,TypeError) as e:return self.send(400,{'error':str(e)})
            except Exception:return self.send(500,{'error':'처리하지 못했습니다. 입력 파일과 서버 로그를 확인하세요.'})
    return Handler

def serve(store,port):
    server=ThreadingHTTPServer(('127.0.0.1',port),handler(store,secrets.token_urlsafe(32)));print('상세페이지 작업실 http://127.0.0.1:'+str(server.server_port),flush=True)
    server.serve_forever()
