import json
import pytest
from app import coupang_home_search as search

class Browser:
    def __init__(self, blocked=False): self.blocked=blocked; self.calls=[]
    def call(self, action, expression):
        self.calls.append((action,expression))
        if expression == search.SNAPSHOT:return {'blocked':self.blocked,'title':'검색','url':'https://www.coupang.com/np/search?q=x'}
        return {'domItems':[]}

def test_delayed_render_preserves_success_without_repeating_navigation(monkeypatch):
    results=iter(['[]',json.dumps([{'product_id':'123','title':'실리콘 문풍지'}])]);delays=[]
    monkeypatch.setattr(search.subprocess,'check_output',lambda *a,**k:next(results))
    monkeypatch.setattr(search.time,'sleep',lambda value:delays.append(value))
    browser=Browser();trace=[]
    rows=search.read_rendered_rows(browser,'eA==','normalize',trace,polls=3)
    assert rows[0]['product_id']=='123'
    assert [t['rows'] for t in trace]==[0,1]
    assert delays==[.25] and all(a=='eval' for a,_ in browser.calls)

def test_ready_results_have_zero_sleep(monkeypatch):
    monkeypatch.setattr(search.subprocess,'check_output',lambda *a,**k:'[{"product_id":"123"}]')
    monkeypatch.setattr(search.time,'sleep',lambda _:pytest.fail('ready DOM must not sleep'))
    assert search.read_rendered_rows(Browser(),'eA==','normalize',[])[0]['product_id']=='123'

def test_denied_page_stops_before_extractor(monkeypatch):
    monkeypatch.setattr(search.subprocess,'check_output',lambda *a,**k:pytest.fail('blocked page'))
    with pytest.raises(ValueError,match='Access restriction'):search.read_rendered_rows(Browser(True),'eA==','normalize',[])

def test_empty_result_never_becomes_success(monkeypatch):
    monkeypatch.setattr(search.subprocess,'check_output',lambda *a,**k:'[]')
    with pytest.raises(ValueError,match='No products observed'):search.read_rendered_rows(Browser(),'eA==','normalize',[],polls=2,interval=0)
