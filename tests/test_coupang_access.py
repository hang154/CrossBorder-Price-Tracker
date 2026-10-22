import json
import pytest
from app.coupang_access import AccessGate, CoupangAccessError


def test_prior_block_does_not_delay_or_prevent_next_attempt(tmp_path):
    f=tmp_path/'s.json';f.write_text(json.dumps({'blocked_until':10**15,'last_action':10**15}))
    a=AccessGate(f,clock=lambda:1000)
    a.blocked('home')
    b=AccessGate(f,clock=lambda:1000)
    calls=[]
    with b.action('open',['https://www.coupang.com/']):calls.append('sent')
    with b.action('click',['#observed']):calls.append('clicked')
    assert calls==['sent','clicked']
    state=b.status();assert state['artificial_delay_seconds']==0
    assert state['cooldown_enabled'] is False and 'blocked_until' not in state
    assert f.stat().st_mode&0o777==0o600
    assert 'observed' not in f.read_text()


def test_home_only_entry(tmp_path):
    a=AccessGate(tmp_path/'s.json')
    for url in ['https://wing.coupang.com/','https://www.coupang.com/np/search?q=a','https://xauth.coupang.com/login']:
        with pytest.raises(CoupangAccessError):
            with a.action('open',[url]): pytest.fail()
    with a.action('open',['https://www.coupang.com/']):pass


def test_browser_records_denial_but_new_worker_can_try_immediately(tmp_path,monkeypatch):
    from app.coupang_reviews import Browser
    monkeypatch.setenv('COUPANG_ACCESS_STATE',str(tmp_path/'state.json'))
    calls=[]
    def transport(self,action,*args,**kwargs):
        calls.append(action)
        return {'title':'Access Denied','blocked':True} if action=='eval' else {'ok':True}
    monkeypatch.setattr(Browser,'_transport',transport)
    a=Browser(['node'],'coupang-one')
    with pytest.raises(CoupangAccessError):a.call('eval','state')
    b=Browser(['node'],'coupang-two');b.call('open','https://www.coupang.com/');b.call('close')
    assert calls==['eval','open','close']


def test_gated_undispatched_click_retries_only_once(tmp_path,monkeypatch):
    from app.coupang_reviews import Browser
    monkeypatch.setenv('COUPANG_ACCESS_STATE',str(tmp_path/'s.json'))
    calls=[]
    def run(self,action,*args,**kwargs):
        calls.append(action)
        if action=='click' and calls.count('click')==1:raise ValueError('input was not dispatched')
        if action=='tab' and args[0]=='list':return [{'page':'owned'}]
        return {'clicked':True}
    monkeypatch.setattr(Browser,'_transport',run)
    b=Browser(['node'],'coupang-retry')
    assert b.call('click','#observed')=={'clicked':True}
    assert calls==['click','tab','tab','click']
