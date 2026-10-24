"""1688 -> China forwarder -> sea -> business import -> Rocket Growth.

Public tariff subtotals are not landed-cost quotes. Unknowns stay unknown.
No network access, guessed product weights, personal-import allowance or MOQ discounts.
"""
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING
from app.rocket_margin import D, money, nonnegative, BATCH_COSTS

SSJ_URL='https://www.ssjlog.com/Front/Page/DlvrMny_S.asp?sCenterSeq=5&sDlvrWayCd=3'
NEXT_URL='https://next1688.com/Front/Introduction/DlvrMny.asp?CTR_SEQ=2031&gMnu1=201&gMnu2=20107&sCbmYn=N'
# Observed BASIC entries for the specified China -> Incheon1 route only.
NEXT_BASIC={str(D(1)+D('.5')*i):6200+800*i for i in range(19)}


def positive(x,name):
    if x is None:raise ValueError(name+' is missing')
    v=nonnegative(x,name)
    if not v:raise ValueError(name+' must be positive')
    return v


def cartons_measure(cartons):
    if not cartons:raise ValueError('Packed master-carton measurements are required')
    cbm=kg=pieces=D(0)
    for c in cartons:
        count=positive(c['count'],'carton count')
        units=positive(c['units_per_carton'],'units per carton')
        if count!=count.to_integral_value() or units!=units.to_integral_value():
            raise ValueError('Carton counts and physical pieces must be integers')
        cbm+=count*positive(c['length_cm'],'length')*positive(c['width_cm'],'width')*positive(c['height_cm'],'height')/D(1000000)
        kg+=count*positive(c['gross_kg'],'carton gross weight')
        pieces+=count*units
    return dict(cbm=cbm,kg=kg,pieces=pieces)


def freight_quote(mode, *, cbm, kg, volume_weight=False, co=False,
                  small_business_route_confirmed=False):
    """Display-currency charges. VAT basis unspecified by public page: no credit inferred.

    Small parcel includes ordinary domestic delivery but not import brokerage,
    storage, oversize surcharge or business-route acceptance. LCL ends at CFS.
    """
    cbm=positive(cbm,'packed CBM');kg=positive(kg,'packed kg')
    if mode=='ssj_lcl':
        billed=(cbm/D('.1')).to_integral_value(rounding=ROUND_CEILING)*D('.1')
        ocean=money(billed*88000)
        lines=dict(ocean=ocean,doc=D(22000),handling=D(22000) if cbm>=D('.2') or kg>=20 else D(0),co=D(33000) if co else D(0))
        return dict(mode=mode,source=SSJ_URL,billed_cbm=billed,charges=lines,
            known_subtotal=sum(lines.values()),domestic_delivery_included=False,
            vat_basis='unconfirmed_display_amount',business_route_confirmed=True,
            excludes=['CFS release to Rocket Growth transport','customs broker quotation','duties and import VAT','optional inspection/packing/storage','heavy cargo surcharge if quoted'])
    if mode=='next_basic':
        bill_kg=max(kg,cbm*68) if volume_weight else kg
        bill_kg=max(D(1),(bill_kg*2).to_integral_value(rounding=ROUND_CEILING)/2)
        if bill_kg>10:raise ValueError('BASIC rate table pinned only through 10kg; obtain a quote above 10kg')
        price=NEXT_BASIC[str(bill_kg)] if str(bill_kg) in NEXT_BASIC else NEXT_BASIC[str(bill_kg.quantize(D('.1')))]
        return dict(mode=mode,source=NEXT_URL,billed_kg=bill_kg,charges=dict(parcel=D(price)),
            known_subtotal=D(price),domestic_delivery_included=True,
            vat_basis='unconfirmed_display_amount',business_route_confirmed=small_business_route_confirmed is True,
            excludes=['business customs acceptance and broker fees','oversize/remote/freight-carrier surcharge','taxes and customs storage','Rocket Growth appointment/handling or additional onward transport'])
    raise ValueError('Unknown sea route')


# Explicit 0 means verified/not applicable; null means missing, never free.
BULK_AMOUNTS=('china_inland','sourcing_agent','insurance','brokerage','destination_extra',
              'center_inbound','inspection','payment_fx_fee','certification_total','pallet_rework')
BULK_FLAGS=('supplier_price_confirmed','duty_confirmed','wing_fees_confirmed',
            'inbound_preparation_confirmed','tax_evidence_confirmed')


def prepare_bulk(item, assumption, plan):
    """Return executable assumptions only for a complete business-import plan.

    All explicit extra totals are cash/gross unless stated by this schema.
    Public combined transport has no invented VAT credit or invented CIF split.
    The customs value is explicitly supplied by the importer/broker.
    """
    problems=[];p=deepcopy(plan);metrics=quote=None
    for key in BULK_AMOUNTS:
        if p.get(key) is None:problems.append(key+' 미견적')
        else:nonnegative(p[key],key)
    for key in BULK_FLAGS:
        if p.get(key) is not True:problems.append(key+' 미확인')
    if not item.get('quantity_verified'):problems.append('국내 판매단위와 1688 구성 환산 미검증')
    try:
        units=positive(p.get('selling_units'),'selling units')
        if units!=units.to_integral_value():raise ValueError('Selling units must be integers')
        physical=units*positive(item['quantity_ratio_assumed'],'quantity ratio')
        if physical!=physical.to_integral_value():raise ValueError('Physical order quantity must be integral')
        metrics=cartons_measure(p.get('cartons'))
        if metrics['pieces']!=physical:problems.append('마스터박스 포장수량과 발주 실물수량 불일치')
        moq=item['overseas'].get('moq_value')
        if moq is None:problems.append('MOQ 미확인')
        elif physical<D(moq):problems.append('발주 수량이 MOQ 미달')
        quote=freight_quote(p['route'],cbm=metrics['cbm'],kg=metrics['kg'],
            volume_weight=p.get('volume_weight',False),co=p.get('co',False),
            small_business_route_confirmed=p.get('small_business_route_confirmed',False))
        if not quote['business_route_confirmed']:problems.append('소량 해운 사업자통관 수락 확인 필요')
    except (ValueError,KeyError,TypeError) as e:
        problems.append(str(e));units=None
    for key in ('customs_value_per_sale','duty_rate','wing_io','wing_delivery','fee_rate','storage_daily','storage_free_days'):
        if p.get(key) is None:problems.append(key+' 미확인')
        else:nonnegative(p[key],key)
    # Included basic domestic shipping and a second delivery to the same destination
    # must not both be charged. A real separate onward leg needs explicit evidence.
    if quote and quote['domestic_delivery_included'] and p.get('center_inbound',0) and not p.get('separate_onward_leg'):
        problems.append('국내배송 포함 운임과 센터운송 중복: 별도 구간 확인 필요')
    if p.get('co') and not p.get('co_eligibility_confirmed'):
        problems.append('CO 발급만으로 FTA 관세 자동 적용 불가')
    if problems:return dict(ready=False,issues=problems,metrics=metrics,freight=quote,assumptions=None)
    a=deepcopy(assumption);a.pop('bulk_plan',None);a['batch_units']=units
    totals=dict.fromkeys(BATCH_COSTS,D(0))
    for key in ('china_inland','sourcing_agent','insurance'):totals[key]=D(p[key])
    # Ocean + B/L + handling + optional CO: one conservative cash pool.
    totals['international']=quote['known_subtotal']+D(p['destination_extra'])
    # Cash VAT is not silently added on top of gross supplier/forwarder quotes.
    totals['clearance']=D(p['brokerage'])
    totals['inspection']=D(p['inspection'])+D(p['certification_total'])
    totals['center_inbound']=D(p['center_inbound'])+D(p['pallet_rework'])
    totals['sourcing_agent']+=D(p['payment_fx_fee'])
    for key in BATCH_COSTS:a[key]=0
    a['shipment']=dict(basis='units',quote_status='explicit_business_import_plan',totals=totals)
    a['shipment_costs_gross']=True
    a['customs_value_per_sale']=p['customs_value_per_sale']
    a['fee_rate']=p['fee_rate'];a['duty_rate']=p['duty_rate']
    a['logistics_multiplier']=1
    a['storage_daily']=p['storage_daily'];a['storage_free_days']=p['storage_free_days']
    return dict(ready=True,issues=[],metrics=metrics,freight=quote,assumptions=a,
                logistics=dict(io=p['wing_io'],delivery=p['wing_delivery']))
