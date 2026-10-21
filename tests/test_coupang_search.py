import datetime as dt
import json
from pathlib import Path
import subprocess
import threading

import httpx
import pytest

from app import coupang_search_agent as agent
from app.coupang_reviews import summarize
from app.sourcing_pipeline import atomic_json


@pytest.fixture(autouse=True)
def no_stagger_in_unit_tests(monkeypatch):
    monkeypatch.setattr(agent, "DEFAULT_START_INTERVAL", 0)


def mock_runtime(monkeypatch, no_tool=False, partial=False):
    requests, audits = [], []
    native_client = httpx.Client
    def respond(request):
        body = json.loads(request.content)
        name = body['tools'][0]['function']['name']
        requests.append(name)
        msg = {'role': 'assistant', 'content': 'tool use' if no_tool else None}
        if not no_tool:
            msg['tool_calls'] = [{'id': 'call-'+name, 'type': 'function', 'function': {'name': name, 'arguments': '{}'}}]
        return httpx.Response(200, json={'choices': [{'message': msg, 'finish_reason': 'stop' if no_tool else 'tool_calls'}], 'usage': {'total_tokens': 30}})
    monkeypatch.setattr(agent.httpx, 'Client', lambda **kwargs: native_client(transport=httpx.MockTransport(respond)))
    rows = [{'product_id': str(i), 'rank': i, 'title': '상품 '+str(i), 'price': 1000, 'review_count': 20} for i in range(1, 12)]
    monkeypatch.setattr(agent.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess([], 0, json.dumps({'ok': True, 'data': rows}), ''))
    def crawl(url, out, prefix, day, multiplier, max_pages, resume=False, on_progress=None, **kwargs):
        out.mkdir(parents=True, exist_ok=True)
        if resume and (out/'state.json').exists() and json.loads((out/'state.json').read_text()).get('done'):
            return json.loads((out/'report.json').read_text())
        audits.append(url)
        on_progress({'page': 1, 'records': 0, 'total': 0})
        complete = not (partial and url.endswith('/3'))
        report = summarize([], day, coverage={'date_range_complete': complete, 'rating_only_coverage': 'count_reconciled'})
        report['finished_at_kst'] = agent.now()
        atomic_json(out/'report.json', report)
        atomic_json(out/'state.json', {'done': complete, 'pages': []})
        return report
    monkeypatch.setattr(agent, 'crawl', crawl)
    return requests, audits


def test_native_qwen_tools_search_then_all_ten_then_finish(tmp_path, monkeypatch):
    requests, audits = mock_runtime(monkeypatch)
    run = agent.SearchAgent('손저울', tmp_path, [], dt.date(2026, 10, 21))
    result = run.run({'Authorization': 'Bearer test'})
    assert result['status'] == 'complete'
    assert len(result['products']) == 10 and len(audits) == 10
    assert requests == ['search_products', 'audit_top_products', 'finish_search']
    assert all(p['analysis']['windows']['1']['sales_multiplier'] == 15 for p in result['products'])
    assert len(list(tmp_path.glob('qwen-response-*.json'))) == 3


def test_missing_model_tool_never_falls_back_to_fake_agent(tmp_path, monkeypatch):
    requests, audits = mock_runtime(monkeypatch, no_tool=True)
    result = agent.SearchAgent('손저울', tmp_path, []).run({'Authorization': 'Bearer test'})
    assert result['status'] == 'interrupted'
    assert len(requests) == 2 and audits == [] and result['products'] == []


def test_complete_resume_skips_model_and_crawler_and_rejects_changed_evidence(tmp_path, monkeypatch):
    requests, audits = mock_runtime(monkeypatch)
    agent.SearchAgent('손저울', tmp_path, []).run({'Authorization': 'Bearer test'})
    requests.clear(); audits.clear()
    assert agent.SearchAgent('손저울', tmp_path, [], resume=True).run()['status'] == 'complete'
    assert requests == [] and audits == []
    (tmp_path/'products/1/report.json').write_text('{}')
    with pytest.raises(ValueError, match='changed'):
        agent.SearchAgent('손저울', tmp_path, [], resume=True).run()


def test_partial_resume_reuses_nine_finished_products(tmp_path, monkeypatch):
    requests, audits = mock_runtime(monkeypatch, partial=True)
    assert agent.SearchAgent('손저울', tmp_path, []).run({'Authorization': 'Bearer test'})['status'] == 'partial'
    requests.clear(); audits.clear()
    result = agent.SearchAgent('손저울', tmp_path, [], max_pages=200, resume=True).run({'Authorization': 'Bearer test'})
    assert result['status'] == 'partial'
    assert requests == ['audit_top_products', 'finish_search']
    assert audits == ['https://www.coupang.com/vp/products/3']


@pytest.mark.parametrize('keyword', ['', 'x'*121, ['invalid'], 'test\ninput'])
def test_invalid_keyword_is_rejected(tmp_path, keyword):
    with pytest.raises(ValueError):
        agent.SearchAgent(keyword, tmp_path, [])


def test_http_submit_poll_security_and_static_route(tmp_path, monkeypatch):
    from app.coupang_search_web import Jobs, handler, ThreadingHTTPServer
    ready = threading.Event()
    def fake_run(self):
        self.state['status'] = 'complete'; self.save(); ready.set()
    monkeypatch.setattr(agent.SearchAgent, 'run', fake_run)
    jobs = Jobs(tmp_path, [])
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(jobs, 'test-token'))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        with httpx.Client(base_url='http://127.0.0.1:'+str(server.server_port), trust_env=False) as client:
            assert client.get('/').status_code == 200
            assert client.get('/api/bootstrap').json()['csrf'] == 'test-token'
            assert client.post('/api/jobs', json={'keyword': '손저울'}).status_code == 403
            assert client.post('/api/jobs', headers={'X-CSRF-Token': 'test-token', 'Origin': 'https://foreign.example'}, json={'keyword': '손저울'}).status_code == 403
            assert client.get('/api/jobs', headers={'Host': 'foreign.example'}).status_code == 403
            r = client.post('/api/jobs', headers={'X-CSRF-Token': 'test-token'}, json={'keyword': '손저울'})
            assert r.status_code == 202
            jid = r.json()['id']; assert ready.wait(5)
            assert client.get('/api/jobs/'+jid).json()['status'] == 'complete'
            assert client.get('/api/jobs').json()[0]['id'] == jid
            assert client.get('/reports/'+jid+'/../job.json').status_code == 404
            assert client.post('/api/jobs', headers={'X-CSRF-Token': 'test-token'}, json={'keyword': []}).status_code == 400
    finally:
        server.shutdown(); server.server_close(); thread.join(5)


def test_restart_marks_unfinished_jobs_interrupted(tmp_path):
    from app.coupang_search_web import Jobs
    folder = tmp_path/('a'*32)
    run = agent.SearchAgent('손저울', folder, [])
    run.state['status'] = 'running'; run.save()
    jobs = Jobs(tmp_path, [])
    assert jobs.read('a'*32)['status'] == 'interrupted'


def test_opening_resume_does_not_overwrite_live_checkpoint(tmp_path):
    active = agent.SearchAgent('손저울', tmp_path, [])
    active.state['status'] = 'running'; active.save()
    original = (tmp_path/'job.json').read_bytes()
    agent.SearchAgent('손저울', tmp_path, [], max_pages=200, resume=True)
    assert (tmp_path/'job.json').read_bytes() == original


def test_parallel_workers_overlap_and_keep_atomic_progress(tmp_path, monkeypatch):
    mock_runtime(monkeypatch)
    run = agent.SearchAgent('청바지', tmp_path, [], workers=2)
    run.search()
    original = agent.crawl
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    active = peak = 0
    def crawl(*args, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait(timeout=5)
        result = original(*args, **kwargs)
        with lock:
            active -= 1
        return result
    monkeypatch.setattr(agent, 'crawl', crawl)
    run.audit()
    saved = json.loads(run.path.read_text())
    assert peak == 2
    assert all(p['status'] == 'complete' for p in saved['products'])
    assert saved['collection']['workers'] == 2


def test_access_restriction_stops_remaining_products(tmp_path, monkeypatch):
    mock_runtime(monkeypatch)
    run = agent.SearchAgent('청바지', tmp_path, [], workers=1)
    run.search()
    original = agent.crawl
    calls = []
    def blocked(*args, **kwargs):
        calls.append(args[0])
        r = original(*args, **kwargs)
        r['coverage']['error'] = 'ValueError: Access restriction detected; collection stopped'
        return r
    monkeypatch.setattr(agent, 'crawl', blocked)
    run.audit()
    assert len(calls) == 1
    assert run.state['collection']['stopped_on_restriction']
    assert all(p['status'] == 'failed' for p in run.state['products'][1:])
