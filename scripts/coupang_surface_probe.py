#!/usr/bin/env python3
"""Probe every Coupang access surface and record which route is currently open.

Blocking is a rolling, per-surface decision (see ../app/coupang_fastpath.py and
reports/coupang-access-ladder-20261022/), so "is Coupang blocked right now"
needs a matrix, not one probe. Surfaces: plain HTTP (curl, httpx), TLS-
impersonated HTTP (curl_cffi over each exit interface), and the logged-in
browser via OpenCLI. Exit code 0 when at least one text surface returns real
data, 1 when only assets/canaries answer, 2 when everything denies.

Usage: python3 scripts/coupang_surface_probe.py [--out DIR] [--opencli dist/src/main.js]
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.coupang_fastpath import (CoupangFastPath, FastSession, HOME, ROBOTS,
                                  classify, is_expected, search_products)

KST = dt.timezone(dt.timedelta(hours=9))
DETAIL = 'https://www.coupang.com/vp/products/7318559460'
SEARCH = 'https://www.coupang.com/np/search?q=%EB%B6%80%EC%A0%81&channel=user&page=1'
MOBILE = 'https://m.coupang.com/vm/products/7318559460'
CDN = 'https://thumbnail.coupangcdn.com/thumbnails/remote/492x492ex/image/retail/images/2025-04-23/15/9/e73ee455-eddb-41b5-a7fb-5db8c4fbf126.png'

SNAP = r"""(() => ({url:location.href,title:document.title,
 blocked:/access denied|captcha|접속이.*제한/i.test(document.title+' '+(document.body?.innerText||'').slice(0,1000)),
 detail:!!document.querySelector('.product-detail-content'),
 cards:document.querySelectorAll('a[href*="/vp/products/"]').length}))()"""


def head(url):
    r = subprocess.run(['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', '20', url],
                       capture_output=True, text=True)
    return r.stdout.strip() or 'ERR'


def httpx_probe(url):
    import httpx
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as c:
            r = c.get(url, headers={'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                                 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'})
            return {'status': r.status_code, 'denied': 'Access Denied' in r.text[:3000]}
    except Exception as exc:
        return {'error': type(exc).__name__}


def fastpath(url, kind, iface=None):
    sess = FastSession(impersonate='chrome', interface=iface)
    try:
        code, body = sess.get(HOME)                      # warm
        time.sleep(1.5)
        code, body = sess.get(url, referer=HOME)
        cls = classify(code, body)
        return {'status': code, 'classification': cls, 'bytes': len(body),
                'expected': is_expected(kind, body) if cls == 'ready' else None}
    except Exception as exc:
        return {'error': type(exc).__name__}


def browser(url, opencli, session='probe'):
    cmd = ['node', str(opencli), 'browser', '--session', session, '--window', 'background']
    try:
        subprocess.run([*cmd, 'open', url], capture_output=True, timeout=90)
        time.sleep(4)
        r = subprocess.run([*cmd, 'eval', SNAP], capture_output=True, text=True, timeout=60)
        payload = json.loads(r.stdout)
        data = payload.get('data', payload)
        return {'status': 'blocked' if data.get('blocked') else 'ready',
                'title': data.get('title'), 'cards': data.get('cards', 0),
                'detail': data.get('detail', False)}
    except Exception as exc:
        return {'error': type(exc).__name__}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=None, help='report dir (default reports/coupang-surface-<date>)')
    ap.add_argument('--opencli', type=Path, default=Path('../OpenCLI/dist/src/main.js'))
    args = ap.parse_args()
    out = args.out or Path(f'reports/coupang-surface-{dt.datetime.now(KST):%Y%m%d-%H%M}')
    out.mkdir(parents=True, exist_ok=True)
    ifaces = [s.strip() for s in __import__('os').environ.get('COUPANG_FASTPATH_IFACES', '').split(',') if s.strip()]

    report = {'at_kst': dt.datetime.now(KST).isoformat(), 'surfaces': {}}
    surfaces = report['surfaces']
    surfaces['curl-h2'] = {name: head(u) for name, u in
                           [('robots', ROBOTS), ('home', HOME), ('detail', DETAIL), ('mobile', MOBILE)]}
    surfaces['httpx'] = {name: httpx_probe(u) for name, u in [('home', HOME), ('detail', DETAIL)]}
    surfaces['cdn-assets'] = httpx_probe(CDN)
    fp_report = {}
    for label, url, kind in [('robots', ROBOTS, 'home'), ('home', HOME, 'home'),
                             ('search', SEARCH, 'search'), ('detail', DETAIL, 'detail')]:
        for iface in [None] + ifaces:
            key = label + ('' if iface is None else '@' + iface)
            res = fastpath(url, kind, iface)
            if res.get('status') == 200:
                sess = FastSession(impersonate='chrome', interface=iface)
            fp_report[key] = res
            time.sleep(1.0)
    surfaces['curl_cffi'] = fp_report
    surfaces['browser'] = {name: browser(u, args.opencli) for name, u in
                           [('home', HOME), ('search', SEARCH), ('detail', DETAIL)]}

    text_ok = (any(v.get('classification') == 'ready' and v.get('expected') for v in surfaces['curl_cffi'].values())
               or any(v.get('status') == 'ready' for v in surfaces['browser'].values()))
    report['verdict'] = ('text-traffic-open' if text_ok
                         else 'browser-assets-only' if surfaces['cdn-assets'].get('status') == 200
                         else 'everything-denied')
    digest = {'sha256': hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()}
    (out/'surfaces.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    (out/'verdict.json').write_text(json.dumps({**digest, 'verdict': report['verdict'],
                                                'at_kst': report['at_kst']}, ensure_ascii=False))
    print(json.dumps({'verdict': report['verdict'],
                      'curl': surfaces['curl-h2'],
                      'curl_cffi': {k: (v.get('classification') or v.get('error')) for k, v in surfaces['curl_cffi'].items()},
                      'browser': {k: v.get('status', v) for k, v in surfaces['browser'].items()}},
                     ensure_ascii=False, indent=1))
    return 0 if report['verdict'] == 'text-traffic-open' else (1 if report['verdict'] == 'browser-assets-only' else 2)


if __name__ == '__main__':
    sys.exit(main())
