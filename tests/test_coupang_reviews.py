import datetime as dt

import pytest

from app.coupang_reviews import KST, months_ago, summarize


def event(rid, day, user='person', text=True, identity='stable_public_id'):
    timestamp=dt.datetime.combine(day,dt.time(0,0),KST).timestamp()*1000
    return dict(review_id=rid,review_at=timestamp,created_at=timestamp,reviewer_key=user,
                identity_basis=identity,rating=5,has_text=text,has_media=False)


def complete():
    return dict(date_range_complete=True,rating_only_coverage='count_reconciled')


def test_calendar_months_clamp_leap_year():
    assert months_ago(dt.date(2024,3,31),1)==dt.date(2024,2,29)
    assert months_ago(dt.date(2026,1,31),3)==dt.date(2025,10,31)


def test_star_and_text_same_person_are_union_not_sum():
    day=dt.date(2026,10,21)
    reviews=[event('1',day),event('2',day,text=False),event('3',day,'second',False)]
    w=summarize(reviews,day,coverage=complete())['windows']['1']
    assert w['participants_observed_or_inferred']==2
    assert w['review_participants']==1 and w['rating_only_participants']==2
    assert w['both_kinds_participants']==1 and w['estimated_sales']==30


def test_inclusive_boundaries_kst_future_and_duplicate_pages():
    end=dt.date(2026,10,21)
    records=[event('1',dt.date(2026,9,21),'a'),event('2',dt.date(2026,9,20),'b'),
             event('3',dt.date(2026,7,21),'c'),event('4',dt.date(2026,7,20),'d'),
             event('5',dt.date(2026,10,22),'future')]
    result=summarize(records+[records[0]],end,coverage=complete())
    assert result['windows']['1']['participants_observed_or_inferred']==1
    assert result['windows']['3']['participants_observed_or_inferred']==3
    assert result['windows']['3']['estimated_sales']==45


def test_masked_names_and_missing_ids_are_not_claimed_exact_people():
    day=dt.date(2026,10,21)
    records=[event('1',day,'masked',identity='masked_signature'),event('2',day,None,identity='unknown')]
    w=summarize(records,day,coverage=complete())['windows']['1']
    assert w['participants_observed_or_inferred']==2 and w['estimated_sales']==30
    assert w['participant_count_is_exact'] is False and w['participants_exact_if_identifiable'] is None


def test_hidden_star_only_and_truncated_crawl_never_mark_complete():
    day=dt.date(2026,10,21)
    result=summarize([event('1',day)],day,coverage={'date_range_complete':True,'rating_only_coverage':'unknown'})
    assert result['windows']['1']['is_complete'] is False
    partial=summarize([event('1',day)],day,coverage={'date_range_complete':False,'rating_only_coverage':'count_reconciled'})
    assert partial['windows']['1']['is_complete'] is False
    assert partial['windows']['1']['estimated_sales']==15


def test_edited_review_keeps_display_and_created_basis_separate():
    day=dt.date(2026,10,21)
    r=event('1',dt.date(2026,7,1));r['review_at']=event('x',day)['review_at']
    assert summarize([r],day,date_basis='display')['windows']['1']['rating_or_review_events']==1
    assert summarize([r],day,date_basis='created')['windows']['1']['rating_or_review_events']==0
    assert summarize([r],day)['windows']['1']['rating_or_review_events']==0


@pytest.mark.parametrize('value',[0,-1,True,1.5])
def test_invalid_multiplier(value):
    with pytest.raises(ValueError):summarize([],dt.date(2026,10,21),value)


def test_options_use_item_id_and_keep_vendor_listings_separate():
    day=dt.date(2026,10,21)
    a=event('1',day,'same');a.update(item_id='red',vendor_item_id='shop-a',item_name='빨강 1개',vendor_name='A')
    b=event('2',day,'same',False);b.update(item_id='blue',vendor_item_id='shop-b',item_name='파랑 2개',vendor_name='B')
    c=event('3',day,'other');c.update(item_id='red',vendor_item_id='shop-c',item_name='빨강 1개',vendor_name='C')
    unknown=event('4',day,'unidentified')
    report=summarize([a,b,c,unknown],day,coverage=complete())
    groups={g['option_key']:g for g in report['option_groups']}
    assert report['windows']['1']['participants_observed_or_inferred']==3
    assert groups['item:red']['windows']['1']['participants_observed_or_inferred']==2
    assert groups['item:red']['windows']['1']['estimated_sales']==30
    assert len(groups['item:red']['vendor_items'])==2
    assert groups['item:blue']['windows']['1']['rating_only_events']==1
    assert groups['unknown']['option_label']=='옵션 미확인'


def test_page_cap_resume_selects_all_pages_and_completed_cache_skips_browser(tmp_path,monkeypatch):
    from app import coupang_reviews as audit
    calls=[]
    class FakeBrowser:
        def __init__(self,*args):pass
        def call(self,action,*args):calls.append(action)
        def wait(self,page):
            r=event(str(page),dt.date(2026,10,21),'person-'+str(page));r['product_id']='123'
            return dict(product_id='123',title='sample',records=[r],filters={},listed_review_count=2,
                        rating_count=2,total_pages=2,page=page)
        def next_page(self,page):calls.append(('next',page));return True
    monkeypatch.setattr(audit,'Browser',FakeBrowser)
    # These tests isolate pagination/cache behavior; native entry is covered
    # with actual DOM navigation in test_coupang_navigation.py.
    monkeypatch.setattr('app.coupang_navigation.home_search_detail', lambda *args, **kwargs: None)
    args=('https://www.coupang.com/vp/products/123',tmp_path,[],dt.date(2026,10,21))
    partial=audit.crawl(*args,max_pages=1)
    assert partial['coverage']['stop_reason']=='page_limit'
    assert ('next',2) not in calls
    finished=audit.crawl(*args,max_pages=2,resume=True)
    assert finished['coverage']['pages']==2 and finished['windows']['1']['estimated_sales']==30
    import json
    state=json.loads((tmp_path/'state.json').read_text())
    assert len(state['previous_attempts'][0]['pages'])==1
    calls.clear()
    assert audit.crawl(*args,max_pages=2,resume=True)==finished
    assert calls==[]
    (tmp_path/'attempt-002-page-00001.json').write_text('{}')
    with pytest.raises(ValueError,match='Cached page changed'):
        audit.crawl(*args,resume=True)


def test_creation_order_accepts_late_edit_display_date(monkeypatch):
    from app.coupang_reviews import Browser
    browser=Browser([],'fixture')
    older=event('old',dt.date(2025,1,1));older['review_at']=event('edit',dt.date(2026,10,21))['review_at']
    newer=event('new',dt.date(2026,9,1))
    monkeypatch.setattr(browser,'snapshot',lambda:dict(page=1,sort='DATE_DESC',querying=False,records=[newer,older]))
    assert browser.wait(1)['records']==[newer,older]


def test_old_creation_page_does_not_skip_recent_edits_in_display_mode(tmp_path,monkeypatch):
    from app import coupang_reviews as audit
    class FakeBrowser:
        def __init__(self,*args):pass
        def call(self,*args):pass
        def wait(self,page):
            r=event(str(page),dt.date(2025,1,3-page),'person-'+str(page));r['product_id']='123'
            r['review_at']=event('edit',dt.date(2026,10,21))['review_at']
            return dict(product_id='123',title='sample',records=[r],filters={},listed_review_count=2,
                        rating_count=2,total_pages=2,page=page)
        def next_page(self,page):return True
    monkeypatch.setattr(audit,'Browser',FakeBrowser)
    # These tests isolate pagination/cache behavior; native entry is covered
    # with actual DOM navigation in test_coupang_navigation.py.
    monkeypatch.setattr('app.coupang_navigation.home_search_detail', lambda *args, **kwargs: None)
    url='https://www.coupang.com/vp/products/123'
    created=audit.crawl(url,tmp_path/'created',[],dt.date(2026,10,21))
    display=audit.crawl(url,tmp_path/'display',[],dt.date(2026,10,21),date_basis='display')
    assert created['coverage']['stop_reason']=='three_month_boundary'
    assert created['windows']['1']['rating_or_review_events']==0
    assert display['coverage']['pages']==2
    assert display['windows']['1']['rating_or_review_events']==2


def test_undispatched_click_recovers_only_its_single_leased_tab(monkeypatch):
    import json
    import subprocess
    from app import coupang_reviews as audit
    calls=[]
    def run(argv,**kwargs):
        action=argv[1:3]
        calls.append(action)
        if len(calls)==1:
            return subprocess.CompletedProcess(argv,1,json.dumps({'ok':False,'error':{'message':'Native input requires a visible browser page; input was not dispatched.'}}),'')
        data=[{'page':'owned-tab'}] if action==['tab','list'] else {'clicked':True}
        return subprocess.CompletedProcess(argv,0,json.dumps({'ok':True,'data':data}),'')
    monkeypatch.setattr(audit.subprocess,'run',run)
    assert audit.Browser([],'fixture').call('click','#next')=={'clicked':True}
    assert calls==[['click','#next'],['tab','list'],['tab','select'],['click','#next']]


def test_parallel_native_input_activates_only_worker_tab_in_background(monkeypatch):
    import json
    import subprocess
    from app import coupang_reviews as audit
    calls = []
    def run(argv, **kwargs):
        assert argv[-2:] == ['--window', 'background']
        calls.append(argv[1:3])
        data = [{'page': 'worker-page', 'active': False}] if argv[1:3] == ['tab','list'] else True
        return subprocess.CompletedProcess(argv, 0, json.dumps({'ok':True,'data':data}), '')
    monkeypatch.setattr(audit.subprocess, 'run', run)
    coordinator = audit.CollectionCoordinator(0)
    browser = audit.Browser([], 'worker-session', coordinator)
    browser.call('click', '#next')
    assert calls == [['tab','list'],['tab','select'],['click','#next']]
    coordinator.stopped.set()
    with pytest.raises(ValueError, match='stopped'):
        browser.call('open', 'https://www.coupang.com/')
    browser.call('close')
