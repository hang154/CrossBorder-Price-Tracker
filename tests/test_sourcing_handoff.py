import pytest
from app.sourcing import normalize_rows
ROW={'item_url':'https://detail.1688.com/offer/123.html','price_min':2.4,'currency':'CNY','moq_value':2,'seller_name':'Supplier'}
def test_keeps_moq_supplier_and_raw_evidence():
    r=normalize_rows('1688',{'ok':True,'data':[ROW,ROW]});assert len(r)==1
    assert r[0]['moq']==2 and r[0]['supplier']=='Supplier' and r[0]['raw_listing']==ROW
@pytest.mark.parametrize('price',[None,0,-1,float('nan'),True])
def test_unknown_price_retained_as_product_but_not_price(price):
    r=normalize_rows('1688',{'ok':True,'data':[{**ROW,'price_min':price}]})
    assert r[0]['price'] is None and r[0]['currency'] is None
@pytest.mark.parametrize('payload',[{'ok':False,'error':{'code':'auth_required'}},{'ok':True,'data':[]},{'ok':True,'data':[{'item_url':'https://evil.test/offer/123.html'}]}])
def test_failure_not_marked_success(payload):
    with pytest.raises(ValueError):normalize_rows('1688',payload)

def test_bridge_check_does_not_confuse_doctor_exit_zero_with_connected(monkeypatch):
    from types import SimpleNamespace
    from app.sourcing import browser_ready
    monkeypatch.delenv('OPENCLI_CDP_ENDPOINT',raising=False)
    monkeypatch.setattr('app.sourcing.subprocess.run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout='{"ok":true,"data":{"extensionConnected":false}}'))
    assert browser_ready(['opencli'])['ready'] is False

def test_bridge_connection_is_detected(monkeypatch):
    from types import SimpleNamespace
    from app.sourcing import browser_ready
    monkeypatch.delenv('OPENCLI_CDP_ENDPOINT',raising=False)
    monkeypatch.setattr('app.sourcing.subprocess.run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout='{"ok":true,"data":{"extensionConnected":true}}'))
    assert browser_ready(['opencli'])['ready'] is True
