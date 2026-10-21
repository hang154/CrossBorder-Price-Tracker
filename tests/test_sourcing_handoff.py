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

def test_image_plan_uses_real_image_commands_for_both_sites(tmp_path):
    from argparse import Namespace
    from app.sourcing import commands,image_provenance
    image=tmp_path/'product.png';image.write_bytes(bytes.fromhex('89504e470d0a1a0a'))
    jobs=commands(Namespace(opencli_main=None,site='both',image=image,limit=5))
    assert len(jobs)==2 and all(argv[2]=='image-search' for _,argv in jobs)
    assert all(str(image) in argv for _,argv in jobs)
    assert image_provenance(image)['mime']=='image/png'
    assert len(image_provenance(image)['sha256'])==64

def test_renamed_nonimage_rejected(tmp_path):
    from app.sourcing import image_provenance
    image=tmp_path/'bad.jpg';image.write_text('not image')
    with pytest.raises(ValueError,match='signature'):image_provenance(image)

def test_image_handoff_preserves_hash():
    row={**ROW,'search_type':'image','query_image_sha256':'a'*64}
    result=normalize_rows('1688',{'ok':True,'data':[row]})[0]
    assert result['search_type']=='image' and result['query_image_sha256']=='a'*64

def test_run_rejects_unrelated_image_results(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import json,sys
    from app.sourcing import main
    image=tmp_path/'query.png';image.write_bytes(bytes.fromhex('89504e470d0a1a0a'))
    output=tmp_path/'result.json'
    monkeypatch.setattr(sys,'argv',['sourcing','run','--site','1688','--image',str(image),'--output',str(output)])
    monkeypatch.setattr('app.sourcing.browser_ready',lambda _: {'ready':True})
    monkeypatch.setattr('app.sourcing.subprocess.run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,'data':[ROW]})))
    assert main()==1
    assert json.loads(output.read_text())['jobs'][0]['state']=='blocked_or_failed'

def test_run_image_provenance_end_to_end_fake_bridge(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import json,sys
    from app.sourcing import main,image_provenance
    image=tmp_path/'query.png';image.write_bytes(bytes.fromhex('89504e470d0a1a0a'))
    output=tmp_path/'result.json'
    row={**ROW,'search_type':'image','query_image_sha256':image_provenance(image)['sha256']}
    monkeypatch.setattr(sys,'argv',['sourcing','run','--site','1688','--image',str(image),'--output',str(output)])
    monkeypatch.setattr('app.sourcing.browser_ready',lambda _: {'ready':True})
    monkeypatch.setattr('app.sourcing.subprocess.run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,'data':[row]})))
    assert main()==0
    result=json.loads(output.read_text());assert result['jobs'][0]['state']=='collected'
    assert result['query_image']['sha256']==row['query_image_sha256']
