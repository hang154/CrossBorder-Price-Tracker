import pytest
from app.coupang_navigation import HOME, NavigationError, home_search_detail, search_query


class PageBrowser:
    def __init__(self, page):
        self.page, self.calls = page, []

    def call(self, action, *args):
        self.calls.append((action, *args))
        if action == 'open': return self.page.goto(args[0])
        if action == 'eval': return self.page.evaluate(args[0])
        if action == 'tab': return [{'page': 'owned', 'active': True}] if args[0] == 'list' else None
        if action == 'fill':
            self.page.locator(args[0]).fill(args[1])
            return {'verified': self.page.locator(args[0]).input_value() == args[1]}
        if action == 'keys': return self.page.keyboard.press(args[0])
        if action == 'click': return self.page.locator(args[0]).click()
        if action == 'scroll': return self.page.evaluate('window.scrollBy(0,800)')
        raise AssertionError(action)


@pytest.mark.parametrize('mode', ['success', 'missing', 'wrong', 'blocked', 'noinput'])
def test_home_search_native_navigation(mode):
    pw = pytest.importorskip('playwright.sync_api')
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            requests = []
            def serve(route):
                url = route.request.url
                requests.append(url)
                if '/vp/products/' in url:
                    body = '<h1>상품</h1><div class="product-detail-content">상세 이미지</div>'
                elif '/np/search' in url:
                    body = '<a target="_blank" href="/vp/products/123?itemId=42&amp;vendorItemId=99">부적</a>' if mode != 'missing' else '<a href="/vp/products/456">다른 상품</a>'
                    if mode == 'wrong':
                        body += '<script>document.querySelector("a").onclick=e=>{e.preventDefault();location.href="/vp/products/456"}</script>'
                elif mode == 'blocked': body = '<title>Access Denied</title>Access Denied'
                elif mode == 'noinput': body = '<h1>홈</h1>'
                else: body = '<form action="/np/search"><input id="headerSearchKeyword" name="q" placeholder="검색"><button type="submit">검색</button></form>'
                route.fulfill(body='<meta charset="utf-8">'+body, content_type='text/html; charset=utf-8')
            page.route('https://www.coupang.com/**', serve)
            b, trace = PageBrowser(page), []
            if mode == 'success':
                result = home_search_detail(b, '123', '부적 팔찌', trace, polls=2, interval=.01, scrolls=1)
                assert result['url'].endswith('123?itemId=42&vendorItemId=99')
                assert trace[-1]['stage'] == 'detail_verified'
                assert len(page.context.pages) == 1  # target=_blank stays in owned tab
                assert any('q=' in url for url in requests)
            else:
                with pytest.raises(NavigationError):
                    home_search_detail(b, '123', '부적', trace, polls=2, interval=.01, scrolls=1)
                assert not any(t['stage'] == 'detail_verified' for t in trace)
            assert [c for c in b.calls if c[0] == 'open'] == [('open', HOME)]
            if mode == 'missing': assert not any('/vp/products/' in url for url in requests)
            if mode == 'blocked': assert len(requests) == 1
        finally: browser.close()


def test_query_precedence():
    assert search_query({'keywords': ['부적']}, keyword='런 이름') == '부적'
    assert search_query({'keywords': ['부적']}, override='팔찌') == '팔찌'
    with pytest.raises(NavigationError): search_query({})


@pytest.mark.parametrize('blocked', [False, True])
def test_collector_connects_route_archives_trace_and_resumes(tmp_path, monkeypatch, blocked):
    import importlib.util
    import json
    from pathlib import Path
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location('detail_collector', Path(__file__).parents[1]/'scripts/coupang_detail_collect.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    source = tmp_path/'job.json'
    source.write_text(json.dumps({'products': [{'product_id': '123', 'keywords': ['부적']}]}))
    out = tmp_path/'archive'
    monkeypatch.setattr(mod, 'parse_args', lambda: SimpleNamespace(source=source, output_dir=out,
        opencli_main=tmp_path/'main.js', keyword='라벨', max=1, workers=1,
        search_query='', entry_route='home-search'))
    routes = []
    def route(browser, product_id, query, trace):
        routes.append((product_id, query))
        trace.append({'stage': 'home', 'blocked': blocked})
        if blocked: raise NavigationError('Access restriction detected at home')
    monkeypatch.setattr(mod, 'home_search_detail', route)
    class ArchiveBrowser:
        def __init__(self, *args): pass
        def call(self, action, *args):
            assert action != 'open'  # collector delegates entry exclusively to route
            if action == 'close': return None
            if args[0] == mod.EXTRACT:
                return {'product_id':'123', 'title':'부적', 'url':HOME+'vp/products/123',
                    'expanded':True, 'detail_html':'<p>원본 설명</p>', 'detail_text':'원본 설명',
                    'detail_images':[], 'main_image':None, 'selected_options':None,
                    'mandatory_information':None, 'price':None, 'currency':None}
            return {'blocked':False, 'detail':True, 'more':False}
    monkeypatch.setattr(mod, 'Browser', ArchiveBrowser)
    assert mod.main() == (1 if blocked else 0)
    saved = json.loads((out/'123/detail.json').read_text())
    assert saved['entry_route'] == 'home-search'
    assert saved['search_query'] == '부적'
    assert saved['status'] == ('failed' if blocked else 'partial')
    assert json.loads((out/'123/navigation.json').read_text())['trace'] == saved['navigation_trace']
    if not blocked:
        assert (out/'123/detail-original.html.txt').read_text() == '<p>원본 설명</p>'
        assert (out/'123/description.txt').read_text() == '원본 설명'
        assert mod.main() == 0
        assert routes == [('123', '부적')]  # completed/partial archive is reused
