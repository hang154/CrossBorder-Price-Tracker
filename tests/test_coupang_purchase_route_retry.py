import json
from scripts import coupang_purchase_route_retry as retry

P={'product_id':'123','item_id':'456','vendor_item_id':'789','url':'https://www.coupang.com/vp/products/123?itemId=456&vendorItemId=789'}

def test_shell_canonical_must_match_product():
 assert retry.validate_payload('detail_shell','<link rel="canonical" href="https://www.coupang.com/vp/products/123"><div id="itemBrief"></div>',P)
 assert not retry.validate_payload('detail_shell','<link rel="canonical" href="https://www.coupang.com/vp/products/999"><div id="itemBrief"></div>',P)

def test_btf_cannot_substitute_another_option():
 assert retry.validate_payload('detail_btf',json.dumps({'productId':123,'itemId':456,'vendorItemId':789}),P)
 assert not retry.validate_payload('detail_btf',json.dumps({'productId':123,'itemId':777,'vendorItemId':789}),P)

def test_review_error_and_other_product_not_valid():
 good={'rCode':'RET0000','rData':{'paging':{'totalCount':1,'contents':[{'reviewId':7,'productId':123}]}}}
 assert retry.validate_payload('reviews',json.dumps(good),P)
 good['rData']['paging']['contents'][0]['productId']=999
 assert not retry.validate_payload('reviews',json.dumps(good),P)
 assert not retry.validate_payload('reviews',json.dumps({'rCode':'ERROR','rData':{'paging':{'totalCount':0,'contents':[]}}}),P)

def test_saved_review_excludes_personal_fields():
 body=json.dumps({'rData':{'paging':{'currentPage':1,'totalCount':1,'contents':[{'reviewId':7,'productId':123,'createdAt':1,'member':{'name':'PRIVATE','email':'secret'},'content':'PRIVATE','title':'SECRET'}]}}})
 result=json.dumps(retry.public_review_projection(body))
 assert 'PRIVATE' not in result and 'secret' not in result and 'SECRET' not in result
 assert retry.public_review_projection(body)['records'][0]['has_text']

def test_transport_failure_keeps_next_route_and_saved_success(tmp_path,monkeypatch):
 class Fake:
  def __init__(self,impersonate,interface):self.name=impersonate+(('@'+interface) if interface else '')
  def get(self,url,referer=None):
   if self.name=='chrome':raise TimeoutError('test timeout')
   if url==retry.HOME:return 200,'headerSearchKeyword'
   return 200,'<link rel="canonical" href="https://www.coupang.com/vp/products/123"><div id="itemBrief"></div>'
 monkeypatch.setattr(retry,'FastSession',Fake)
 q=tmp_path/'q.json';q.write_text(json.dumps({'products':[P]}));out=tmp_path/'out'
 first=retry.run(q,out,stage_names={'detail_shell'})
 assert first['observed_stages']==1
 assert first['monthly_sales_complete']==first['detail_archives_complete']==0
 second=retry.run(q,out,stage_names={'detail_shell'})
 assert second['requests_this_execution']==0
 assert second['items']['123']['stages']['detail_shell']['profile']=='chrome124'

def test_stages_preserve_observed_listing_option_url():
 assert retry.stage_urls(P)[0][1]==P['url']
