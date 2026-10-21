"""Browser regression for submitting and switching jobs without clobbering History."""
import json
from pathlib import Path

import pytest


def test_submit_and_switch_jobs_preserves_native_browser_history():
    playwright = pytest.importorskip('playwright.sync_api')
    html = (Path(__file__).parents[1]/'app/coupang_search.html').read_text()
    submitted = []
    errors = []
    ids = ['a'*32, 'b'*32]
    def route(request):
        path = request.request.url.split('ui.test', 1)[1].split('?', 1)[0]
        if path == '/':
            return request.fulfill(body=html, content_type='text/html')
        if path == '/api/bootstrap':
            data = {'csrf': 'fixture-token'}
        elif path == '/api/jobs' and request.request.method == 'POST':
            submitted.append(request.request.post_data_json)
            data = {'id': ids[1]}
        elif path == '/api/jobs':
            data = [{'id': ids[0], 'keyword': '이전 검색', 'status': 'complete'}]
        else:
            data = {'keyword': '새 검색' if path.endswith(ids[1]) else '이전 검색',
                    'status': 'complete', 'products': [], 'as_of_kst': '2026-10-21',
                    'max_pages_per_product': 100, 'model': 'fixture', 'events': []}
        request.fulfill(body=json.dumps(data), content_type='application/json')
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route('http://ui.test/**', route)
            page.goto('http://ui.test/')
            page.wait_for_selector('html[data-ready="true"]')
            page.wait_for_function("document.querySelector('#status').textContent.includes('이전 검색')")
            assert page.evaluate('typeof window.history.replaceState') == 'function'
            page.locator('#keyword').fill('새 검색')
            page.locator('#submit').click()
            page.wait_for_function("document.querySelector('#status').textContent.includes('새 검색')")
            assert submitted == [{'keyword': '새 검색', 'max_pages': 100}]
            assert page.url.endswith('?job='+ids[1])
            page.locator('#history').select_option(ids[0])
            page.wait_for_function("document.querySelector('#status').textContent.includes('이전 검색')")
            assert page.url.endswith('?job='+ids[0])
            assert page.evaluate('typeof window.history.replaceState') == 'function'
            assert page.locator('#error').text_content() == ''
            assert errors == []
        finally:
            browser.close()
