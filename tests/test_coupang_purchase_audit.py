import datetime as dt
from pathlib import Path
import json
from app.coupang_reviews import KST, summarize
from app.coupang_purchase_audit import monthly_metrics, queue_from_results, capture_detail


def record(rid,day,person='same',text=True):
 return dict(review_id=rid,created_at=dt.datetime.combine(day,dt.time(),KST).timestamp()*1000,review_at=dt.datetime.combine(day,dt.time(),KST).timestamp()*1000,reviewer_key=person,identity_basis='stable_public_id',has_text=text,has_media=False)


def test_review_id_multiplier_not_people_or_cumulative_count():
 day=dt.date(2026,10,23);r=record('a',day);s=record('b',day,text=False)
 report=summarize([r,r,s,record('old',dt.date(2025,1,1))],day,coverage=dict(pages=2,date_range_complete=True,rating_only_coverage='count_reconciled'))
 assert report['windows']['1']['estimated_sales']==15  # original participant model remains intact
 m=monthly_metrics(report)
 assert m['review_count']==2 and m['estimated_monthly_sales']==30
 assert m['text_media_reviews']==1 and m['rating_only_records']==1


def test_unavailable_is_null_never_zero():
 r=summarize([],dt.date(2026,10,23),coverage=dict(pages=0,date_range_complete=False))
 m=monthly_metrics(r);assert m['review_count'] is None and m['observed_review_sales_estimate'] is None
 assert m['estimated_monthly_sales'] is None and m['status']=='unavailable'


def test_partial_is_explicit_lower_bound_not_completed_month():
 day=dt.date(2026,10,23);r=summarize([record('a',day)],day,coverage=dict(pages=1,date_range_complete=False))
 m=monthly_metrics(r);assert m['observed_review_sales_estimate']==15 and m['estimated_monthly_sales'] is None
 assert m['status']=='partial'


def test_one_month_covered_does_not_require_three_months():
 day=dt.date(2026,10,23);r=summarize([record('a',day)],day,coverage=dict(pages=2,covered_months=1,date_range_complete=False,rating_only_coverage='count_reconciled'))
 assert monthly_metrics(r)['estimated_monthly_sales']==15


def test_wrong_product_detail_is_not_archived(tmp_path):
 class Browser:
  def call(self,action,*args):return False if action=='eval' and 'some(e' in args[0] else dict(product_id='999',detail_html='<p>wrong</p>')
 a=capture_detail(Browser(),'123',tmp_path)
 assert a['status']=='failed'
 assert not (tmp_path/'123'/'detail-original.html.txt').exists()


def test_detail_waits_for_expansion_before_archiving(tmp_path,monkeypatch):
 from app import coupang_purchase_audit as audit
 monkeypatch.setattr(audit.time,'sleep',lambda _:None)
 class Browser:
  extracted=0
  def call(self,action,*args):
   if action=='click':return None
   if args[0]!=audit.EXTRACT:return True
   self.extracted+=1;ready=self.extracted>=2
   return dict(product_id='123',expanded=ready,detail_html='<p>expanded</p>' if ready else '<p>collapsed</p>',detail_text='expanded' if ready else 'collapsed',detail_images=[])
 b=Browser();data=capture_detail(b,'123',tmp_path)
 assert b.extracted==2 and data['expanded'] is True
 assert (tmp_path/'123'/'description.txt').read_text()=='expanded'


def test_queue_deduplicates_domestic_products(tmp_path):
 p=tmp_path/'results.json';p.write_text(json.dumps({'items':[{'domestic':{'product_id':'1','title':'a'},'opportunity':{'overall_opportunity_score':5}},{'domestic':{'product_id':'1','title':'a'},'opportunity':{'overall_opportunity_score':20}}]}))
 q=queue_from_results(p);assert len(q)==1 and q[0]['opportunity_score']==20
 assert q[0]['estimated_monthly_sales'] is None


def test_monthly_join_keeps_missing_sales_and_profit_null(tmp_path):
 from app.coupang_purchase_audit import merge_monthly_opportunities,save_dashboard
 source=tmp_path/'source.json';source.write_text(json.dumps({'items':[{'pair_id':'a','domestic':{'product_id':'1','title':'상품','url':'https://www.coupang.com/vp/products/1'},'scenarios':{'base':{'estimated_profit':1000}},'quantity_verified':False}]}))
 queue=[dict(product_id='1',review_status='pending',detail_status='pending')]
 save_dashboard(tmp_path,queue,'2026-10-23');merge_monthly_opportunities(source,tmp_path,queue)
 row=json.loads((tmp_path/'opportunities-with-monthly.json').read_text())['items'][0]
 assert row['estimated_monthly_sales'] is None and row['conditional_monthly_contribution']['base'] is None


def test_one_month_boundary_and_detail_hook_share_same_visit(tmp_path,monkeypatch):
 from app import coupang_reviews as a
 calls=[];day=dt.date(2026,10,23)
 class Browser:
  def __init__(self,*args):pass
  def call(self,action,*args):calls.append(action)
  def wait(self,page):
   rows=[record('new',day),record('old',dt.date(2026,9,22))]
   for r in rows:r['product_id']='123'
   return dict(product_id='123',title='상품',records=rows,filters={},listed_review_count=4,rating_count=4,total_pages=2,page=1)
  def next_page(self,page):raise AssertionError('Month boundary already covered')
 monkeypatch.setattr(a,'Browser',Browser)
 monkeypatch.setattr('app.coupang_navigation.home_search_detail',lambda *args,**kwargs:calls.append('navigate'))
 result=a.crawl('https://www.coupang.com/vp/products/123',tmp_path,[],day,months_to_cover=1,detail_observer=lambda b,pid:calls.append('detail_snapshot'))
 assert calls[:3]==['navigate','detail_snapshot','click']
 assert result['coverage']['stop_reason']=='one_month_boundary'
 assert monthly_metrics(result)['estimated_monthly_sales']==15
 assert result['coverage']['date_range_complete'] is False


def test_list_count_mismatch_cannot_mark_month_complete(tmp_path,monkeypatch):
 from app import coupang_reviews as a
 day=dt.date(2026,10,23)
 class Browser:
  def __init__(self,*args):pass
  def call(self,*args):pass
  def wait(self,page):
   r=record('one',day);r['product_id']='123'
   return dict(product_id='123',title='商品',records=[r],filters={},listed_review_count=10,rating_count=10,total_pages=1,page=1)
 monkeypatch.setattr(a,'Browser',Browser)
 monkeypatch.setattr('app.coupang_navigation.home_search_detail',lambda *args,**kwargs:None)
 result=a.crawl('https://www.coupang.com/vp/products/123',tmp_path,[],day,months_to_cover=1)
 assert result['coverage']['covered_months']==0
 assert monthly_metrics(result)['estimated_monthly_sales'] is None


def test_confirmed_month_sales_feed_conditional_profit_and_rank(tmp_path):
 from app.coupang_purchase_audit import merge_monthly_opportunities,save_dashboard
 rows=[]
 for pid,profit in [('1',1000),('2',2000)]:rows.append(dict(pair_id=pid,eligible=True,domestic=dict(product_id=pid,title=pid,url='https://www.coupang.com/vp/products/'+pid),scenarios={'base':{'estimated_profit':profit}},quantity_verified=False))
 source=tmp_path/'source.json';source.write_text(json.dumps({'items':rows}))
 queue=[dict(product_id='1',review_status='complete',detail_status='complete',monthly_metrics={'review_count':10,'estimated_monthly_sales':150,'status':'complete'}),dict(product_id='2',review_status='complete',detail_status='complete',monthly_metrics={'review_count':20,'estimated_monthly_sales':300,'status':'complete'})]
 save_dashboard(tmp_path,queue,'2026-10-23');merge_monthly_opportunities(source,tmp_path,queue)
 a=json.loads((tmp_path/'opportunities-with-monthly.json').read_text())['items']
 assert [r['pair_id'] for r in a]==['2','1']
 assert a[0]['conditional_monthly_contribution']['base']==600000
 assert 'not forecast' in a[0]['monthly_estimate_scope']


def test_isolated_merge_requires_terminal_same_date_and_queue(tmp_path):
 import hashlib,pytest
 from app.coupang_purchase_audit import merge_isolated_audit
 queue=[dict(product_id='1',review_status='pending',detail_status='pending')]
 raw=json.dumps({'products':queue}).encode();(tmp_path/'queue.json').write_bytes(raw)
 folder=tmp_path/'isolated-audit';folder.mkdir()
 state=dict(source_sha256=hashlib.sha256(raw).hexdigest(),as_of='2026-10-23',products={})
 file=folder/'manifest.json';file.write_text(json.dumps(state))
 with pytest.raises(ValueError,match='not finished'):merge_isolated_audit(tmp_path,queue,'2026-10-23')
 state['finished_at_kst']='2026-10-23T04:00:00+09:00';file.write_text(json.dumps(state))
 with pytest.raises(ValueError,match='date mismatch'):merge_isolated_audit(tmp_path,queue,'2026-10-24')
 state['source_sha256']='wrong';file.write_text(json.dumps(state))
 with pytest.raises(ValueError,match='source queue mismatch'):merge_isolated_audit(tmp_path,queue,'2026-10-23')


def test_isolated_unavailable_stays_null_and_preserves_prior_success(tmp_path):
 import hashlib
 from app.coupang_purchase_audit import merge_isolated_audit
 queue=[dict(product_id='1',review_status='pending',detail_status='pending'),dict(product_id='2',review_status='complete',detail_status='complete',estimated_monthly_sales=150)]
 raw=json.dumps({'products':queue}).encode();(tmp_path/'queue.json').write_bytes(raw)
 folder=tmp_path/'isolated-audit';folder.mkdir()
 unavailable=monthly_metrics(summarize([],dt.date(2026,10,23),coverage=dict(pages=0)))
 entry=dict(attempts=[{'error':'Access restriction'}],detail_status='pending',monthly_metrics=unavailable)
 state=dict(finished_at_kst='2026-10-23T04:00:00+09:00',source_sha256=hashlib.sha256(raw).hexdigest(),as_of='2026-10-23',products={'1':entry,'2':entry})
 (folder/'manifest.json').write_text(json.dumps(state));merge_isolated_audit(tmp_path,queue,'2026-10-23')
 assert queue[0]['estimated_monthly_sales'] is None and queue[0]['review_status']=='unavailable'
 assert queue[0]['detail_status']=='not_reached' and queue[0]['isolated_browser_attempts']==1
 assert queue[1]['estimated_monthly_sales']==150 and queue[1]['detail_status']=='complete'


def test_merge_can_resume_after_report_write_but_rejects_price_change(tmp_path):
 import hashlib,pytest
 from app.coupang_purchase_audit import merge_isolated_audit,save_dashboard
 queue=[dict(product_id='1',title='상품',price=1000,review_status='pending',detail_status='pending')]
 raw=json.dumps({'as_of':'2026-10-23','products':queue}).encode();(tmp_path/'queue.json').write_bytes(raw)
 folder=tmp_path/'isolated-audit';folder.mkdir()
 metric=monthly_metrics(summarize([],dt.date(2026,10,23),coverage=dict(pages=0)))
 state=dict(finished_at_kst='2026-10-23T05:00:00+09:00',as_of='2026-10-23',source_sha256=hashlib.sha256(raw).hexdigest(),products={'1':dict(attempts=[{'error':'Access restriction'}],detail_status='pending',monthly_metrics=metric)})
 (folder/'manifest.json').write_text(json.dumps(state))
 merge_isolated_audit(tmp_path,queue,'2026-10-23');save_dashboard(tmp_path,queue,'2026-10-23')
 merge_isolated_audit(tmp_path,queue,'2026-10-23')
 assert queue[0]['review_status']=='unavailable' and queue[0]['estimated_monthly_sales'] is None
 queue[0]['price']=2000
 with pytest.raises(ValueError,match='source queue mismatch'):merge_isolated_audit(tmp_path,queue,'2026-10-23')
