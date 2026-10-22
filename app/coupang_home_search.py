"""Use existing Chrome home navigation and the existing OpenCLI DOM extractor."""
import base64
import json
from pathlib import Path
import subprocess
import time
import uuid

from app.coupang_navigation import home_search_results, SNAPSHOT
from app.sourcing_pipeline import atomic_json


def search_products(prefix, keyword, trace_path):
    # Import lazily: Browser also supports detail/review callers.
    from app.coupang_reviews import Browser
    root = Path(prefix[-1]).resolve().parents[2]
    extractor = root/'clis/coupang/search.js'
    utils = root/'clis/coupang/utils.js'
    if not extractor.exists() or not utils.exists():
        raise ValueError('Existing OpenCLI Coupang adapter not found')
    b = Browser(prefix, 'coupang-home-search-'+uuid.uuid4().hex[:10])
    trace = []
    try:
        home_search_results(b, keyword, trace)
        # Only already-rendered DOM data: suppress the adapter's additional API
        # query. Keep its established parsing and normalization, including Unicode.
        expression = subprocess.check_output(['node', '--input-type=module', '-e',
            'import {buildSearchEvaluate} from '+json.dumps(extractor.as_uri())+';'
            'console.log(buildSearchEvaluate('+json.dumps(keyword)+',10,1)'
            ".replace('let items = await byApi();','let items = [];'));"], text=True)
        encoded = base64.b64encode(expression.encode()).decode()
        normalizer = ('import {sanitizeSearchItems,normalizeSearchItem} from '+json.dumps(utils.as_uri())+';'
            "let s='';for await(const c of process.stdin)s+=c;const r=JSON.parse(s);"
            'console.log(JSON.stringify(sanitizeSearchItems((r.domItems||[]).map(normalizeSearchItem),10)));')
        rows = read_rendered_rows(b, encoded, normalizer, trace)
        return {'ok':True,'data':rows,'entry_route':'home-search-visible-submit','extraction':'existing OpenCLI DOM only'}
    finally:
        atomic_json(Path(trace_path), trace)
        b.call('close')


def read_rendered_rows(browser, encoded, normalizer, trace, *, polls=20, interval=.25):
    """A changed URL may precede the rendered results; wait only on missing DOM."""
    expression = 'eval(new TextDecoder().decode(Uint8Array.from(atob('+json.dumps(encoded)+'),c=>c.charCodeAt(0))))'
    for attempt in range(polls):
        state = browser.call('eval', SNAPSHOT)
        if state.get('blocked'):
            raise ValueError('Access restriction detected while waiting for search results')
        raw = browser.call('eval', expression)
        rows = json.loads(subprocess.check_output(['node','--input-type=module','-e',normalizer], input=json.dumps(raw), text=True))
        trace.append({'stage':'result_extraction','attempt':attempt+1,'rows':len(rows),'title':state.get('title'),'url':state.get('url')})
        if rows:
            return rows
        if attempt+1 < polls:
            time.sleep(interval)  # DOM readiness only, never request pacing.
    raise ValueError('No products observed after actual home search and bounded DOM readiness checks')
