"""Local search UI and durable FIFO jobs for the Qwen Coupang agent."""
import argparse
import datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import secrets
import threading
from urllib.parse import urlsplit
import uuid

from app.coupang_search_agent import SearchAgent, now
from app.sourcing_pipeline import atomic_json, digest


class Jobs:
    def __init__(self, root, prefix, workers=2, start_interval=0.0, window_mode="background"):
        self.collection_options = dict(workers=workers, start_interval=start_interval, window_mode=window_mode)
        self.root, self.prefix = Path(root).resolve(), prefix
        self.root.mkdir(parents=True, exist_ok=True)
        self.queue, self.lock, self.pending = queue.Queue(), threading.Lock(), set()
        for path in self.root.glob('*/job.json'):
            state = json.loads(path.read_text())
            if state['status'] in ['queued', 'running']:
                state.update(status='interrupted', error='서버가 재시작되었습니다. 이어서 실행할 수 있습니다.')
                atomic_json(path, state)
        threading.Thread(target=self.worker, daemon=True).start()

    def folder(self, jid):
        if len(jid) != 32 or any(c not in '0123456789abcdef' for c in jid):
            raise ValueError('Invalid job ID')
        return self.root/jid

    def read(self, jid):
        folder=self.folder(jid)
        state=json.loads((folder/'job.json').read_text())
        for event in state.get('events',[]):
            if event.get('type')=='qwen_response' and 'reported_model' not in event:
                file=folder/Path(event['file']).name
                if file.exists():
                    response=json.loads(file.read_text())
                    if digest(response)==event['sha256']:
                        event.update(requested_model=state['model'],reported_model=response.get('model'))
        return state

    def submit(self, keyword, max_pages=100, jid=None):
        with self.lock:
            if jid in self.pending:
                raise ValueError('이미 실행 대기 또는 실행 중입니다.')
            if len(self.pending) >= 8:
                raise ValueError('작업 대기열이 찼습니다. 진행 중인 작업이 끝난 뒤 요청하세요.')
            if jid:
                saved = self.read(jid)
                if saved['status'] in ['queued', 'running']:
                    raise ValueError('아직 실행 중인 작업입니다.')
                if saved['status'] == 'complete':
                    raise ValueError('이미 완료된 작업입니다. 새 검색을 실행하세요.')
                keyword, day = saved['keyword'], dt.date.fromisoformat(saved['as_of_kst'])
            else:
                jid, day = uuid.uuid4().hex, None
            agent = SearchAgent(keyword, self.folder(jid), self.prefix, day, max_pages, resume=jid is not None and (self.folder(jid)/'job.json').exists(), **self.collection_options)
            agent.state['status'] = 'queued'
            agent.save()
            self.pending.add(jid)
            self.queue.put(jid)
            return jid

    def worker(self):
        while True:
            jid = self.queue.get()
            try:
                s = self.read(jid)
                SearchAgent(s['keyword'], self.folder(jid), self.prefix, dt.date.fromisoformat(s['as_of_kst']), s['max_pages_per_product'], True, **self.collection_options).run()
            except Exception as exc:
                s = self.read(jid)
                s.update(status='interrupted', error=type(exc).__name__+': '+str(exc), updated_at_kst=now())
                atomic_json(self.folder(jid)/'job.json', s)
            finally:
                with self.lock:
                    self.pending.discard(jid)
                self.queue.task_done()


def handler(jobs, csrf):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type='application/json; charset=utf-8'):
            raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(raw)

        def valid_host(self):
            return self.headers.get('Host') in ['127.0.0.1:'+str(self.server.server_port), 'localhost:'+str(self.server.server_port)]

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Local host required'})
            route = urlsplit(self.path).path
            try:
                if route == '/':
                    return self.send(200, Path(__file__).with_name('coupang_search.html').read_bytes(), 'text/html; charset=utf-8')
                if route == '/api/bootstrap':
                    return self.send(200, {'csrf': csrf, 'model': 'Qwen3.8-27B-uncensored-FP8'})
                if route == '/api/jobs':
                    rows = []
                    for path in sorted(jobs.root.glob('*/job.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
                        s = json.loads(path.read_text())
                        rows.append({'id': path.parent.name, **{k: s[k] for k in ['keyword', 'status', 'updated_at_kst']}})
                    return self.send(200, rows)
                parts = route.strip('/').split('/')
                if len(parts) == 3 and parts[:2] == ['api', 'jobs']:
                    return self.send(200, jobs.read(parts[2]))
                if len(parts) == 4 and parts[0] == 'reports' and parts[2].isdigit() and parts[3] == 'index.html':
                    file = jobs.folder(parts[1])/'products'/parts[2]/'index.html'
                    return self.send(200, file.read_bytes(), 'text/html; charset=utf-8')
                return self.send(404, {'error': 'Not found'})
            except (ValueError, FileNotFoundError):
                return self.send(404, {'error': 'Not found'})

        def do_POST(self):
            try:
                origin = self.headers.get('Origin')
                if not self.valid_host() or self.headers.get('X-CSRF-Token') != csrf or (origin and origin != 'http://'+self.headers['Host']):
                    return self.send(403, {'error': 'Local request token required'})
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096:
                    return self.send(400, {'error': 'Invalid body size'})
                body = json.loads(self.rfile.read(size))
                route = urlsplit(self.path).path.strip('/').split('/')
                if route == ['api', 'jobs']:
                    jid = jobs.submit(body['keyword'], body.get('max_pages', 100))
                elif len(route) == 4 and route[:2] == ['api', 'jobs'] and route[3] == 'resume':
                    jid = jobs.submit('', body.get('max_pages', 100), route[2])
                else:
                    return self.send(404, {'error': 'Not found'})
                return self.send(202, {'id': jid})
            except (ValueError, TypeError, KeyError, FileNotFoundError) as exc:
                return self.send(400, {'error': str(exc)})

        def log_message(self, fmt, *args):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--opencli-main', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=Path('sourcing-runs/coupang-search'))
    parser.add_argument('--port', type=int, default=8879)
    parser.add_argument('--workers', type=int, choices=range(1,5), default=2)
    parser.add_argument('--start-interval', type=float, default=0.0)
    parser.add_argument('--window-mode', choices=['background','foreground'], default='background')
    args = parser.parse_args()
    jobs = Jobs(args.output_dir, ['node', str(args.opencli_main.resolve())], args.workers, args.start_interval, args.window_mode)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(jobs, secrets.token_hex(24)))
    print('쿠팡 검색 UI: http://127.0.0.1:'+str(server.server_port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
