from pathlib import Path
import pytest
from app.coupang_catalog_routes import parse_ranking,categories,PublicCatalogClient

CARD='''<a class="best100-product-cell" href="/vp/products/123?itemId=456&amp;vendorItemId=789"><img src="//thumbnail.coupangcdn.com/a.png"/><div class="ProductUnit_productNameV2__x">실리콘 &amp; 문풍지</div><del>30,000원</del><strong class="Price_priceValue__x">12,900원</strong><div class="ProductRating_productRating__x"><div aria-label="4.5"></div><span>(<!-- -->1,234<!-- -->)</span></div><p>최대 645원 적립</p></a>'''

def test_current_card_preserves_sale_price_ids_and_unknown_sales():
 r=parse_ranking(CARD,'https://www.coupang.com/np/best100/bestseller/all')[0]
 assert r['product_id']=='123' and r['price']==12900 and r['review_count']==1234 and r['rating']==4.5
 assert r['title']=='실리콘 & 문풍지' and r['sales_count'] is None
 assert r['url'].endswith('itemId=456&vendorItemId=789') and r['image_url'].startswith('https://thumbnail.')

def test_categories_dedupe_and_drop_non_numeric():
 assert categories('<a href="/np/best100/bestseller/42">침구</a><a href="/np/best100/trending/42">침구</a>')==[{'id':'42','name':'침구'}]

def test_recommendations_and_plain_links_are_not_ranked_cards():
 assert parse_ranking('<a href="/vp/products/1">추천</a>','x')==[]
 assert parse_ranking(CARD.replace('/vp/products/123','https://evil.example/vp/products/123'),'x')==[]

def test_duplicate_cards_and_missing_reviews():
 body=CARD.replace('ProductRating_productRating','ignored_rating')
 r=parse_ranking(body+body,'x');assert len(r)==1 and r[0]['review_count'] is None

@pytest.mark.parametrize('status,body',[(403,'Access Denied'),(200,'<div id="error403">blocked</div>'),(200,'<html>empty</html>')])
def test_transport_success_alone_is_not_collection_success(status,body):
 class Transport:
  def get(self,*a,**kw):return type('R',(),{'status_code':status,'text':body})()
 with pytest.raises(ValueError):PublicCatalogClient(Transport()).ranking()


def test_store_metadata_success_does_not_prove_listing_access():
 class Transport:
  def get(self,*a,**kw):
   return type('R',(),{'status_code':200,'json':lambda self:{'id':42,'vendorId':'A000001'}})()
  def post(self,*a,**kw):return type('R',(),{'status_code':403})()
 with pytest.raises(ValueError,match='listing unavailable'):PublicCatalogClient(Transport()).store('A000001')


def test_empty_store_listing_is_not_a_success():
 class Transport:
  def get(self,*a,**kw):
   return type('R',(),{'status_code':200,'json':lambda self:{'id':42,'vendorId':'A000001'}})()
  def post(self,*a,**kw):return type('R',(),{'status_code':200,'json':lambda self:{'data':{'products':[]}}})()
 with pytest.raises(ValueError,match='no observed products'):PublicCatalogClient(Transport()).store('A000001')


def test_badges_do_not_confuse_seller_rocket_with_standard_rocket():
 body=CARD.replace('<div class="ProductRating', '<img alt="판매자로켓" src="badge.png"/><div class="ProductRating')
 r=parse_ranking(body,'x')[0]
 assert r['rocket_badge_present'] is True and r['rocket_delivery_types']==['seller_rocket']
 assert r['rocket_delivery'] is True and r['free_shipping_observed'] is None
 assert r['item_id']=='456' and r['vendor_item_id']=='789'


def test_absent_badge_and_missing_shipping_are_unknown_not_ineligibility():
 r=parse_ranking(CARD,'x')[0]
 assert r['rocket_badge_present'] is False and r['rocket_delivery'] is None
 assert r['free_shipping_observed'] is None and r['seller_name'] is None


def test_matching_embedded_variant_keeps_returned_price_separate_from_sale():
 import json
 props={'index':{'title':'제품','itemId':456,'winnerVendorItemId':789},'legacyProductId':123,'vendorItemId':789,'priceArea':{'basePrice':'30,000','discountRate':57},'soldoutArea':{'soldout':False},'usedProductArea':{'usedProductInfo':[{'text':'반품 (2)'}],'usedProductPrice':[{'text':'최저 9,000원'}]},'adBadgeArea':{'sponsored':False}}
 script='<script>self.__next_f.push('+json.dumps([1,json.dumps(props,ensure_ascii=False)],ensure_ascii=False)+')</script>'
 r=parse_ranking(CARD+script,'x')[0]
 assert r['base_price']==30000 and r['discount_rate_percent']==57
 assert r['price']==12900 and r['used_or_returned_lowest_price']==9000
 assert r['sold_out'] is False and r['sponsored'] is False
 props['index']['itemId']=999
 script='<script>self.__next_f.push('+json.dumps([1,json.dumps(props)],ensure_ascii=False)+')</script>'
 r=parse_ranking(CARD+script,'x')[0]
 assert r['base_price'] is None and r['used_or_returned_lowest_price'] is None


def test_explicit_free_shipping_and_discount_are_observations_only():
 card=CARD.replace('<del>', '<span>무료배송</span><del class="PriceInfo_basePrice__x">').replace('<strong class="Price_priceValue', '<span class="PriceInfo_discountRate__x">57<!-- -->%</span><strong class="Price_priceValue')
 r=parse_ranking(card,'x')[0]
 assert r['base_price']==30000 and r['discount_rate_percent']==57 and r['free_shipping_observed'] is True


def test_product_title_is_not_shipping_evidence():
 fake=CARD.replace('<img src="//thumbnail.coupangcdn.com/a.png"/>','<figure><img src="//thumbnail.coupangcdn.com/a.png" alt="[무료배송] 문풍지 로켓배송"/></figure>').replace('실리콘 &amp; 문풍지','[5만원 이상 무료배송] 실리콘 문풍지')
 r=parse_ranking(fake,'x')[0]
 assert r['delivery_badges']==[] and r['free_shipping_observed'] is None
 assert r['rocket_delivery'] is None


def test_out_of_range_source_rating_is_preserved_but_not_used_as_valid_stars():
 r=parse_ranking(CARD.replace('aria-label="4.5"','aria-label="5.5"'),'x')[0]
 assert r['rating'] is None and r['rating_raw']==5.5 and r['rating_quality']=='source_out_of_range'
