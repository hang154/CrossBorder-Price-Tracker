"""Qwen extracts exact material/unit claims; Python ranks observed listing prices."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import re
from pathlib import Path

from app.catalog_review import qwen_call
from app.sourcing_agent import tool
from app.sourcing_pipeline import atomic_json, digest


FIELDS = {
    'key': {'type': 'string'}, 'material': {'type': 'string'},
    'material_quote': {'type': 'string'},
    'unit': {'type':'string','enum':['finished_bracelet','ring','mala','prayer_rope','single_bead','bead_strand','charm','other','unknown']},
    'unit_quote': {'type':'string'}, 'size': {'type':'string'}, 'size_quote': {'type':'string'},
    'grade': {'type':'string'}, 'grade_quote': {'type':'string'}}

ALIASES = {
 '호안석':r'호안|타이거\s*아이|호랑이\s*눈|虎眼|tiger.?eye',
 '황수정':r'황수정|시트린|黄水晶|citrine','자수정':r'자수정|紫水晶|amethyst',
 '백수정':r'백수정|白水晶|clear quartz','흑요석':r'흑요석|黑曜|obsidian',
 '마노':r'마노|아게이트|玛瑙|agate','카넬리안':r'카넬리안|carnelian',
 '연옥':r'연옥|nephrite|和田|허톈|허티안|헤티안|hetian',
 '비취':r'비취|翡翠|jadeite','옥':r'옥|jade|玉',
 '청금석':r'청금|라피스|랩피스|lapis','황철석':r'황철|pyrite',
 '토파즈':r'토파즈|topaz','문스톤':r'문스톤|moonstone','가넷':r'가넷|가닛|garnet',
 '백단':r'백단|샌달\s*우드|檀香|sandalwood','침향':r'침향|沉香|agarwood',
 '자단':r'자단|紫檀','로즈우드':r'로즈우드|rosewood','복숭아나무':r'복숭아|桃木|peach.?wood',
 '녹단':r'녹단|绿檀','보리자':r'보리자|보리수|bodhi|菩提',
 '은':r'실버|순은|은도금|silver|银|s925|s999',
 '스테인리스':r'스테인리스|스테인레스|stainless',
 '티타늄 스틸':r'티타늄\s*(?:스틸|강철)|titanium.?steel|钛钢',
 '황동':r'황동|黄铜|brass','구리':r'구리|铜|copper',
 '합금':r'합금|alloy|合金','레진':r'레진|resin|树脂',
 '유리':r'유리|glass|玻璃','진사':r'진사|朱砂|cinnabar',
 '지르콘':r'지르콘|zircon','세라믹':r'세라믹|ceramic|陶瓷',
 '종이':r'종이|paper|纸'}


def canonical_material(quote):
    matches=[name for name,pattern in ALIASES.items() if re.search(pattern,quote,re.I)]
    if any(m in matches for m in ['연옥','비취']):matches=[m for m in matches if m!='옥']
    if '황동' in matches:matches=[m for m in matches if m!='구리']
    if not matches:return 'unknown'
    # Wood trade names/translations do not prove botanical identity. Preserve the
    # exact observed claim instead of merging green/red/sandal/agarwood species.
    if any(m in matches for m in ['백단','침향','자단','로즈우드','복숭아나무','녹단']):
        return '+'.join(sorted(matches))+' · '+quote.strip()
    label='+'.join(sorted(matches))
    if re.search(r'도금|plated|镀',quote,re.I):label+=' (도금 표기)'
    if re.search(r'인조|합성|synthetic|imitation|人造',quote,re.I):label+=' (인조·합성 표기)'
    return label


def validate_item(item, row):
    text=(row.get('title') or '')+'\n'+row.get('evidence_text','')
    for field in ['material_quote','unit_quote','size_quote','grade_quote']:
        if item.get(field) and item[field] not in text:
            item[field]=''
    item['material']=canonical_material(item['material_quote'])
    if '은' in item['material'] and re.search(r'도금|plated|镀',row.get('title',''),re.I) and '도금 표기' not in item['material']:
        item['material']+=' (도금 병기 · 바탕금속 미확인)'
    if not item['unit_quote']:item['unit']='unknown'
    if item['unit']=='single_bead' and not re.search(r'낱알|느슨한|루스|loose|single.?bead|per.?bead|散珠|单珠',item['unit_quote'],re.I):
        item['unit']='unknown'
    if not item['size_quote']:item['size']='unknown'
    if not item['grade_quote']:item['grade']='unspecified'
    return item


def rank(rows, items):
    known={r['key']:r for r in rows};groups={}
    for a in items:
        r=known.get(a['key'])
        if not r or a['material']=='unknown' or a['unit'] in ['unknown','other'] or not isinstance(r.get('price'),(int,float)) or r['price']<=0 or not r.get('currency'):continue
        # Never combine grades, sizes, currencies or different selling units.
        identity=(a['material'],a['unit'],a['size'],a['grade'],r['currency'])
        groups.setdefault(identity,[]).append({**a,'price':r['price'],'moq':r['moq'],'url':r['url'],'title':r['title'],'site':r['site'],'image_url':r.get('inline_image') or r.get('image_url')})
    result=[]
    for identity,values in groups.items():
        values.sort(key=lambda x:(x['price'],x['key']))
        cheapest=values[0]['price']
        result.append({'material':identity[0],'unit':identity[1],'size':identity[2],'grade':identity[3],'currency':identity[4],
            'status':'size_unconfirmed' if identity[2]=='unknown' else 'same_claimed_spec',
            'count':len(values),'minimum_listing_price':cheapest,'winner_keys':[r['key'] for r in values if r['price']==cheapest],'candidates':values})
    return sorted(result,key=lambda g:(-g['count'],g['material'],g['minimum_listing_price']))


def run(out):
    data=json.loads((out/'reviewed-catalog.json').read_text());rows=[r for r in data['items'] if r['annotation']['relevance']!='irrelevant'];known={r['key']:r for r in rows}
    schema=tool('extract_material_units','Extract source-quoted material and selling-unit claims, not natural origin or quality certification.',{'items':{'type':'array','items':{'type':'object','properties':FIELDS,'required':list(FIELDS),'additionalProperties':False}}},['items'])
    batches=[rows[i:i+16] for i in range(0,len(rows),16)]
    def one(values):
        compact=[{k:r.get(k) for k in ['key','title','evidence_text']} for r in values];name='material-units-'+digest(compact)[:14];path=out/(name+'.json')
        if path.exists():return json.loads(path.read_text())['items']
        prompt=('Classify EVERY supplied key. Use identical canonical Korean material labels for identical explicit materials (호안석, 황수정, 백수정, 자수정, 흑요석, 마노, 연옥, 비취, 백단, 침향, 자단, 보리자, 은, 스테인리스, 레진, 유리 etc). Keep distinct species, alloys, synthetic/natural CLAIMS, mixed materials distinct. Never infer jade species or purity. Unknown -> unknown. unit is what the title explicitly describes: finished bracelet versus loose single bead versus bead strand versus ring/mala/charm. Quotes MUST be exact substrings. size should be normalized mm only when explicit, otherwise unknown. grade normalizes explicit 5A/7A/925/999/etc, otherwise unspecified. Do not infer price tier, pack count or variant applicability. items must be an array, not a string.\n'+json.dumps(compact,ensure_ascii=False))
        try:
            a=qwen_call(out,name,prompt,schema);seen=set();items=[];batch_keys={r['key'] for r in values}
            for item in a['items']:
                if item['key'] in batch_keys and item['key'] not in seen:
                    items.append(validate_item(item,known[item['key']]));seen.add(item['key'])
            atomic_json(path,{'items':items});print(json.dumps({'material_batch':name,'items':len(items),'expected':len(values)}),flush=True);return items
        except Exception as e:
            atomic_json(out/(name+'-error.json'),{'error':str(e)});return []
    with ThreadPoolExecutor(max_workers=3) as pool:items=[x for batch in pool.map(one,batches) for x in batch]
    items=[validate_item(a,known[a['key']]) for a in items]
    result={'scope':'lowest_observed_listing_not_global_or_landed_cost','source_sha256':digest(data),'requested':len(rows),'classified':len(items),'items':items,'groups':rank(rows,items),'limitations':['동일 소재 표기라도 재질 진위 미확인','규격 미표기 그룹은 최저가 후보이며 동등 규격 비교 미확정','대표 옵션 표시가가 정확한 규격 옵션에 적용되는지 미확인','MOQ·포장 수량·배송·세금 별도 확인; 묶음 가격을 낱개 가격으로 임의 환산하지 않음']}
    atomic_json(out/'material-price-ranking.json',result)
    print(json.dumps({'classified':len(items),'groups':len(result['groups']),'multi_candidate_groups':sum(g['count']>1 for g in result['groups'])}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True);run(p.parse_args().output_dir.resolve())
