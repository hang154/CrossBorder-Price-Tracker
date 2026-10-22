"""Akamai-aware fast HTTP path for Coupang pages, validated live on 2026-10-22.

Live evidence (see reports/coupang-access-ladder-20261022/evidence.jsonl and
the run logs stored there):

  * Plain curl/httpx fingerprints (no TLS impersonation) are edge-denied with
    AkamaiGHost 403 "Access Denied".
  * curl_cffi sessions impersonating Chrome, entered through HOME (warm),
    served the home page (221 KB), search pages and detail pages with 200
    while the very same IP denied curl, and re-served them minutes after a
    browser-session denial on that IP. Sustained bursts then re-denied both
    exit IPs — blocking here is a rolling rate window, not a permanent ban.
  * A 200 response can be an interstitial instead of the page: Akamai's
    behavioural challenge (``sec-if-cpt-container``, ~2.7 KB) or Coupang's
    branded error page (``id="error403"``, ~3.5 KB). Both must be treated as
    not-ready even though the HTTP status is 200.
  * ``/robots.txt`` stays 200 even while whole surfaces are edge-denied, so a
    cheap impersonated robots.txt GET is a safe liveness canary that does not
    re-trigger the challenge path.
  * ``coupangcdn.com`` image/asset URLs return 200 over plain httpx with no
    cookies — archived asset downloads never needed the fast path.
  * A second physical exit exists on this host (wired 175.121.6.111 via
    enp4s0, wifi 58.230.12.110 via wlo1). curl_cffi ``interface=`` rebinds
    the socket, and during a live test wifi served a 354 KB 200 detail page
    while the default surface was denied the same minute.

Design stance: blocking events mark observations; they never install a timed
cooldown (standing user decision of 2026-10-22). Every ladder step is an
immediate probe recorded with response evidence. When all fast surfaces are
denied the caller is told to use the browser entry; robots canaries report only robots availability; actual search/detail
responses are required to establish readiness.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import quote

HOME = 'https://www.coupang.com/'
ROBOTS = 'https://www.coupang.com/robots.txt'
CHALLENGE_MARKER = 'sec-if-cpt-container'
DENIED_MARKER = 'Access Denied'
STATE_DEFAULT = str(Path.home()/'.local/state/product-sourcing/coupang-fastpath.json')

# Expected-shape markers per surface. Any single marker is enough; missed
# expectations classify a 200 as unexpected-embedded (treated as not-ready).
# Verified against bodies captured in reports/coupang-access-ladder-20261022/.
# Verified against 2026-10-22 bodies: the SSR search page (title "쿠팡이 추천하는 …",
# 1.0 MB) embeds a schema.org CollectionPage with one ListItem per product and
# carries /vp/products/ links; the SSR detail shell (0.97 MB) always contains
# id="itemBrief"; the classic description fragment contains
# product-detail-content-inside. Chosen markers are heuristically unique to
# their surface (a denied/interstitial body contains none of them).
EXPECTS = {
    'search': ('/vp/products/', 'CollectionPage'),
    'detail': ('id="itemBrief"', 'product-detail-content-inside'),
    'home': ('headerSearchKeyword',),
}


class FastPathUnavailable(RuntimeError):
    """Raised when every surface is denied; use the browser entry instead."""


def classify(status: int, body: str) -> str:
    """Evidence-based response classes observed live at the Coupang edge."""
    if status == 403 and DENIED_MARKER in body[:600]:
        return 'edge_denied'                       # hard AkamaiGHost deny page
    if status in (429, 503):
        return 'rate_limited'
    if status == 200 and CHALLENGE_MARKER in body:
        return 'soft_challenge'                    # behavioural interstitial, 200
    if status == 200 and len(body) < 100_000 and ('id="error403"' in body or DENIED_MARKER in body):
        return 'branded_denied'                    # 쿠팡! error page served with 200
    if status == 200:
        return 'ready'
    return 'unknown'


def is_expected(kind: str, body: str) -> bool:
    return any(marker in body for marker in EXPECTS.get(kind, ()))


def default_surfaces(evidence=None):
    """Cheapest-first surface ladder: fingerprint x exit-interface combinations.

    The interface list is environment-specific so this keeps working on hosts
    without a second exit; set COUPANG_FASTPATH_IFACES=enp4s0,wlo1 here.
    """
    surfaces = [FastSession(impersonate='chrome', evidence=evidence)]
    for iface in [s.strip() for s in (os.environ.get('COUPANG_FASTPATH_IFACES') or '').split(',') if s.strip()]:
        surfaces.append(FastSession(impersonate='chrome124', interface=iface, evidence=evidence))
    surfaces.append(FastSession(impersonate='chrome124', evidence=evidence))
    return surfaces


class FastSession:
    """One cookie jar + TLS fingerprint + optional exit interface."""

    def __init__(self, *, impersonate='chrome', interface=None, transport=None, evidence=None):
        self.impersonate, self.interface = impersonate, interface
        self.evidence = evidence
        if transport is not None:
            self._get = transport
        else:
            from curl_cffi.requests import Session
            kwargs = {'impersonate': impersonate}
            if interface:
                kwargs['interface'] = interface
            session = Session(**kwargs)

            def get(url, *, referer=None):
                headers = {'accept-language': 'ko-KR,ko;q=0.9'}
                if referer:
                    headers['referer'] = referer
                r = session.get(url, headers=headers, timeout=30)
                return r.status_code, r.text
            self._get = get
        self.name = impersonate + (f'@{interface}' if interface else '')

    def get(self, url, *, referer=None):
        return self._get(url, referer=referer)


class CoupangFastPath:
    """Ladder: warm home -> request -> one same-session refetch for
    self-clearing classes -> next surface (fingerprint, then exit IP)."""

    def __init__(self, surfaces=None, *, evidence_path=None, warm_url=HOME, state_path=None,
                 clock=time.monotonic, min_gap=0.0):
        if surfaces is None:
            surfaces = default_surfaces(EvidenceLog(evidence_path))
        self.surfaces = list(surfaces)
        self.evidence = EvidenceLog(evidence_path)
        self.warm_url = warm_url
        self.state_path = Path(state_path or os.environ.get('COUPANG_FASTPATH_STATE', STATE_DEFAULT))
        self.clock, self.min_gap = clock, min_gap
        self._last_request = {}
        self.warmed = {}

    # -- bookkeeping -------------------------------------------------------
    def _state(self):
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {}

    def _update(self, **row):
        state = self._state()
        state.update(row)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=str(self.state_path.parent))
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(state, f)
        except Exception:
            os.unlink(name)
            raise
        os.replace(name, self.state_path)

    def status(self):
        state = self._state()
        state.update(robots_available=self.canary(), window_open=None,
                     canary_marker='robots-only-not-search-readiness')
        return state

    def canary(self):
        """Robots liveness only; this does not prove search/detail access."""
        code, body = self.surfaces[0].get(ROBOTS)
        ok = code == 200 and 'user-agent' in body.lower()
        self._update(canary_status=code, canary_at=time.time())
        return bool(ok)

    # -- ladder ------------------------------------------------------------
    def _pacing(self, sess):
        # Disabled by default. A caller can explicitly opt into pacing;
        # prior observations never impose an automatic cooldown.
        now = self.clock()
        gap = now - self._last_request.get(sess.name, 0)
        if self._last_request.get(sess.name) is not None and gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self._last_request[sess.name] = self.clock()

    def _log(self, **row):
        row.setdefault('at_utc', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
        if self.evidence.path:
            self.evidence.write(**row)

    def fetch(self, url, *, kind, surface_limit=4):
        for surface_no, sess in enumerate(self.surfaces[:surface_limit]):
            if sess.name not in self.warmed:              # entry discipline: HOME first
                wcode, wbody = sess.get(self.warm_url)
                self._log(session=sess.name, url=self.warm_url, stage='warm',
                          status=wcode, classification=classify(wcode, wbody), bytes=len(wbody))
                self.warmed[sess.name] = classify(wcode, wbody)
            for stage in ('first', 'refetch'):
                self._pacing(sess)
                code, body = sess.get(url, referer=self.warm_url)
                cls = classify(code, body)
                self._log(session=sess.name, url=url, stage=stage, surface=surface_no,
                          status=code, classification=cls, expected=is_expected(kind, body),
                          bytes=len(body),
                          body_sha256=hashlib.sha256(body.encode('utf-8', 'replace')).hexdigest())
                if cls == 'ready' and is_expected(kind, body):
                    self._update(ready_via=sess.name, last_surface_kind=kind)
                    return body
                if stage == 'first' and cls in ('edge_denied', 'rate_limited', 'unknown'):
                    break                                # re-request cannot clear these; next surface
                # soft_challenge / branded_denied: the sensor script in our own
                # warm home call may clear the embedded page; the single
                # same-session refetch decides, without any timed wait.
        self._log(url=url, stage='exhausted', classification='fastpath_exhausted')
        raise FastPathUnavailable('fast path exhausted for ' + url + '; use browser entry')

    # -- typed surfaces ----------------------------------------------------
    def detail_html(self, product_id):
        """SSR detail shell (title/brief/LD-JSON). Description body itself is a
        client-side fragment: fetch description_fragment() for full copy."""
        pid = str(product_id)
        if not pid.isdigit():
            raise ValueError('numeric product id required')
        return self.fetch(f'https://www.coupang.com/vp/products/{pid}', kind='detail')

    def description_fragment(self, product_id):
        pid = str(product_id)
        if not pid.isdigit():
            raise ValueError('numeric product id required')
        return self.fetch(f'https://www.coupang.com/vp/products/{pid}/description', kind='detail')

    def search_html(self, query, page=1):
        return self.fetch(f'https://www.coupang.com/np/search?q={quote(query)}&channel=user&page={int(page)}',
                          kind='search')


def search_products(search_html_body):
    """Parse the SSR search page's schema.org CollectionPage into job-JSON rows.

    Field-compatible with the existing pipeline input
    (``products:[{product_id,rank,title,price,url}]``), verified against the
    body captured 2026-10-22 (58 ListItems => 10/58 already used by adapters).
    Only data embedded in the observed page: no synthetic fields.
    """
    import re
    from urllib.parse import urlsplit
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', search_html_body, re.S)
    for raw in blocks:
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        main = doc.get('mainEntity') or {}
        items = main.get('itemListElement') if doc.get('@type') == 'CollectionPage' else None
        if not items:
            continue
        rows = []
        for entry in items:
            item = entry.get('item') or {}
            url = item.get('url') or ''
            match = re.match(r'https://(?:www\.)?coupang\.com/vp/products/(\d+)', url)
            if not match:
                continue
            offers = item.get('offers') or {}
            rating = item.get('aggregateRating') or {}
            try:
                price = int(float(offers.get('price'))) if offers.get('price') else None
            except ValueError:
                price = None
            rows.append({'rank': entry.get('position'), 'product_id': match.group(1),
                         'title': item.get('name'), 'price': price,
                         'rating': rating.get('ratingValue'), 'review_count': rating.get('reviewCount'),
                         'url': urlsplit(url)._replace(query='', fragment='').geturl()})
        if rows:
            return rows
    raise ValueError('no CollectionPage ItemList found in observed search body')


class EvidenceLog:
    """Append-only JSONL evidence: every ladder step leaves a replayable line."""

    def __init__(self, path=None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, **row):
        line = json.dumps(row, ensure_ascii=False) + '\n'
        if self.path:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
        return row
