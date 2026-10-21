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

NAVER_ROW={'product_id':'60325563982','item_url':'https://cr3.shopping.naver.com/v2/bridge/searchGate?nv_mid=60325563982',
           'source_url':'https://search.naver.com/search.naver?query=창문+필름','title':'무점착 창문 필름',
           'price_min':2400,'currency':'KRW','seller_name':'매장','shipping_fee':3000,'is_sponsored':False,
           'search_surface':'unified_search_shopping_section','strategy':'visible_dom'}

def test_naver_handoff_keeps_observed_identity_and_domestic_price():
    r=normalize_rows('naver',{'ok':True,'data':[NAVER_ROW,NAVER_ROW]})
    assert len(r)==1 and r[0]['price']==2400 and r[0]['currency']=='KRW'
    assert r[0]['shipping_fee']==3000 and r[0]['is_sponsored'] is False
    assert r[0]['price_scope']=='domestic_listing_shipping_not_included'
    assert r[0]['identical_product_verified'] is False

@pytest.mark.parametrize('change',[{'source_url':'https://search.naver.com.evil.test/search.naver?query=film'},
                                   {'product_id':'bad'}, {'item_url':'https://naver.com.evil.test/item/123'},
                                   {'source_url':'https://search.naver.com/search.naver'}])
def test_naver_rejects_forged_or_missing_search_provenance(change):
    with pytest.raises(ValueError):normalize_rows('naver',{'ok':True,'data':[{**NAVER_ROW,**change}]})

def test_combined_image_and_korean_query_jobs_are_separate(tmp_path):
    from argparse import Namespace
    from app.sourcing import commands
    a=Namespace(opencli_main=None,site='all',image=tmp_path/'product.jpg',query_ko='창문 필름',limit=5,naver_provider='browser')
    jobs=commands(a)
    assert len(jobs)==3 and jobs[0][1][2]=='image-search' and jobs[1][1][2]=='image-search'
    assert jobs[2][0]=='naver' and jobs[2][1][1:4]==['naver-shopping','search','창문 필름']

def test_naver_api_can_run_without_a_browser(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import json,sys
    from app.sourcing import main
    output=tmp_path/'naver.json';row={**NAVER_ROW,'strategy':'official_api',
        'source_url':'https://openapi.naver.com/v1/search/shop.json?query=film','item_url':'https://merchant.example/item/123'}
    monkeypatch.setattr(sys,'argv',['sourcing','run','--site','naver','--query-ko','필름','--naver-provider','api','--output',str(output)])
    def forbidden(_):raise AssertionError('API job must not require browser')
    monkeypatch.setattr('app.sourcing.browser_ready',forbidden)
    monkeypatch.setattr('app.sourcing.subprocess.run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,'data':[row]})))
    assert main()==0 and json.loads(output.read_text())['jobs'][0]['products'][0]['platform']=='naver'

def test_combined_image_run_does_not_require_image_hash_on_naver_keywords(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import json,sys
    from app.sourcing import main,image_provenance
    image=tmp_path/'product.png';image.write_bytes(bytes.fromhex('89504e470d0a1a0a'))
    output=tmp_path/'combined.json';sha=image_provenance(image)['sha256']
    def run(argv,**kw):
        row=(NAVER_ROW if 'naver-shopping' in argv else
             {**ROW,'item_url':'https://www.alibaba.com/product-detail/Film_1601234567890.html' if 'alibaba' in argv else ROW['item_url'],
              'search_type':'image','query_image_sha256':sha})
        return SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,'data':[row]}))
    monkeypatch.setattr(sys,'argv',['sourcing','run','--site','all','--image',str(image),'--query-ko','필름','--output',str(output)])
    monkeypatch.setattr('app.sourcing.browser_ready',lambda _:{'ready':True})
    monkeypatch.setattr('app.sourcing.subprocess.run',run)
    assert main()==0
    result=json.loads(output.read_text());assert result['search_type']=='image_and_keyword'
    assert [j['state'] for j in result['jobs']]==['collected']*3
