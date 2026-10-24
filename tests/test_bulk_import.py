import copy
import json
from pathlib import Path
from decimal import Decimal
import pytest
from app.bulk_import import freight_quote,cartons_measure,prepare_bulk,BULK_AMOUNTS,BULK_FLAGS
from app.rocket_margin import calculate
from tests.test_rocket_margin import inputs

@pytest.mark.parametrize('kg,price',[(1,6200),(1.2,7000),(5,12600),(10,20600)])
def test_basic_weight_rounding_and_domestic_inclusion(kg,price):
    q=freight_quote('next_basic',cbm=.01,kg=kg)
    assert q['known_subtotal']==price and q['domestic_delivery_included']
    assert not q['business_route_confirmed']
    assert q['vat_basis']=='unconfirmed_display_amount'

@pytest.mark.parametrize('cbm,ocean,handling',[(.1,8800,0),(.101,17600,0),(.2,17600,22000),(.5,44000,22000),(1,88000,22000)])
def test_lcl_tenth_cbm_and_per_bl_costs(cbm,ocean,handling):
    q=freight_quote('ssj_lcl',cbm=cbm,kg=10)
    assert q['charges']['ocean']==ocean
    assert q['known_subtotal']==ocean+22000+handling
    assert not q['domestic_delivery_included']

def test_handling_weight_boundary_co_and_volume_weight():
    assert freight_quote('ssj_lcl',cbm=.1,kg=20,co=True)['known_subtotal']==85800
    assert freight_quote('next_basic',cbm=.1,kg=1,volume_weight=True)['billed_kg']==7
    with pytest.raises(ValueError):freight_quote('next_basic',cbm=1,kg=11)
    with pytest.raises(ValueError):freight_quote('ssj_lcl',cbm=0,kg=1)

def complete():
    i,a,l=inputs();i['quantity_verified']=True;i['overseas']['moq_value']=100
    p={k:0 for k in BULK_AMOUNTS};p.update({k:True for k in BULK_FLAGS})
    p.update(route='ssj_lcl',selling_units=100,cartons=[dict(count=2,units_per_carton=50,length_cm=50,width_cm=50,height_cm=40,gross_kg=10)],customs_value_per_sale=1308,duty_rate=.08,wing_io=1250,wing_delivery=1500,fee_rate=.108,storage_daily=5,storage_free_days=30)
    return i,a,p

def test_carton_measurements_and_no_fake_complete_for_missing_data():
    i,a,p=complete();assert cartons_measure(p['cartons'])==dict(cbm=Decimal('.2'),kg=20,pieces=100)
    r=prepare_bulk(i,a,{'route':'ssj_lcl'})
    assert not r['ready'] and r['assumptions'] is None and r['freight'] is None
    assert prepare_bulk(i,a,p)['ready']

@pytest.mark.parametrize('change', ['moq','cartons','ratio','duty','co','domestic_duplicate'])
def test_invalid_business_plans_cannot_be_silently_accepted(change):
    i,a,p=complete()
    if change=='moq':i['overseas']['moq_value']=101
    if change=='cartons':p['cartons'][0]['units_per_carton']=49
    if change=='ratio':i['quantity_verified']=False
    if change=='duty':p['duty_confirmed']=False
    if change=='co':p.update(co=True,co_eligibility_confirmed=False)
    if change=='domestic_duplicate':
        p.update(route='next_basic',small_business_route_confirmed=True,center_inbound=1000)
        p['cartons']=[dict(count=1,units_per_carton=100,length_cm=50,width_cm=50,height_cm=40,gross_kg=5)]
    assert not prepare_bulk(i,a,p)['ready']

def test_complete_business_plan_reaches_margin_without_fake_vat_or_starting_fee_multiplier():
    i,a,p=complete();p.update(brokerage=33000,inspection=11000)
    a['bulk_plan']=p
    r=calculate(i,a,dict(io=1,delivery=1))
    lines={x['name']:x for x in r['ledger']}
    assert lines['international_freight']['cash']==616 # 17600 + DOC22000 + handling22000 /100
    assert lines['clearance']['cash']==330 and lines['clearance']['vat']==0
    assert lines['fulfillment_io']['net']==1250
    assert r['customs_value_proxy']==1308
    assert r['batch_units']==100
    assert r['import_vat']==Decimal('141.264')
    assert r['cash_contribution_before_vat']-r['vat_due_allocated']==r['operating_profit_after_vat']
    p['cartons']=None
    with pytest.raises(ValueError):calculate(i,a,dict(io=1,delivery=1))
