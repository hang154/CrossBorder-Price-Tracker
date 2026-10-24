"""Korean sourcing adapter: local Qwen + MIT upstream pricing/opportunity engine.
No purchases. All cost scenarios are editable estimates, not official fees.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import html
import json
import re
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from app.catalog_review import qwen_call
from app.sourcing_agent import tool, MODEL, BASE
from app.sourcing_pipeline import atomic_json

SCENARIOS = {
 'optimistic': dict(sale_factor=1, fee=.10, ads=.05, returns=.02, international=500, delivery=2800, packaging=300, buffer=.05),
 'base': dict(sale_factor=.95, fee=.12, ads=.10, returns=.05, international=1000, delivery=3200, packaging=500, buffer=.15),
 'stress': dict(sale_factor=.85, fee=.15, ads=.20, returns=.10, international=2000, delivery=3800, packaging=800, buffer=.30),
}
NOTICE = '원가는 대표 옵션 표시가입니다. 국내외 구성·길이·소재·운임·세금·수수료 미확정. 수익은 가정에 따른 세전 공헌이익이며 실제 순이익·최근 판매량이 아닙니다. 모든 후보는 견적·샘플 검증용입니다.'

def sha(path):
 return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_pairs(source, comparison):
 domestic=json.loads((source/'enriched-candidates.json').read_text())
 overseas=json.loads((source/'overseas-candidates.json').read_text())
 ds={(r['group_id'],str(r['product_id'])):r for r in domestic}
 os={(r['group_id'],str(r.get('offer_id') or r['product_id'])):r for r in overseas}
 pairs=[]
 for p in sorted(comparison.glob('w*/qwen-selection.json')):
  for m in json.loads(p.read_text()).get('matches',[]):
   d=ds.get((p.parent.name,str(m['domestic_id'])))
   o=os.get((p.parent.name,str(m['overseas_id'])))
   if d and o and d.get('currency')=='KRW' and o.get('currency')=='KRW' and (d.get('price') or 0)>0 and (o.get('price_min') or 0)>0:
    key=f"{p.parent.name}:{m['domestic_id']}:{m['overseas_id']}"
    if not any(x['pair_id']==key for x in pairs):
     pairs.append(dict(pair_id=key,domestic=d,overseas=o,previous_difference=m.get('difference','')))
 return domestic,overseas,pairs

def validate_reviews(items, expected):
 by={p['pair_id']:p for p in expected}; found={}
 for a in items:
  key=a['pair_id']
  if key not in by or key in found: raise ValueError('Unknown/duplicate pair ID')
  if a.get('match_type') not in ['comparable_function','weak_reference','different_product'] or a.get('unit_compatibility') not in ['listing_consistent','requires_check','incompatible']: raise ValueError('Invalid comparison class')
  if not isinstance(a.get('reason_ko'),str) or not isinstance(a.get('risk_traits'),list) or any(t not in ['apparel_sizes','bulky','fragile','electric','liquid','brand','dimensions_unknown'] for t in a['risk_traits']): raise ValueError('Invalid risk evidence')
  for side in ['domestic','overseas']:
   n=a[side+'_units']; quote=a[side+'_quantity_quote']
   if not isinstance(quote,str): raise ValueError('Invalid quantity quote')
   if type(n) is not int or not 0<=n<=1000: raise ValueError('Invalid unit count')
   if n>1 and (not quote or quote not in by[key][side]['title']):
    raise ValueError('Pack quantity must have exact title evidence')
  found[key]=a
 if set(found)!=set(by): raise ValueError('Missing pair IDs')
 return found

def review_pairs(out,pairs):
 props={'pair_id':{'type':'string'},'match_type':{'type':'string','enum':['comparable_function','weak_reference','different_product']},
 'unit_compatibility':{'type':'string','enum':['listing_consistent','requires_check','incompatible']},
 'domestic_units':{'type':'integer'},'overseas_units':{'type':'integer'},
 'domestic_quantity_quote':{'type':'string'},'overseas_quantity_quote':{'type':'string'},
 'risk_traits':{'type':'array','items':{'type':'string','enum':['apparel_sizes','bulky','fragile','electric','liquid','brand','dimensions_unknown']}},'reason_ko':{'type':'string'}}
 schema=tool('review_sourcing_pairs','Review supplied pair IDs only. Units 0=unknown, 1=explicit single item, >1 requires exact title quote. MOQ is never pack size.',{'items':{'type':'array','items':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}}},['items'])
 batches=[pairs[i:i+8] for i in range(0,len(pairs),8)]
 def one(values):
  compact=[dict(pair_id=p['pair_id'],domestic_title=p['domestic']['title'],overseas_title=p['overseas']['title'],previous_difference=p['previous_difference']) for p in values]
  fingerprint=hashlib.sha256(json.dumps(compact,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
  name='pair-review-'+fingerprint[:16]; cache=out/(name+'.json')
  if cache.exists():
   try: return validate_reviews(json.loads(cache.read_text())['items'],values)
   except (ValueError,KeyError,TypeError): pass
  found={}; by={v['pair_id']:v for v in values}
  def retain(items):
   for a in items:
    if not isinstance(a,dict) or a.get('pair_id') not in by: continue
    try:
     a=dict(a); rejected=[]
     for side in ['domestic','overseas']:
      count=a.get(side+'_units'); quote=a.get(side+'_quantity_quote')
      if type(count) is int and count>0 and (not isinstance(quote,str) or not quote or quote not in by[a['pair_id']][side]['title']):
       a[side+'_units']=0; a[side+'_quantity_quote']=''; rejected.append(side)
     if rejected:
      a['unit_compatibility']='requires_check'
      a['reason_ko']='[수량 인용 거부: '+','.join(rejected)+'; 해당 단위 미확정] '+a.get('reason_ko','')
     found.update(validate_reviews([a],[by[a['pair_id']]]))
    except (ValueError,KeyError,TypeError): continue
  # Preserve valid records from failed earlier tool responses; never coerce malformed JSON.
  for raw_path in sorted(out.glob(name+'-attempt*-response.json')):
   try:
    raw=json.loads(raw_path.read_text()); calls=raw['choices'][0]['message'].get('tool_calls') or []
    if raw['choices'][0]['finish_reason']=='length': continue
    for c in calls:
     if c['function']['name']==schema['function']['name']:
      args=json.loads(c['function']['arguments'])
      if isinstance(args.get('items'),list): retain(args['items'])
   except (ValueError,KeyError,TypeError): pass
  for attempt in range(2):
   pending=[v for v in compact if v['pair_id'] not in found]
   if not pending: break
   suffix=hashlib.sha256(json.dumps(pending,sort_keys=True).encode()).hexdigest()[:8]
   try:
    result=qwen_call(out,name+f'-attempt{attempt}-'+suffix, '한국 사입 후보 비교. 모든 pair_id를 정확히 한번씩 검토. items는 실제 JSON 배열. 모양/용도가 유사해도 구성·길이·재질 차이를 명시. 개수 명시 없으면 units=0. MOQ/최소주문수는 묶음수 아님. 길이 3M은 개수3이 아님. 단위 미확정 requires_check. 짧은 한국어 근거.\n'+json.dumps(pending,ensure_ascii=False),schema)
    retain(result['items'])
   except Exception as exc:
    atomic_json(out/(name+f'-error{attempt}.json'),{'error':str(exc)})
  missing=[v for v in values if v['pair_id'] not in found]
  if missing:
   if len(values)==1: raise ValueError('Single record failed after bounded retries: '+values[0]['pair_id'])
   step=max(1,len(missing)//2)
   for i in range(0,len(missing),step): found.update(one(missing[i:i+step]))
  checked=validate_reviews(list(found.values()),values)
  atomic_json(cache,{'items':list(checked.values())})
  print(json.dumps({'batch_done':len(values),'cache':name}),flush=True)
  return checked

 reviews={}
 with ThreadPoolExecutor(max_workers=4) as pool:
  for f in as_completed([pool.submit(one,b) for b in batches]): reviews.update(f.result())
 return reviews

def explicit_units(a, side, title):
 n=a[side+'_units']; quote=a[side+'_quantity_quote']
 if not n or not quote or quote not in title: return 0
 # A generic word such as 'carpet' is not evidence of one carpet per selling unit.
 pattern=rf'(?<![0-9]){n}\s*(?:개|장|매|세트|팩|입|pcs|pc|pieces?|件|套|个|条|组)'
 return n if re.search(pattern,quote,re.I) else 0


def engines(repo):
 sys.path.insert(0,str(repo.resolve()))
 from amazon_india_seller_mcp.config.settings import FeeSchedule
 from amazon_india_seller_mcp.services.pricing_service import PricingService
 from amazon_india_seller_mcp.services import OpportunityScores,score_opportunity
 return FeeSchedule,PricingService,OpportunityScores,score_opportunity

def evaluate(pairs,reviews,domestic,repo,scenarios):
 FeeSchedule,PricingService,OpportunityScores,score_opportunity=engines(repo)
 engines_by_scenario={}
 for name,s in scenarios.items():
  fees=FeeSchedule(currency='KRW',referral_fee_rates={'default':s['fee']},closing_fee_slabs=[{'up_to_price':1000000,'self_ship':0}],gst_rate_on_fees=0,payment_gateway_rate=0,source='Unverified Korean cost scenario; Indian fees disabled')
  engines_by_scenario[name]=PricingService(SimpleNamespace(fee_schedule=fees,beginner_criteria=SimpleNamespace(min_profit_margin=.3)))
 results=[]
 for p in pairs:
  d,o=p['domestic'],p['overseas']; a=dict(reviews[p['pair_id']])
  for side,source in [('domestic',d),('overseas',o)]:
   a[side+'_units']=explicit_units(a,side,source['title'])
  counts=[r.get('review_count') or 0 for r in domestic if r['group_id']==d['group_id']]
  count=d.get('review_count') or 0
  percentile=100*sum(c<count for c in counts)/max(1,len(counts)-1)
  rating=d.get('rating'); smooth=((rating or 4)*count+4*20)/(count+20) if rating else 4
  popularity=min(100,.75*percentile+.25*max(0,(smooth-3)*50))
  # Never divide a set price by '3pcs' when domestic composition is unknown.
  denominator=max(1,a['overseas_units']) if a['domestic_units']>0 and a['unit_compatibility']=='listing_consistent' else 1
  quantity=max(1,a['domestic_units'])/denominator
  bulk=2 if 'bulky' in a['risk_traits'] else 1
  computed={}
  for name,s in scenarios.items():
   sale=round(d['price']*s['sale_factor'],2)
   cost=round(o['price_min']*quantity*(1+s['buffer']),2)
   freight=round(s['international']*quantity*bulk,2)
   other=round(freight+sale*s['ads'],2)
   raw=engines_by_scenario[name].calculate(sale,cost,packaging_cost=s['packaging'],weight_grams=1,fulfillment_method='Self Ship',expected_return_rate=s['returns'],other_costs=other,shipping_cost_override=s['delivery']*bulk).model_dump()
   expected=round(sale-cost-s['packaging']-round(sale*s['fee'],2)-s['delivery']*bulk-raw['return_reserve']-other,2)
   if abs(expected-raw['estimated_profit'])>.021: raise ValueError('Independent profit reconciliation failed')
   raw['platform_fee_excluding_delivery']=round(sale*s['fee'],2)
   raw['international_freight_assumption']=freight
   raw['variable_rate_break_even']=round((cost+s['packaging']+s['delivery']*bulk+raw['return_reserve']+freight)/(1-s['fee']-s['ads']),2)
   computed[name]=raw
  moq=o.get('moq_value'); sourcing=60 if moq is None else 90 if moq<=5 else 65 if moq<=50 else 35
  rocket=sum(bool(r.get('rocket_badge_present')) for r in domestic if r['group_id']==d['group_id'])/len(counts)
  scores=OpportunityScores(demand=popularity,profitability=computed['base']['profitability_score'],competition=max(10,85-rocket*45),return_risk=max(10,85-len(a['risk_traits'])*15),sourcing_ease=sourcing,beginner_friendliness=max(10,85-len(a['risk_traits'])*20))
  penalty=25 if a['match_type']=='different_product' else 12 if a['match_type']=='weak_reference' else 0
  penalty+=10 if a['unit_compatibility']!='listing_consistent' else 0
  score=score_opportunity(scores,penalties=[a['reason_ko']],penalty_points=penalty).model_dump()
  eligible=a['match_type']=='comparable_function' and a['unit_compatibility']!='incompatible' and computed['base']['estimated_profit']>0
  results.append(dict(**p,review=a,scenarios=computed,opportunity=score,popularity_proxy=round(popularity,2),quantity_ratio_assumed=quantity,quantity_verified=a['domestic_units']>0 and a['overseas_units']>0,monthly_sales=None,decision='견적·샘플 검증 후보' if eligible else '보류',eligible=eligible))
 return sorted(results,key=lambda r:(r['eligible'],r['opportunity']['overall_opportunity_score'],r['scenarios']['base']['estimated_profit']),reverse=True)


def final_review(out, result):
 # Models select only supplied candidates; arithmetic remains deterministic.
 pool=[]; seen=set()
 for r in result:
  if not r['eligible'] or r['domestic']['group_id'] in seen: continue
  seen.add(r['domestic']['group_id'])
  pool.append(dict(pair_id=r['pair_id'],domestic_title=r['domestic']['title'],overseas_title=r['overseas']['title'],group=r['domestic']['group_name'],score=r['opportunity']['overall_opportunity_score'],reviews=r['domestic'].get('review_count'),quantity_verified=r['quantity_verified'],reason=r['review']['reason_ko'],profits={n:v['estimated_profit'] for n,v in r['scenarios'].items()}))
 pool=pool[:20]
 if not pool: return {'items':[], 'conclusion_ko':'기준 시나리오 양수 후보 없음'}
 ref_map={f'C{i+1:02d}':item['pair_id'] for i,item in enumerate(pool)}
 for ref,item in zip(ref_map,pool): item['candidate_ref']=ref
 props={'candidate_ref':{'type':'string','enum':list(ref_map)},'reason_ko':{'type':'string'},'next_validation_ko':{'type':'string'}}
 schema=tool('recommend_validation_shortlist','Pick 5 distinct supplied IDs for quotation/sample validation only. No purchase execution.',{'items':{'type':'array','items':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}},'conclusion_ko':{'type':'string'}},['items','conclusion_ko'])
 fingerprint=hashlib.sha256(json.dumps(pool,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 dest=out/('final-review-'+fingerprint[:16]+'.json')
 if dest.exists(): return json.loads(dest.read_text())
 answer=qwen_call(out,'final-shortlist-'+fingerprint[:16], 'candidate_ref(C01 등)로만 후보 선택. 긴 pair_id를 출력하지 말 것. 상품군 이름보다 실제 국내외 상품 제목을 우선 검토하고 용도가 다르면 제외. 인기도 대리지표와 세전 공헌이익의 민감도를 비교해 서로 다른 상품군 최대5개를 골라 견적/샘플 우선순위로 권장. 실제 순이익/최근 판매량 확정 금지. 단위 미확정과 보수 시나리오 적자를 명시. 숫자를 새로 계산하거나 조작하지 말고 다음 검증 행동을 제시.\n'+json.dumps(pool,ensure_ascii=False),schema)
 for item in answer['items']:
  if item.get('candidate_ref') not in ref_map: raise ValueError('Unknown candidate ref')
  item['pair_id']=ref_map[item['candidate_ref']]
 ids=[a['pair_id'] for a in answer['items']]
 if not 1<=len(ids)<=5 or len(set(ids))!=len(ids) or not set(ids)<={a['pair_id'] for a in pool}: raise ValueError('Invalid shortlist IDs')
 atomic_json(dest,answer); return answer

def report(out,result):
 from openpyxl import Workbook
 wb=Workbook(); ws=wb.active; ws.title='사입 검증 우선순위'
 headers=['ID','상품군','국내 상품','1688 상품','점수','인기도 대리지표','누적 리뷰','별점','로켓 표시','국내가','해외가','낙관 이익','기준 이익','보수 이익','기준 마진','단위 확정','판정','비교 근거','국내 URL','1688 URL']
 ws.append(headers)
 rows=[]
 for r in result:
  d,o=r['domestic'],r['overseas']; sc=r['scenarios']
  values=[r['pair_id'],d['group_name'],d['title'],o['title'],r['opportunity']['overall_opportunity_score'],r['popularity_proxy'],d.get('review_count'),d.get('rating'),d.get('rocket_badge_present'),d['price'],o['price_min'],*[sc[n]['estimated_profit'] for n in ['optimistic','base','stress']],sc['base']['profit_margin'],r['quantity_verified'],r['decision'],r['review']['reason_ko'],d['url'],o['item_url']]
  ws.append([("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for v in values])
  esc=lambda v:html.escape(str(v))
  cells=['<td>'+esc(v)+'</td>' for v in values[:-2]]
  for idx,source in [(2,d),(3,o)]:
   if source.get('image_url'): cells[idx]='<td><img loading="lazy" style="width:72px;height:72px;object-fit:contain;display:block" src="'+esc(source['image_url'])+'">'+esc(values[idx])+'</td>'
  rows.append('<tr>'+''.join(cells)+f'<td><a href="{esc(d["url"])}">쿠팡</a> · <a href="{esc(o["item_url"])}">1688</a></td></tr>')
 ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
 notes=wb.create_sheet('가정과 한계'); notes.append([NOTICE]); notes.append(['점수는 표본 내 리뷰 순위·별점의 대리지표. 최근 수요/월 판매량 없음.']); notes.append([(out/'scenarios.json').read_text()])
 wb.save(out/'research.xlsx')
 page='<!doctype html><meta charset="utf-8"><title>사입 기회 평가</title><style>body{font:14px system-ui;margin:24px;color:#222}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px;min-width:80px}td:nth-child(3),td:nth-child(4),td:nth-child(18){min-width:230px}thead{position:sticky;top:0;background:#eee}input{padding:10px;width:350px}</style><h1>사입 견적·샘플 검증 우선순위</h1><p>'+html.escape(NOTICE)+'</p><p>GitHub MIT 엔진 + 로컬 Qwen. 누적 리뷰 기반 인기도, 실측 구매 성과 아님. 1건=국내외 비교 조합.</p><input id="filter" placeholder="상품명·판정 검색"><p><a href="research.xlsx">엑셀</a> · <a href="results.json">전체 결과·가정</a></p><table><thead><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in headers[:-2]+['원본'])+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table><script>document.querySelector("#filter").oninput=e=>document.querySelectorAll("tbody tr").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(e.target.value.toLowerCase()))</script>'
 (out/'index.html').write_text(page)

def main():
 p=argparse.ArgumentParser(); p.add_argument('--engine-repo',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--comparison',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--scenarios',type=Path)
 args=p.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
 started=datetime.now(timezone.utc).isoformat()
 domestic,overseas,pairs=load_pairs(args.source,args.comparison)
 atomic_json(args.out/'run-input.json',dict(started=started,pairs=len(pairs),model=MODEL,base=BASE,upstream_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.engine_repo,text=True).strip(),input_hashes={str(f):sha(f) for f in [args.source/'enriched-candidates.json',args.source/'overseas-candidates.json',*args.comparison.glob('w*/qwen-selection.json')]},code_sha256=sha(__file__)))
 scenarios=json.loads(args.scenarios.read_text()) if args.scenarios else SCENARIOS
 atomic_json(args.out/'scenarios.json',scenarios)
 reviews=review_pairs(args.out,pairs)
 result=evaluate(pairs,reviews,domestic,args.engine_repo,scenarios)
 atomic_json(args.out/'evaluated.json',{'items':result})
 shortlist=final_review(args.out,result)
 atomic_json(args.out/'shortlist.json',shortlist)
 atomic_json(args.out/'results.json',dict(notice=NOTICE,scenarios=scenarios,shortlist=shortlist,items=result))
 report(args.out,result)
 atomic_json(args.out/'summary.json',dict(started=started,finished=datetime.now(timezone.utc).isoformat(),pairs=len(pairs),reviews=len(reviews),eligible_pairs=sum(r['eligible'] for r in result),eligible_groups=len({r['domestic']['group_id'] for r in result if r['eligible']}),schema_validated=True,independent_profit_checks=len(result)*len(scenarios),monthly_sales_available=False,artifacts={f:sha(args.out/f) for f in ['results.json','research.xlsx','index.html']}))
 print(json.dumps({'finished':True,'pairs':len(pairs),'out':str(args.out)}),flush=True)
if __name__=='__main__': main()
