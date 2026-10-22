"""Fast-HTTP ladder tests against bodies captured live from Coupang on 2026-10-22.

see reports/coupang-access-ladder-20261022/ for the untruncated originals; fixtures/ are the
fixed matrices that covered every response shape we saw (edge 403, Akamai
behavioural interstitial served with 200, Coupang branded error with 200, and
real SSR page bodies). A passing run here proves routing/parsing logic, not
that the live edge currently answers; live state is reported by
COUPANG_FASTPATH_STATE + CoupangFastPath.status().
"""
import gzip
import json
from pathlib import Path

import pytest

from app import coupang_fastpath as fp

HERE = Path(__file__).parent
SEARCH_BODY = gzip.decompress((HERE/'fixtures/coupang-search-ssr-20261022.html.gz').read_bytes()).decode()
DETAIL_BODY = gzip.decompress((HERE/'fixtures/coupang-detail-shell-20261022.html.gz').read_bytes()).decode()

DENIED_EDGE = '<HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>\n<H1>Access Denied</H1>\n Reference #18.x </BODY></HTML>'
CHALLENGE = '<html><body><script src="/bo3/x"></script><div id="sec-if-cpt-container"></div></body></html>'
BRANDED = '<!DOCTYPE html><html><head><title>쿠팡!</title></head><body><div id="error403">x</div></body></html>'


class FakeTransport:
    """Programmable (status, body) queue per URL; counts requests per session."""
    def __init__(self, plans):
        self.plans = list(plans)
        self.calls = []
    def __call__(self, url, *, referer=None):
        self.calls.append(url)
        plan = self.plans.pop(0)
        return plan


def tmp_state(tmp_path):
    return str(tmp_path/'state.json')


def test_edge_denied_goes_to_next_surface(tmp_path):
    home = (200, '<html id="headerSearchKeyword"></html>')
    s1 = fp.FastSession(transport=lambda url, referer=None: (403, DENIED_EDGE), evidence=fp.EvidenceLog(None))
    s2 = fp.FastSession(transport=lambda url, referer=None: (200, DETAIL_BODY) if '/vp/' in url else (200, 'home'),
                        evidence=fp.EvidenceLog(None))
    path = fp.CoupangFastPath([s1, s2], evidence_path=tmp_path/'evid.jsonl', state_path=tmp_state(tmp_path), min_gap=0)
    body = path.detail_html('7318559460')
    assert 'id="itemBrief"' in body
    lines = [json.loads(l) for l in (tmp_path/'evid.jsonl').read_text().splitlines()]
    assert lines[0]['stage'] == 'warm'   # warm HOME probe leaves evidence too
    assert any(l['classification'] == 'edge_denied' and l['session'] == 'chrome' for l in lines)
    assert lines[-1]['classification'] == 'ready'


def test_challenge_response_refetch_once_same_session(tmp_path):
    seq = iter([(200, 'home headerSearchKeyword'), (200, CHALLENGE), (200, DETAIL_BODY)])
    seen = []
    def transport(url, *, referer=None):
        seen.append(url); return next(seq)
    s = fp.FastSession(transport=transport, evidence=fp.EvidenceLog(None))
    path = fp.CoupangFastPath([s], state_path=tmp_state(tmp_path), min_gap=0)
    assert 'id="itemBrief"' in path.detail_html('7318559460')
    assert seen == [fp.HOME,   # warm
                    'https://www.coupang.com/vp/products/7318559460',
                    'https://www.coupang.com/vp/products/7318559460']  # the single refetch


def test_exhaustion_raises_and_records(tmp_path):
    s = fp.FastSession(transport=lambda url, referer=None: (403, DENIED_EDGE), evidence=fp.EvidenceLog(None))
    path = fp.CoupangFastPath([s], state_path=tmp_state(tmp_path), min_gap=0)
    with pytest.raises(fp.FastPathUnavailable):
        path.detail_html('7318559460')


def test_branded_denied_treated_as_not_ready(tmp_path):
    s = fp.FastSession(transport=lambda url, referer=None: (200, BRANDED), evidence=fp.EvidenceLog(None))
    path = fp.CoupangFastPath([s], state_path=tmp_state(tmp_path), min_gap=0)
    with pytest.raises(fp.FastPathUnavailable):
        path.detail_html('7318559460')


def test_search_body_parses_captured_page():
    rows = fp.search_products(SEARCH_BODY)
    assert rows[0]['product_id'] == '9327328371' and rows[0]['rank'] == 1
    assert rows[0]['price'] == 15000 and rows[0]['url'].endswith('/vp/products/9327328371')
    assert all(r['product_id'].isdigit() and r['title'] for r in rows)


def test_detail_shell_contains_itemBrief_marker():
    assert fp.is_expected('detail', DETAIL_BODY)
    assert not fp.is_expected('detail', DENIED_EDGE)
    assert not fp.is_expected('detail', CHALLENGE)


def test_no_artificial_wait_between_surfaces(tmp_path, monkeypatch):
    import time as _t
    slept = []
    monkeypatch.setattr(_t, 'sleep', lambda s: slept.append(s))
    s = fp.FastSession(transport=lambda url, referer=None: (403, DENIED_EDGE), evidence=fp.EvidenceLog(None))
    path = fp.CoupangFastPath([s], state_path=tmp_state(tmp_path), min_gap=0)
    with pytest.raises(fp.FastPathUnavailable):
        path.detail_html('1')
    assert slept == []


def test_canary_uses_robots_and_marks_state(tmp_path):
    s = fp.FastSession(transport=lambda url, referer=None: (200, 'User-agent: *\nDisallow:\n'),
                       evidence=fp.EvidenceLog(None))
    path = fp.CoupangFastPath([s], state_path=tmp_state(tmp_path), min_gap=0)
    assert path.canary() is True
    st = json.loads(Path(tmp_state(tmp_path)).read_text())
    assert st['canary_status'] == 200


def test_default_refetch_has_no_sleep(tmp_path, monkeypatch):
    monkeypatch.setattr(fp.time, 'sleep', lambda _: pytest.fail('default must not sleep'))
    seq = iter([(200, 'headerSearchKeyword'), (200, CHALLENGE), (200, DETAIL_BODY)])
    session = fp.FastSession(transport=lambda url, referer=None: next(seq))
    path = fp.CoupangFastPath([session], state_path=tmp_state(tmp_path))
    assert path.detail_html('7318559460') == DETAIL_BODY


def test_robots_success_does_not_certify_search(tmp_path):
    session = fp.FastSession(transport=lambda url, referer=None: (200, 'User-agent: *'))
    state = fp.CoupangFastPath([session], state_path=tmp_state(tmp_path)).status()
    assert state['robots_available'] is True
    assert state['window_open'] is None


def test_robots_error_body_cannot_report_ready(tmp_path):
    session = fp.FastSession(transport=lambda url, referer=None: (403, 'user-agent: *'))
    assert fp.CoupangFastPath([session], state_path=tmp_state(tmp_path)).canary() is False
