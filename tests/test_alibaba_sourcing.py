import json
import pytest
from app.models.product import detect_platform,extract_product_id
from app.scrapers import get_scraper
from app.scrapers.ali1688 import Ali1688Scraper
URL='https://www.alibaba.com/product-detail/Window-film_1601234567890.html'
def document(offers):
    return '<script type="application/ld+json">'+json.dumps({'@type':'Product','name':'Film','offers':offers})+'</script>'
def test_product_offer_and_identity():
    assert detect_platform(URL)=='alibaba'
    assert extract_product_id(URL,'alibaba')=='1601234567890'
    r=get_scraper('alibaba').parse_price(document({'price':'2.40','priceCurrency':'USD'}),URL)
    assert r.price==2.4 and r.currency=='USD'
    assert r.raw_data['scope']=='listing_only_not_landed_cost'
    assert not r.raw_data['availability_verified']
@pytest.mark.parametrize('offer',[{}, {'price':0,'priceCurrency':'USD'},{'price':'NaN','priceCurrency':'USD'},{'price':2},{'price':'Infinity','priceCurrency':'USD'}])
def test_no_fake_zero_or_unknown_currency_price(offer):
    assert get_scraper('alibaba').parse_price(document(offer),URL) is None
def test_challenge_not_a_price():
    assert get_scraper('alibaba').parse_price('<title>Verify</title>',URL) is None
    assert Ali1688Scraper().parse_price('<title>登录</title>','https://detail.1688.com/offer/123.html') is None
    assert Ali1688Scraper().parse_price('captcha "price":"2.00"','https://detail.1688.com/offer/123.html') is None
@pytest.mark.parametrize('url',['https://alibaba.com.evil.test/product-detail/Film_123.html','https://evil.test/?next=https://www.alibaba.com/product-detail/Film_123.html','https://1688.com.evil.test/offer/123.html'])
def test_wrong_host_not_imported(url):
    assert detect_platform(url)=='unknown'
    assert extract_product_id(url,'alibaba')==''
def test_aggregate_offer():
    r=get_scraper('alibaba').parse_price(document({'@type':'AggregateOffer','lowPrice':1.2,'highPrice':1.8,'priceCurrency':'USD'}),URL)
    assert r.price==1.2 and r.raw_data['offers']['highPrice']==1.8
