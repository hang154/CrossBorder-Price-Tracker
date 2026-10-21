"""Alibaba.com product-page structured prices. No guessed price or search API."""
import json
import math
from html.parser import HTMLParser
from .base import BaseScraper
from app.models.product import ScrapedProduct, extract_product_id

class _StructuredScripts(HTMLParser):
    def __init__(self):
        super().__init__(); self.active=False; self.current=[]; self.documents=[]
    def handle_starttag(self, tag, attrs):
        if tag=='script':
            self.active=dict(attrs).get('type','').lower()=='application/ld+json'; self.current=[]
    def handle_data(self, value):
        if self.active: self.current.append(value)
    def handle_endtag(self, tag):
        if tag=='script' and self.active:
            try: self.documents.append(json.loads(''.join(self.current)))
            except (ValueError,TypeError): pass
            self.active=False

def _products(value):
    if isinstance(value,list):
        for item in value: yield from _products(item)
    elif isinstance(value,dict):
        types=value.get('@type',[]);types=[types] if isinstance(types,str) else types
        if isinstance(types,list) and 'Product' in types: yield value
        yield from _products(value.get('@graph',[]))

class AlibabaScraper(BaseScraper):
    platform='alibaba'
    def scrape(self,url):
        html=self.fetch(url)
        return self.parse_price(html,url) if html else None
    def parse_price(self,html,url):
        pid=extract_product_id(url,self.platform)
        if not pid: return None
        parser=_StructuredScripts();parser.feed(html)
        for document in parser.documents:
            for product in _products(document):
                offers=product.get('offers',[])
                if isinstance(offers,dict): offers=[offers]
                if not isinstance(offers,list): continue
                for offer in offers:
                    if not isinstance(offer,dict): continue
                    currency=offer.get('priceCurrency','')
                    try: price=float(offer.get('price',offer.get('lowPrice')))
                    except (TypeError,ValueError): continue
                    if not math.isfinite(price) or price<=0 or currency not in {'USD','CNY','EUR','GBP','KRW','JPY','AUD','CAD','HKD'}: continue
                    return ScrapedProduct(url=url,platform=self.platform,product_id=pid,title=str(product.get('name','')),
                        price=price,currency=currency,in_stock='OutOfStock' not in str(offer.get('availability','')),
                        raw_data={'price_source':'product_json_ld','scope':'listing_only_not_landed_cost',
                                  'availability_verified':'availability' in offer,'offers':offer})
        return None
