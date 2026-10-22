"""Browse dated Coupang rating/review pages and estimate sales with an explicit multiplier."""
import argparse
import calendar
import datetime as dt
import fcntl
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import time
import threading
import uuid
from urllib.parse import urlsplit

from app.sourcing_pipeline import atomic_json, digest
from app.coupang_access import AccessGate, CoupangAccessError

KST = dt.timezone(dt.timedelta(hours=9))


def months_ago(day, months):
    year, month = divmod(day.year*12+day.month-1-months, 12)
    return dt.date(year, month+1, min(day.day, calendar.monthrange(year, month+1)[1]))


def record_date(record, basis):
    value = record.get('created_at' if basis == 'created' else 'review_at')
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        return dt.datetime.fromtimestamp(value/1000, KST).date()
    except (ValueError, OSError, OverflowError):
        return None


def summarize(records, as_of, multiplier=15, coverage=None, date_basis='created', _with_options=True):
    if not isinstance(multiplier, int) or isinstance(multiplier, bool) or multiplier <= 0:
        raise ValueError('Positive integer multiplier required')
    unique = {}
    for record in records:
        rid = record.get('review_id')
        if not rid or rid in ['None','undefined']:
            raise ValueError('Stable review ID required for pagination deduplication')
        unique[rid] = record
    coverage = coverage or {}
    windows = {}
    for months in [1, 3]:
        start = months_ago(as_of, months)
        subset = [r for r in unique.values() if record_date(r, date_basis) and start <= record_date(r, date_basis) <= as_of]
        reviewed = [r for r in subset if r.get('has_text') or r.get('has_media')]
        ratings_only = [r for r in subset if not r.get('has_text') and not r.get('has_media')]
        def keys(rows):
            return {r.get('reviewer_key') or 'unknown-review:'+r['review_id'] for r in rows}
        people, text_people, star_people = keys(subset), keys(reviewed), keys(ratings_only)
        ambiguous = sum(r.get('identity_basis') != 'stable_public_id' for r in subset)
        windows[str(months)] = {'months': months, 'start_inclusive': start.isoformat(), 'end_inclusive': as_of.isoformat(),
            'rating_or_review_events': len(subset), 'rating_only_events': len(ratings_only), 'review_events': len(reviewed),
            'participants_observed_or_inferred': len(people), 'review_participants': len(text_people),
            'rating_only_participants': len(star_people), 'both_kinds_participants': len(text_people & star_people),
            'identity_ambiguous_events': ambiguous, 'participant_count_is_exact': ambiguous == 0,
            'participants_exact_if_identifiable': len(people) if ambiguous == 0 else None,
            'estimated_sales': len(people)*multiplier, 'sales_multiplier': multiplier,
            'estimate_scope': 'observed_or_inferred_participants_only' if not coverage.get('date_range_complete') else 'covered_date_range_participants',
            'is_complete': bool(coverage.get('date_range_complete')) and coverage.get('rating_only_coverage') == 'count_reconciled'}
    report = {'as_of_kst': as_of.isoformat(), 'window_definition': 'rolling calendar months; both boundary dates inclusive',
        'date_basis': date_basis, 'date_basis_note': 'display uses reviewAt; created uses createdAt; edits may move the display date',
        'deduplicated_records': len(unique), 'missing_dates': sum(record_date(r,date_basis) is None for r in unique.values()),
        'coverage': coverage, 'windows': windows,
        'sales_model': 'user_assumption: observed/inferred unique participants × '+str(multiplier),
        'limitations': ['×15 is a user-specified heuristic, not observed transactions or a calibrated sales model.',
            'Masked email/name signatures may merge different people; missing identities use one review as one inferred participant.',
            'Coupang catalog reviews may combine options and sellers; this is not seller-specific sales.',
            'A dated list can be complete for the requested interval while hidden rating-only coverage remains unknown.']}
    if _with_options:
        groups={}
        for r in unique.values():
            key=('item:'+str(r['item_id']) if r.get('item_id') else
                 'vendor-item:'+str(r['vendor_item_id']) if r.get('vendor_item_id') else
                 'label:'+str(r['item_name']).strip() if r.get('item_name') else 'unknown')
            groups.setdefault(key,[]).append(r)
        report['option_groups']=[]
        for key, rows in sorted(groups.items()):
            vendors={}
            for r in rows:
                vendors.setdefault(r.get('vendor_item_id') or 'unknown',[]).append(r)
            labels=sorted({r['item_name'] for r in rows if r.get('item_name')})
            report['option_groups'].append({
                'option_key':key,'item_id':rows[0].get('item_id'),
                'option_label':labels[0] if labels else '옵션 미확인','observed_labels':labels,
                'identity_basis': 'catalog_item_id' if key.startswith('item:') else 'seller_listing_id' if key.startswith('vendor-item:') else 'label_only' if key.startswith('label:') else 'unknown',
                'review_records':len(rows),
                'windows':summarize(rows,as_of,multiplier,coverage,date_basis,False)['windows'],
                'vendor_items':[{'vendor_item_id':None if vid=='unknown' else vid,
                    'vendor_names':sorted({r['vendor_name'] for r in vr if r.get('vendor_name')}),
                    'windows':summarize(vr,as_of,multiplier,coverage,date_basis,False)['windows']}
                    for vid,vr in sorted(vendors.items())]})
        report['option_coverage']='Only options observed in collected reviews; not a complete catalog of selectable options.'
        report['limitations'].append('One person may contribute to multiple options; option participant totals must not be added to obtain the product union.')
    return report


def render(report, target):
    esc=lambda value:html.escape(str(value))
    rows=[]
    for window in report['windows'].values():
        rows.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [str(window['months'])+'개월',window['start_inclusive']+' ~ '+window['end_inclusive'],window['participants_observed_or_inferred'],window['review_events'],window['rating_only_events'],window['both_kinds_participants'],window['estimated_sales'],'기간·별점 포함 확인' if window['is_complete'] else '부분/포함범위 미확인'])+'</tr>')
    option_rows=[]
    for group in report.get('option_groups',[]):
        for months,w in group['windows'].items():
            option_rows.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [group['option_label'],group['item_id'] or group['option_key'],months+'개월',w['participants_observed_or_inferred'],w['review_events'],w['rating_only_events'],w['estimated_sales']])+'</tr>')
    options='<h2>구매 옵션별 집계</h2><p>리뷰에 기록된 itemId로 구분하고 판매자별 vendorItemId도 저장합니다. 기록이 없는 옵션의 판매량을 0으로 간주하지 않습니다. 여러 옵션에 참여한 동일인은 전체 합계에서 한 번만 셉니다.</p><article><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in ['기록된 구매 옵션명','옵션 식별값','기간','관측·추정 인원','글/사진 리뷰 건','별점만 건','추정 판매량'])+'</tr></thead><tbody>'+''.join(option_rows)+'</tbody></table></article>'
    target.write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>쿠팡 리뷰 기반 판매량 추정</title><style>body{font:16px/1.7 system-ui;color:#20384a;background:#f5f7f9;max-width:1150px;margin:32px auto;padding:20px}table{width:100%;border-collapse:collapse;background:white}td,th{padding:12px;border-bottom:1px solid #d6e0e5;text-align:left}article{overflow:auto}.note{background:#fff4df;padding:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#176ca2}</style><h1>쿠팡 별점·리뷰 참여자 집계</h1><p>'+esc(report.get('product_title',''))+'</p><p><a href="'+esc(report['product_url'])+'">원본 상품</a> · 기준일 '+report['as_of_kst']+' (한국시간)</p><p class="note">추정 판매량 = 관측·추정 중복 제거 참여자 × '+str(report['windows']['1']['sales_multiplier'])+'. 실제 주문 수가 아닙니다. 마스킹 식별값은 사람 구분의 추정치이며, 한 사람이 글과 별점을 모두 남겨도 합계에서 한 번 셉니다.</p><article><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in ['기간','집계 날짜(포함)','관측·추정 인원','글/사진 리뷰 건','별점만 건','양쪽 참여 인원','×'+str(report['windows']['1']['sales_multiplier'])+' 추정 판매량','수집 범위'])+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></article>'+options+'<h2>수집 근거와 한계</h2><pre>'+esc(json.dumps({k:report[k] for k in ['coverage','deduplicated_records','missing_dates','date_basis','date_basis_note','limitations']},ensure_ascii=False,indent=2))+'</pre></html>',encoding='utf-8')


class CollectionCoordinator:
    """Share native input safely; overlap independent page loads and extraction."""
    def __init__(self, start_interval=0.0, window_mode="background"):
        if window_mode not in ["background", "foreground"]:
            raise ValueError("Invalid window mode")
        self.window_mode = window_mode
        self.native_lock = threading.RLock()
        self.start_lock = threading.Lock()
        self.stopped = threading.Event()
        self.start_interval = start_interval
        self.next_start = 0.0

    def admit(self):
        with self.start_lock:
            delay = max(0, self.next_start-time.monotonic())
            if self.stopped.wait(delay):
                return False
            self.next_start = time.monotonic()+self.start_interval
            return not self.stopped.is_set()


class Browser:
    def __init__(self, prefix, session, coordinator=None):
        self.prefix, self.session = prefix, session
        self.coordinator = coordinator
        self.access_gate = AccessGate() if prefix and 'coupang' in session.lower() else None

    def call(self, action, *args, _retry=True):
        if self.coordinator:
            if self.coordinator.stopped.is_set() and action != 'close':
                raise ValueError('Collection stopped after access restriction')
            if action in ['open', 'click', 'tab', 'close']:
                with self.coordinator.native_lock:
                    if self.coordinator.stopped.is_set() and action != 'close':
                        raise ValueError('Collection stopped after access restriction')
                    if action == 'click':
                        tabs = self._call('tab', 'list')
                        if not isinstance(tabs, list) or len(tabs) != 1 or not tabs[0].get('page'):
                            raise ValueError('Cannot identify this worker tab safely')
                        if not tabs[0].get('active'):
                            self._call('tab', 'select', tabs[0]['page'])
                    return self._call(action, *args, _retry=_retry)
        return self._call(action, *args, _retry=_retry)

    def _call(self, action, *args, _retry=True):
        if action == 'open' and args:
            host = urlsplit(str(args[0])).hostname or ''
            if host == 'coupang.com' or host.endswith('.coupang.com'):
                self.access_gate = self.access_gate or AccessGate()
        if self.access_gate:
            try:
                with self.access_gate.action(action, args):
                    value = self._transport(action, *args, _retry=_retry)
            except CoupangAccessError:
                if self.coordinator: self.coordinator.stopped.set()
                raise
            except ValueError as exc:
                # Retry only a guaranteed undispatched input; never replay
                # a click whose dispatch outcome is uncertain.
                if _retry and action == 'click' and 'input was not dispatched' in str(exc):
                    tabs = self._call('tab', 'list')
                    if isinstance(tabs, list) and len(tabs) == 1 and tabs[0].get('page'):
                        self._call('tab', 'select', tabs[0]['page'])
                        return self._call(action, *args, _retry=False)
                raise
            if isinstance(value, dict):
                title = str(value.get('title', ''))
                denied = value.get('blocked') is True or value.get('error') == 'access_restricted' or bool(re.search(r'access denied|접속이.*제한', title, re.I))
                if denied:
                    self.access_gate.blocked(action)
                    if self.coordinator: self.coordinator.stopped.set()
                    raise CoupangAccessError(f'Access restriction detected at {action}; attempt stopped without a timed cooldown')
            return value
        return self._transport(action, *args, _retry=_retry)

    def _transport(self, action, *args, _retry=True):
        r=subprocess.run([*self.prefix,'browser',action,*map(str,args),'--session',self.session,'--window',self.coordinator.window_mode if self.coordinator else 'background'],capture_output=True,text=True,timeout=90)
        try: payload=json.loads(r.stdout)
        except ValueError: raise ValueError('Invalid browser JSON; exit '+str(r.returncode))
        if r.returncode or payload.get('ok') is not True:
            # Retry only when the bridge explicitly guarantees no input occurred.
            # Select this session's single leased tab, never an unrelated tab.
            message=str(payload.get('error',{}).get('message',''))
            if not self.access_gate and _retry and action=='click' and 'input was not dispatched' in message:
                tabs=self.call('tab','list')
                if isinstance(tabs,list) and len(tabs)==1 and tabs[0].get('page'):
                    self.call('tab','select',tabs[0]['page'])
                    return self.call(action,*args,_retry=False)
            raise ValueError(str(payload.get('error',{})))
        return payload.get('data')

    def snapshot(self):
        return self.call('eval',Path(__file__).with_name('coupang_review_extract.js').read_text())

    def wait(self, page):
        for _ in range(30):
            s=self.snapshot()
            if s.get('error'):
                blocked = self.call('eval', "(() => {const t=(document.title+' '+document.body.innerText.slice(0,4000)).toLowerCase();return /access denied|too many requests|접속이.*제한|비정상적인 접근|verify you are human|captcha/.test(t)})()")
                if blocked is True:
                    if self.coordinator:
                        self.coordinator.stopped.set()
                    raise ValueError('Access restriction detected; collection stopped')
                time.sleep(.4)
                continue
            dates=[r['created_at'] for r in s['records'] if isinstance(r.get('created_at'),(int,float))]
            if s['page']==page and s['sort']=='DATE_DESC' and not s['querying'] and dates==sorted(dates,reverse=True):
                return s
            time.sleep(.4)
        raise ValueError('Latest-first review page did not settle; blocked or changed structure')

    def next_page(self, wanted):
        code='''(() => {const root=document.querySelector('#sdpReview');const buttons=[...root.querySelectorAll('button')];let b=buttons.find(b=>b.innerText.trim()===WANTED);let grouped=false;if(!b){grouped=true;const numbers=buttons.filter(b=>/^\\d+$/.test(b.innerText.trim()));const last=numbers.at(-1);if(last){const group=last.parentElement;const candidates=[...group.querySelectorAll('button')];b=candidates.slice(candidates.indexOf(last)+1).find(x=>!x.disabled)}}if(!b||b.disabled)return false;b.setAttribute('data-codex-review-next','yes');return grouped?'group':'direct'})()'''.replace('WANTED',json.dumps(str(wanted)))
        mode=self.call('eval',code)
        if mode not in ['group','direct']:
            return False
        self.call('click','[data-codex-review-next="yes"]')
        self.call('eval',"document.querySelectorAll('[data-codex-review-next]').forEach(x=>x.removeAttribute('data-codex-review-next'))")
        if mode=='group':
            # Coupang's next-group arrow lands at the group's LAST page (20),
            # so explicitly select the required first page (11) before reading.
            selector="""(() => {const b=[...document.querySelectorAll('#sdpReview button')].find(b=>b.innerText.trim()===WANTED);if(!b||b.disabled)return false;b.setAttribute('data-codex-review-next','yes');return true})()""".replace('WANTED',json.dumps(str(wanted)))
            for _ in range(30):
                if self.call('eval',selector) is True:
                    self.call('click','[data-codex-review-next="yes"]')
                    self.call('eval',"document.querySelectorAll('[data-codex-review-next]').forEach(x=>x.removeAttribute('data-codex-review-next'))")
                    return True
                time.sleep(.4)
            return False
        return True


def crawl(url, out, prefix, as_of, multiplier=15, max_pages=100, full_scan=False, resume=False, date_basis='created', on_progress=None, coordinator=None, navigation_query=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    with (out/'.audit.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another audit owns this output directory')
        return _crawl(url,out,prefix,as_of,multiplier,max_pages,full_scan,resume,date_basis,on_progress,coordinator,navigation_query)


def _crawl(url, out, prefix, as_of, multiplier=15, max_pages=100, full_scan=False, resume=False, date_basis='created', on_progress=None, coordinator=None, navigation_query=None):
    parsed=urlsplit(url)
    match=re.fullmatch(r'/vp/products/(\d+)/?',parsed.path)
    if parsed.scheme!='https' or parsed.hostname not in ['www.coupang.com','coupang.com'] or not match or parsed.username is not None or parsed.password is not None:
        raise ValueError('Canonical HTTPS Coupang product URL required')
    product=match[1]
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    path=out/'state.json'
    fingerprint=digest([url,as_of.isoformat(),multiplier,full_scan,date_basis,prefix,hashlib.sha256(Path(__file__).with_name('coupang_review_extract.js').read_bytes()).hexdigest()])
    if path.exists():
        state=json.loads(path.read_text())
        if not resume or state['fingerprint']!=fingerprint:
            raise ValueError('Use --resume with identical inputs or a new output directory')
        for page in state['pages']:
            if hashlib.sha256(Path(page['file']).read_bytes()).hexdigest()!=page['sha256']:
                raise ValueError('Cached page changed')
        if state.get('done'):
            return json.loads((out/'report.json').read_text())
        state.setdefault('previous_attempts',[]).append({'pages':state['pages'],'finished_at_kst':state.get('finished_at_kst')})
        state['pages']=[]
    else:
        state={'fingerprint':fingerprint,'pages':[],'started_at_kst':dt.datetime.now(KST).isoformat()}
    browser=Browser(prefix,'coupang-reviews-'+product+'-'+uuid.uuid4().hex[:8], coordinator) if coordinator else Browser(prefix,'coupang-reviews-'+product)
    coverage={};records={};stop='page_limit';first=None;previous_date=None
    try:
        from app.coupang_navigation import home_search_detail
        trace=[]
        try:
            home_search_detail(browser, product, navigation_query or product, trace)
        finally:
            atomic_json(out/'navigation.json', trace)
        browser.call('click','--role','button','--name','최신순')
        wanted=1
        for _ in range(max_pages):
            s=browser.wait(wanted)
            if s['product_id']!=product or any(r['product_id']!=product for r in s['records']):
                raise ValueError('Review product mismatch')
            if s['filters'].get('q') or s['filters'].get('ratings') not in [-1,None,''] or s['filters'].get('market'):
                raise ValueError('Unexpected review filter; counts would be incomplete')
            if first is None:first=s
            if s['listed_review_count']!=first['listed_review_count'] or s['rating_count']!=first['rating_count']:
                raise ValueError('Review counts changed during traversal; retry a fresh snapshot')
            current=[record_date(r,'created') for r in s['records']]
            if current and previous_date and current[0] and current[0]>previous_date:
                raise ValueError('Cross-page date order changed')
            if current and current[-1]:previous_date=current[-1]
            if wanted>1 and s['records'] and all(r['review_id'] in records for r in s['records']):
                raise ValueError('Repeated page: pagination failed')
            for r in s['records']:records[r['review_id']]=r
            attempt=len(state.get('previous_attempts',[]))+1
            raw=out/f'attempt-{attempt:03d}-page-{wanted:05d}.json';atomic_json(raw,s)
            state['pages']=[p for p in state['pages'] if p['page']!=wanted]+[{'page':wanted,'file':str(raw.resolve()),'sha256':hashlib.sha256(raw.read_bytes()).hexdigest()}]
            atomic_json(path,state)
            if on_progress:
                on_progress({'page':wanted,'records':len(records),'total':s['listed_review_count']})
            print(json.dumps({'page':wanted,'records':len(records),'total':s['listed_review_count']},ensure_ascii=False),flush=True)
            if wanted>=s['total_pages']:
                stop='list_exhausted';break
            # Creation-date mode can stop at the covered boundary. Display-date
            # mode must scan all pages because later edits occur on old pages.
            if not full_scan and date_basis=='created' and current and all(d is not None for d in current) and current[-1]<months_ago(as_of,3):
                stop='three_month_boundary';break
            if _+1>=max_pages:
                stop='page_limit';break
            if not browser.next_page(wanted+1):
                stop='pagination_control_missing';break
            # Group navigation may jump to page 11/21; the expected next page remains explicit.
            wanted+=1
        coverage={'stop_reason':stop,'pages':len(state['pages']),
            'date_range_complete':stop in ['list_exhausted','three_month_boundary'],
            'rating_only_coverage':'count_reconciled' if first and first['rating_count'] is not None and first['rating_count']==first['listed_review_count'] else 'unknown',
            'site_rating_count':first['rating_count'] if first else None,'listed_review_count':first['listed_review_count'] if first else None,
            'list_count_reconciled':stop=='list_exhausted' and len(records)==first['listed_review_count'] if first else False}
        if stop=='list_exhausted' and not coverage['list_count_reconciled']:
            coverage['date_range_complete']=False
        missing=sum(record_date(r,date_basis) is None for r in records.values())
        if missing:coverage['date_range_complete']=False
    except Exception as exc:
        coverage={'date_range_complete':False,'rating_only_coverage':'unknown','stop_reason':'error','error':type(exc).__name__+': '+str(exc),'pages':len(state['pages'])}
    finally:
        try:browser.call('close')
        except Exception:pass
    result=summarize(list(records.values()),as_of,multiplier,coverage,date_basis)
    result.update(product_url=url,product_id=product,product_title=first.get('title','') if first else '',
                  navigation='OpenCLI existing Chrome; read-only rendered review data',llm_calls=0,
                  finished_at_kst=dt.datetime.now(KST).isoformat())
    atomic_json(out/'report.json',result)
    render(result,out/'index.html')
    state.update(done=all(w['is_complete'] for w in result['windows'].values()),finished_at_kst=result['finished_at_kst'])
    atomic_json(path,state)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',required=True)
    p.add_argument('--opencli-main',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--as-of',type=dt.date.fromisoformat,default=dt.datetime.now(KST).date())
    p.add_argument('--multiplier',type=int,default=15)
    p.add_argument('--max-pages',type=int,default=100)
    p.add_argument('--full-scan',action='store_true')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--date-basis',choices=['display','created'],default='created')
    a=p.parse_args()
    if a.max_pages<1:p.error('--max-pages must be positive')
    if a.multiplier<1:p.error('--multiplier must be positive')
    r=crawl(a.url,a.output_dir,['node',str(a.opencli_main.resolve())],a.as_of,a.multiplier,a.max_pages,a.full_scan,a.resume,a.date_basis)
    print(json.dumps(r,ensure_ascii=False,indent=2))
    return 0 if all(w['is_complete'] for w in r['windows'].values()) else 1


if __name__=='__main__':
    raise SystemExit(main())
