from pathlib import Path
import pytest
from app.purchase_opportunity_agent import validate_reviews, evaluate, SCENARIOS

REPO=Path(__file__).resolve().parents[2]/'research-agents/amazon-india-seller-mcp'

def pair():
 return dict(pair_id='a',previous_difference='',domestic=dict(group_id='w',group_name='시험',product_id='1',title='커버 2개',price=10000,review_count=100,rating=4.8),overseas=dict(title='커버',price_min=1000,moq_value=50))

def review():
 return dict(pair_id='a',match_type='comparable_function',unit_compatibility='requires_check',domestic_units=2,domestic_quantity_quote='2개',overseas_units=0,overseas_quantity_quote='',risk_traits=[],reason_ko='해외 구성 확인 필요')

def test_moq_never_becomes_quantity():
 p=pair(); a=review(); validate_reviews([a],[p]); r=evaluate([p],{'a':a},[p['domestic']],REPO,SCENARIOS)[0]
 assert r['quantity_ratio_assumed']==2
 assert not r['quantity_verified']
 assert r['monthly_sales'] is None
 assert r['scenarios']['base']['product_cost']==2300

@pytest.mark.parametrize('change',[{'domestic_units':True},{'domestic_units':2,'domestic_quantity_quote':'5개'},{'pair_id':'invented'},{'overseas_units':-1}])
def test_reject_invalid_model_arguments(change):
 a=review();a.update(change)
 with pytest.raises(ValueError): validate_reviews([a],[pair()])

def test_wrong_product_cannot_be_purchase_candidate():
 p=pair();a=review();a['match_type']='different_product'
 r=evaluate([p],{'a':a},[p['domestic']],REPO,SCENARIOS)[0]
 assert not r['eligible']
 assert r['decision']=='보류'

def test_independent_profit_and_stress_order():
 p=pair();a=review();r=evaluate([p],{'a':a},[p['domestic']],REPO,SCENARIOS)[0]
 base=r['scenarios']['base']
 expected=9500-2300-500-1140-3200-.05*(2300+500+4800)-2000-950
 assert base['estimated_profit']==pytest.approx(expected)
 assert r['scenarios']['stress']['estimated_profit']<base['estimated_profit']<r['scenarios']['optimistic']['estimated_profit']


def test_unknown_domestic_set_must_not_discount_foreign_three_piece_price():
 p=pair(); p['overseas']['title']='커버 3pcs'
 a=review();a.update(domestic_units=0,domestic_quantity_quote='',overseas_units=3,overseas_quantity_quote='3pcs')
 r=evaluate([p],{'a':a},[p['domestic']],REPO,SCENARIOS)[0]
 assert r['quantity_ratio_assumed']==1
 assert r['scenarios']['base']['product_cost']==1150
 assert not r['quantity_verified']


def test_single_item_needs_explicit_quantity_not_generic_title_word():
 from app.purchase_opportunity_agent import explicit_units
 a=review();a.update(overseas_units=1,overseas_quantity_quote='카펫')
 assert explicit_units(a,'overseas','욕실 카펫')==0
 a.update(overseas_quantity_quote='1개')
 assert explicit_units(a,'overseas','욕실 카펫 1개')==1
