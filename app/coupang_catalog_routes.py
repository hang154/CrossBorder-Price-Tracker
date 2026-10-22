"""Read public best100 cards and seller catalog routes, separately from search.

Route discovery reference: https://github.com/Noah3521/coupang-sourcing .
Parsing is based on HTML observed locally, including the current Next.js cards.
A ranking is never labeled as keyword search or actual sales volume.
"""
import datetime as dt
import hashlib
import html
import json
import re
from urllib.parse import urljoin, urlparse, parse_qs

BASE='https://www.coupang.com/'

def text(value):
    return ' '.join(html.unescape(re.sub(r'<[^>]*>|<!--.*?-->', '', value, flags=re.S)).split())

def embedded_products(body):
    """Read product props from saved Next flight text, never execute script code."""
    chunks=[]
    for encoded in re.findall(r'self\.__next_f\.push\((\[.*?\])\)</script>', body, re.S):
        try:
            value=json.loads(encoded)
            if len(value)>1 and isinstance(value[1],str):chunks.append(value[1])
        except (ValueError, TypeError):continue
    stream=''.join(chunks);decoder=json.JSONDecoder();result={}
    for match in re.finditer(r'\{\s*"index"\s*:\s*\{\s*"title"\s*:',stream):
        try:obj,_=decoder.raw_decode(stream,match.start())
        except ValueError:continue
        idx=obj.get('index') or {};pid=str(obj.get('legacyProductId',''))
        if pid.isdigit():result[(pid,str(idx.get('itemId','')),str(obj.get('vendorItemId') or idx.get('winnerVendorItemId','')))]=obj
    return result


def _number(value):
    if value is None:return None
    digits=re.sub(r'[^0-9]','',str(value))
    return int(digits) if digits else None


def _content_text(value):
    if isinstance(value,list):return ''.join(_content_text(x) for x in value).strip()
    if isinstance(value,dict):return str(value.get('text') or '')
    return ''


def card_details(card,url,props):
    query=parse_qs(urlparse(url).query);item=(query.get('itemId') or [None])[0];vendor=(query.get('vendorItemId') or [None])[0]
    # Delivery badge alt text is direct visual evidence; missing badge is not a
    # declaration that this product can never qualify for Rocket at any address.
    badge_markup=re.sub(r'<figure\b.*?</figure>', '', card, flags=re.S)
    badge_markup=re.sub(r'<[^>]*class="[^"]*ProductUnit_productName[^"]*"[^>]*>.*?</[^>]+>', '', badge_markup, flags=re.S)
    alts=[html.unescape(x) for x in re.findall(r'<img\b[^>]*\balt="([^"]*)"',badge_markup)]
    badges=list(dict.fromkeys(x for x in alts if re.search('로켓|무료배송|무료반품|도착',x)))
    rocket=[x for x in badges if '로켓' in x]
    types=[]
    for badge in rocket:
        kind='seller_rocket' if '판매자' in badge else 'rocket_global' if '직구' in badge else 'rocket_fresh' if '프레시' in badge else 'rocket_install' if '설치' in badge else 'rocket'
        if kind not in types:types.append(kind)
    visible=text(card);delivery_visible=text(badge_markup);price_props=props.get('priceArea') or {};delivery=props.get('promisedDeliveryDateArea') or {}
    base=re.search(r'<del\b[^>]*class="[^"]*PriceInfo_basePrice[^"]*"[^>]*>(.*?)</del>',card,re.S)
    discount=re.search(r'class="[^"]*PriceInfo_discountRate[^"]*"[^>]*>(.*?)</',card,re.S)
    shipping=_content_text((props.get('shippingInfoArea') or {}).get('contents',[]))
    arrival=_content_text(delivery.get('contents',[]))
    if not arrival:
        node=re.search(r'class="[^"]*DeliveryInfo_delivery[^"]*"[^>]*>(.*?)(?=<div class="(?:UsedProductInfo|ProductRating|fw-pt)|$)',card,re.S)
        arrival=text(node[1]) if node else ''
    cash=re.search(r'(최대\s*[\d,]+원\s*적립)',visible)
    used=props.get('usedProductArea') or {};sold=props.get('soldoutArea') or {};ad=props.get('adBadgeArea') or {}
    return {'item_id':item,'vendor_item_id':vendor,
            'base_price':(_number(text(base[1])) if base else _number(price_props.get('basePrice'))) or None,
            'discount_rate_percent':_number(text(discount[1])) if discount else price_props.get('discountRate'),
            'unit_price_text':price_props.get('criteriaPriceInfo') or None,
            'delivery_badges':badges,'rocket_badge_present':bool(rocket),
            'rocket_delivery':True if rocket else None,'rocket_delivery_types':types,
            'rocket_status_basis':'visible card badge; absence means not displayed',
            'delivery_text':arrival or None,'arrival_guaranteed_observed':'도착 보장' in arrival,
            'free_shipping_observed':True if ('무료배송' in delivery_visible or '무료배송' in shipping) and not re.search(r'이상.*무료배송|조건.*무료배송', delivery_visible+' '+shipping) else None,
            'shipping_text':shipping or price_props.get('shippingFeeDescription') or None,
            'cashback_text':cash[1] if cash else None,
            'sold_out':sold.get('soldout') if isinstance(sold.get('soldout'),bool) else None,
            'used_or_returned_options_text':_content_text(used.get('usedProductInfo',[])) or None,
            'used_or_returned_lowest_price':_number(_content_text(used.get('usedProductPrice',[]))),
            'sponsored':ad.get('sponsored') if isinstance(ad.get('sponsored'),bool) else None,
            'seller_name':None,'all_options':None,
            'details_scope':'observed listing card and matching item/vendor page props; not full detail page',
            'card_text':visible,'card_sha256':hashlib.sha256(card.encode()).hexdigest()}


def parse_ranking(body, source_url):
    rows=[];seen=set();props=embedded_products(body)
    cards=re.findall(r'<a\b(?=[^>]*\bclass="[^"]*\bbest100-product-cell\b)[^>]*href="([^"]+)"[^>]*>(.*?)</a>',body,re.S)
    for href,card in cards:
        url=urljoin(BASE,html.unescape(href));m=re.search(r'^https://www\.coupang\.com/vp/products/(\d+)(?:\?|$)',url)
        if not m or m[1] in seen:continue
        name=re.search(r'<[^>]*class="[^"]*ProductUnit_productName[^\"]*"[^>]*>(.*?)</[^>]+>',card,re.S)
        price=re.search(r'<strong\b[^>]*class="[^"]*Price_priceValue[^\"]*"[^>]*>(.*?)</strong>',card,re.S)
        image=re.search(r'<img\b[^>]*src="([^"]+)"',card)
        rating=re.search(r'aria-label="([0-5](?:\.\d+)?)"',card)
        after_rating=card[card.find('ProductRating_productRating'):]
        review=re.search(r'\(([\d,]+)\)',text(after_rating)) if 'ProductRating_productRating' in card else None
        if not name:continue
        seen.add(m[1]);digits=re.sub(r'\D','',text(price[1])) if price else ''
        rows.append({'rank':len(rows)+1,'product_id':m[1],'title':text(name[1]),'price':int(digits) if digits else None,'currency':'KRW','rating':float(rating[1]) if rating else None,'review_count':int(review[1].replace(',','')) if review else None,'url':url,'image_url':urljoin(BASE,html.unescape(image[1])) if image else None,'source_url':source_url,'entry_route':'public-best100-ranking','rank_scope':'observed_board_category_only','sales_count':None})
        query=parse_qs(urlparse(url).query)
        key=(m[1],(query.get('itemId') or [''])[0],(query.get('vendorItemId') or [''])[0])
        rows[-1].update(card_details(card,url,props.get(key,{})))
        if rows[-1]['rating'] is not None and not 0 <= rows[-1]['rating'] <= 5:
            rows[-1].update(rating_raw=rows[-1]['rating'],rating=None,rating_quality='source_out_of_range')
    return rows

def categories(body):
    found={}
    for cid,name in re.findall(r'href="/np/best100/(?:bestseller|trending)/(\d+)"[^>]*>(.*?)</a>',body,re.S):
        name=text(name)
        if name:found[cid]=name
    return [{'id':cid,'name':name} for cid,name in found.items()]

class PublicCatalogClient:
    def __init__(self, transport=None):
        if transport is None:
            from curl_cffi.requests import Session
            transport=Session(impersonate='chrome')
        self.transport=transport
    def ranking(self,board='bestseller',category='all'):
        if board not in ['bestseller','trending'] or (category!='all' and not str(category).isdigit()):raise ValueError('Invalid public ranking route')
        url=BASE+'np/best100/'+board+'/'+str(category)
        r=self.transport.get(url,headers={'referer':BASE,'accept-language':'ko-KR,ko;q=0.9'},timeout=15)
        body=r.text
        if r.status_code!=200 or re.search(r'Access Denied|sec-if-cpt-container|id="error403"',body):raise ValueError('Ranking response is blocked or unavailable')
        rows=parse_ranking(body,url)
        if not rows:raise ValueError('Ranking page has no verified product cards')
        return {'ok':True,'data':rows,'categories':categories(body),'source_url':url,'observed_at_kst':dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),'body_sha256':hashlib.sha256(body.encode()).hexdigest(),'html':body}
    def store(self,url_name):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',url_name):raise ValueError('Invalid store URL name')
        base='https://shop.coupang.com';referer=base+'/'+url_name;headers={'referer':referer,'origin':base,'accept':'application/json','content-type':'application/json'}
        r=self.transport.get(base+'/api/v1/store/getStoreInfo',params={'urlName':url_name},headers=headers,timeout=15)
        if r.status_code!=200:raise ValueError('Store metadata unavailable')
        info=r.json()
        if not isinstance(info,dict) or not info.get('id') or not info.get('vendorId'):raise ValueError('Invalid store metadata')
        r=self.transport.post(base+'/api/v1/listing',json={'storeId':info['id'],'vendorId':info['vendorId'],'enableAdultItemDisplay':False},headers=headers,timeout=15)
        if r.status_code!=200:raise ValueError('Store listing unavailable')
        payload=r.json();products=(payload.get('data') or {}).get('products')
        if not isinstance(products,list) or not products:raise ValueError('Store listing contained no observed products')
        return {'ok':True,'store_id':info['id'],'vendor_id':info['vendorId'],'source_url':referer,'data':products,'scope':'observed_first_listing_page_only'}


def main():
    import argparse
    from pathlib import Path
    from app.sourcing_pipeline import atomic_json
    parser=argparse.ArgumentParser(description='Observed public Coupang ranking, separate from keyword search')
    parser.add_argument('--board',choices=['bestseller','trending'],default='bestseller')
    parser.add_argument('--category',default='all')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        value=PublicCatalogClient().ranking(args.board,args.category)
    except Exception as exc:
        atomic_json(args.out.with_suffix('.error.json'),{'ok':False,'error':str(exc)})
        raise SystemExit(3)
    body=value.pop('html');args.out.parent.mkdir(parents=True,exist_ok=True)
    source=args.out.with_suffix('.source.html');source.write_text(body)
    value['source_file']=str(source);atomic_json(args.out,value)
    print(__import__('json').dumps({'ok':True,'products':len(value['data']),'source':value['source_url'],'out':str(args.out)}))

if __name__=='__main__':main()
