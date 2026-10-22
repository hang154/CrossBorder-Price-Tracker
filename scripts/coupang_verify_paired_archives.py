"""Verify stored detail assets and dated review IDs without network requests."""
import argparse,calendar,datetime as dt,hashlib,json
from pathlib import Path
from app.coupang_reviews import KST
from app.sourcing_pipeline import atomic_json

def verify(audit,source_root):
 state=json.loads((audit/'manifest.json').read_text());assert state.get('finished_at_kst'),'Collection still running'
 end=dt.date.fromisoformat(state['as_of']);year=end.year if end.month>1 else end.year-1;month=end.month-1 if end.month>1 else 12;start=dt.date(year,month,min(end.day,calendar.monthrange(year,month)[1]))
 result=dict(products_with_detail=0,detail_asset_hashes=0,detail_source_hashes=0,review_page_hashes=0,monthly_review_counts_checked=0,start_inclusive=start.isoformat(),end_inclusive=end.isoformat(),errors=[])
 def check_file(path,digest):
  assert path.resolve().is_relative_to(source_root.resolve()),'Evidence path outside run'
  assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,str(path)
 for pid,entry in state['products'].items():
  try:
   detail=audit/'details'/pid/'detail.json'
   if detail.exists():
    d=json.loads(detail.read_text())
    if d.get('raw_html_sha256'):
     assert str(d['product_id'])==pid;check_file(detail.parent/'detail-original.html.txt',d['raw_html_sha256']);result['detail_source_hashes']+=1;result['products_with_detail']+=1
     for a in d.get('assets',[]):
      if a.get('file'):check_file(detail.parent/a['file'],a['sha256']);result['detail_asset_hashes']+=1
     if d.get('status')=='complete':assert d.get('expanded') and d.get('assets') and all(a.get('file') for a in d['assets'])
   review=audit/'reviews'/pid/'state.json'
   metric=entry.get('monthly_metrics',{});records={}
   if review.exists():
    r=json.loads(review.read_text())
    for page in r.get('pages',[]):
     f=Path(page['file']);check_file(f,page['sha256']);result['review_page_hashes']+=1;d=json.loads(f.read_text());assert str(d['product_id'])==pid
     for row in d.get('records',[]):
      assert str(row['product_id'])==pid;records[str(row['review_id'])]=row
   if metric.get('review_count') is not None:
    count=sum(start<=dt.datetime.fromtimestamp(r['created_at']/1000,KST).date()<=end for r in records.values() if r.get('created_at'))
    assert count==metric['review_count'],f'Month count mismatch: source {count}, report {metric["review_count"]}'
    assert metric['observed_review_sales_estimate']==count*15
    if metric.get('estimated_monthly_sales') is not None:assert metric['estimated_monthly_sales']==count*15 and metric['date_range_covered'] and metric['all_rating_coverage_reconciled']
    result['monthly_review_counts_checked']+=1
  except Exception as exc:result['errors'].append(dict(product_id=pid,error=type(exc).__name__+': '+str(exc)))
 result['passed']=not result['errors'];return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--audit-dir',type=Path,required=True);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();result=verify(a.audit_dir,a.source_root);atomic_json(a.out,result);print(json.dumps(result,ensure_ascii=False));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
