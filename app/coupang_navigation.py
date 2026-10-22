"""Navigate through Coupang's visible home search and observed result links."""
import datetime as dt
import json
import re
import time
from urllib.parse import urlsplit, parse_qs

HOME = 'https://www.coupang.com/'
SNAPSHOT = r'''(() => ({url:location.href,title:document.title,
 blocked:/access denied|captcha|접속이.*제한/i.test(document.title+' '+(document.body?.innerText||'').slice(0,1000)),
 detail:!!document.querySelector('.product-detail-content')}))()'''
SEARCH_INPUT = r'''(() => {
 const e=[...document.querySelectorAll('input')].find(e =>
 e.getClientRects().length && !e.disabled &&
 (e.id==='headerSearchKeyword'||e.name==='q'||e.type==='search'||/검색/.test(e.placeholder)));
 if(!e)return null;
 e.setAttribute('data-detail-search','input');return {id:e.id,name:e.name};
})()'''


class NavigationError(ValueError):
    pass


def search_query(product, override='', keyword=''):
    query = (override or product.get('search_query') or product.get('search_keyword')
             or product.get('keyword') or next(iter(product.get('keywords') or []), '')
             or keyword or product.get('title') or '')
    if not isinstance(query, str) or not query.strip() or len(query) > 300:
        raise NavigationError('A nonempty search query (at most 300 characters) is required')
    return query.strip()


def home_search_results(browser, query, trace, *, polls=20, interval=.5):
    """Home -> visible search input -> actual submit click, never direct URLs."""
    if not isinstance(query, str) or not query.strip():
        raise NavigationError('Missing search query')
    def record(stage, **values):
        trace.append({'stage': stage, 'at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), **values})

    def snapshot(stage):
        for attempt in range(polls):
            try:
                state = browser.call('eval', SNAPSHOT)
                break
            except Exception as exc:
                # Navigation can invalidate a read; never repeat native input.
                if 'context was destroyed' not in str(exc).lower() or attempt == polls-1:
                    raise
                time.sleep(interval)
        record(stage, **state)
        u = urlsplit(state['url'])
        if u.scheme != 'https' or u.hostname not in ('coupang.com', 'www.coupang.com'):
            raise NavigationError('Unexpected navigation origin at '+stage)
        if state.get('blocked'):
            raise NavigationError('Access restriction detected at '+stage)
        return state

    browser.call('open', HOME)
    for _ in range(polls):
        snapshot('home')
        if browser.call('eval', SEARCH_INPUT):
            break
        time.sleep(interval)
    else:
        raise NavigationError('Home search input not found')
    # Activate only the tab leased to this worker before native keyboard input.
    tabs = browser.call('tab', 'list')
    if not isinstance(tabs, list) or len(tabs) != 1 or not tabs[0].get('page'):
        raise NavigationError('Cannot identify this worker tab safely')
    browser.call('tab', 'select', tabs[0]['page'])
    filled = browser.call('fill', 'input[data-detail-search="input"]', query)
    if not isinstance(filled, dict) or filled.get('verified') is not True:
        raise NavigationError('Search input value was not verified')
    submit = browser.call('eval', r'''(() => {
 const input=document.querySelector('input[data-detail-search="input"]');
 const button=input?.closest('form')?.querySelector('button[type="submit"], input[type="submit"]');
 if(!button || !button.getClientRects().length || button.disabled)return false;
 button.setAttribute('data-detail-search','submit');return true;
})()''')
    if submit is not True:
        raise NavigationError('Visible search submit button not found')
    browser.call('click', '[data-detail-search="submit"]')
    record('search_submitted', query=query)
    for _ in range(polls):
        state = snapshot('search_wait')
        if urlsplit(state['url']).path.startswith('/np/search') and parse_qs(urlsplit(state['url']).query).get('q') == [query]:
            break
        time.sleep(interval)
    else:
        raise NavigationError('Search submission did not reach results')
    return state


def home_search_detail(browser, product_id, query, trace, *, polls=20, interval=.5, scrolls=5):
    """Only HOME is opened. Search and detail navigation use native input/click.

    Caller holds the coordinator's native lock across this sequence. Trace is
    updated in-place so even a failed navigation can be archived by the caller.
    """
    product_id = str(product_id)
    if not re.fullmatch(r'\d+', product_id):
        raise NavigationError('Invalid product ID')
    if not isinstance(query, str) or not query.strip():
        raise NavigationError('Missing search query')

    def record(stage, **values):
        trace.append({'stage': stage, 'at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), **values})

    def snapshot(stage):
        for attempt in range(polls):
            try:
                state = browser.call('eval', SNAPSHOT)
                break
            except Exception as exc:
                # Navigation can invalidate a read; never repeat native input.
                if 'context was destroyed' not in str(exc).lower() or attempt == polls-1:
                    raise
                time.sleep(interval)
        record(stage, **state)
        u = urlsplit(state['url'])
        if u.scheme != 'https' or u.hostname not in ('coupang.com', 'www.coupang.com'):
            raise NavigationError('Unexpected navigation origin at '+stage)
        if state.get('blocked'):
            raise NavigationError('Access restriction detected at '+stage)
        return state

    record('start', product_id=product_id, query=query, entry_route='home-search')
    home_search_results(browser, query, trace, polls=polls, interval=interval)
    # Exact ID only: another result can never silently replace the requested item.
    find = r'''(() => {
 const id=__ID__;
 const a=[...document.querySelectorAll('a[href]')].find(a=>{
  try{const u=new URL(a.href);return ['www.coupang.com','coupang.com'].includes(u.hostname)&&u.protocol==='https:'&&u.pathname.match(/^\/vp\/products\/(\d+)\/?$/)?.[1]===id&&a.getClientRects().length;}catch{return false}
 });
 if(!a)return null;
 a.setAttribute('data-detail-result','target');a.scrollIntoView({block:'center'});
 // Retain actual href, including item/vendor IDs, but keep the leased tab.
 a.target='_self';return {href:a.href,text:a.innerText.slice(0,300)};
})()'''.replace('__ID__', json.dumps(product_id))
    match = None
    for scroll in range(scrolls+1):
        for _ in range(polls if scroll == 0 else 2):
            snapshot('results')
            match = browser.call('eval', find)
            if match:
                break
            time.sleep(interval)
        if match:
            break
        if scroll < scrolls:
            browser.call('scroll', 'down', '--amount', '800')
    if not match:
        raise NavigationError('Requested product not found in observed search results')
    record('result_selected', **match)
    browser.call('click', 'a[data-detail-result="target"]')
    for _ in range(polls):
        state = snapshot('detail_wait')
        actual = re.fullmatch(r'/vp/products/(\d+)/?', urlsplit(state['url']).path)
        if actual:
            if actual[1] != product_id:
                raise NavigationError('Clicked result opened a different product')
            if state.get('detail'):
                record('detail_verified', product_id=product_id, url=state['url'])
                return state
        time.sleep(interval)
    raise NavigationError('Requested detail content did not become ready')
