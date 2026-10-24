"""Auditable sourcing-to-Rocket-Growth unit economics. No account/API access.

Inputs are estimates unless evidenced separately. Foreign purchase prices never
create Korean purchase-VAT credits. Only the explicit import-VAT ledger does.
The cash result includes expected-loss reserves and is not an actual WING payout.
"""
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING

D = lambda x: Decimal(str(x))
VAT = D('0.10')


def money(x):
    return D(x).quantize(D('.01'), rounding=ROUND_HALF_UP)


def nonnegative(x, name):
    value = D(x)
    if not value.is_finite() or value < 0:
        raise ValueError(f'{name} must be finite and nonnegative')
    return value


def rate(x, name, allow_one=True):
    value = nonnegative(x, name)
    if value > 1 or (not allow_one and value == 1):
        raise ValueError(f'{name} must be in [0,1{str("]" if allow_one else ")")}')
    return value


BATCH_COSTS = ('china_inland', 'sourcing_agent', 'international', 'insurance',
               'clearance', 'inspection', 'center_inbound')


def allocate_batch(total, items, basis='units'):
    """Allocate one consolidated shipment charge, preserving cents exactly.

    quantities are physical supplier pieces; unit_weight/volume/value are
    measured or explicitly supplied values, never guessed from category tags.
    """
    total = money(nonnegative(total, 'shipment total'))
    field = {'units': None, 'weight': 'unit_weight', 'volume': 'unit_volume',
             'value': 'unit_value'}.get(basis)
    if basis not in {'units', 'weight', 'volume', 'value'}:
        raise ValueError('Unknown shipment allocation basis')
    if not items or len({x['id'] for x in items}) != len(items):
        raise ValueError('Shipment must contain unique SKU IDs')
    weights = []
    for x in items:
        quantity = nonnegative(x['quantity'], 'shipment quantity')
        if quantity <= 0:
            raise ValueError('Shipment quantity must be positive')
        weight = quantity * (nonnegative(x[field], field) if field else 1)
        if weight <= 0:
            raise ValueError('Shipment allocation weights must be positive')
        weights.append(weight)
    denominator = sum(weights)
    # Largest-remainder allocation prevents negative residuals on small totals.
    raw = [total*w/denominator for w in weights]
    allocated = [x.quantize(D('.01'), rounding='ROUND_DOWN') for x in raw]
    cents = int((total-sum(allocated))*100)
    order = sorted(range(len(items)), key=lambda n: raw[n]-allocated[n], reverse=True)
    for n in order[:cents]:
        allocated[n] += D('.01')
    return {x['id']: allocated[n] for n, x in enumerate(items)}


def shipment_costs(item, assumption, ratio):
    shipment = assumption['shipment']
    basis = shipment['basis']
    sku = item.get('pair_id', 'single')
    inventory = nonnegative(assumption['batch_units'], 'batch_units')
    entries = shipment.get('items')
    if entries is None:
        # Each sourcing comparison is a SEPARATE hypothetical homogeneous lot.
        entries = [{'id': sku, 'quantity': inventory*ratio}]
        if basis != 'units':
            raise ValueError('Weight/volume allocation needs explicit shipment items')
    selected = next((x for x in entries if x['id'] == sku), None)
    if selected is None:
        raise ValueError('Current sourcing pair is missing from shipment items')
    physical_quantity = nonnegative(selected['quantity'], 'shipment quantity')
    if physical_quantity <= 0:
        raise ValueError('Shipment quantity must be positive')
    inventory = physical_quantity/ratio
    costs = {}; allocated = {}
    if set(shipment['totals']) != set(BATCH_COSTS):
        raise ValueError('Shipment totals must explicitly contain all batch cost fields')
    for name in BATCH_COSTS:
        allocated[name] = allocate_batch(shipment['totals'][name], entries, basis)[sku]
        costs[name] = allocated[name]/inventory
        if D(assumption.get(name, 0)) != 0:
            raise ValueError('Do not combine per-unit and batch shipment charges')
    return costs, dict(basis=basis, quote_status=shipment.get('quote_status', 'unverified'),
        shipment_totals=shipment['totals'], sku_allocated_totals=allocated,
        shipment_physical_units=sum(D(x['quantity']) for x in entries),
        sku_physical_units=physical_quantity, sku_selling_units=inventory,
        per_sale_costs=costs)


def calculate(item, assumption, logistics, *, credit_ratio=1, consumer_price=None):
    """Per retained sale. Returned-order outbound costs are separately reserved.

    Costs in assumption are KRW excluding Korean VAT unless explicitly stated.
    Returned orders are assumed to have their revenue/commission reversed; no
    extra revenue-return percentage is deducted from retained-sale revenue.
    """
    if 'bulk_plan' in assumption:
        from app.bulk_import import prepare_bulk
        prepared=prepare_bulk(item,assumption,assumption['bulk_plan'])
        if not prepared['ready']:
            raise ValueError('Incomplete bulk import: '+'; '.join(prepared['issues']))
        assumption=prepared['assumptions'];logistics=prepared['logistics']
    credit = rate(credit_ratio, 'credit_ratio')
    for key, value in assumption.items():
        if key not in {'fee_rounding', 'monthly_seller_units', 'settlement_delay_days', 'shipment', 'shipment_costs_gross'}:
            nonnegative(value, key)
    for key in ['fee_rate', 'ads_rate', 'return_rate', 'return_writeoff_fraction',
                'unsold_fraction', 'target_margin']:
        rate(assumption[key], key, allow_one=key not in {'return_rate', 'unsold_fraction'})
    a = {k: D(v) for k, v in assumption.items()
         if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)}
    price = nonnegative(consumer_price, 'consumer_price') if consumer_price is not None else (
        nonnegative(item['domestic']['price'], 'listed_price') * a['sale_factor'] - a['coupon'])
    if price <= 0:
        raise ValueError('Final consumer price after coupon must be positive')
    quantity = nonnegative(item['quantity_ratio_assumed'], 'quantity_ratio_assumed')
    if quantity == 0:
        raise ValueError('Quantity ratio must be positive; MOQ is not a pack size')
    foreign = nonnegative(item['overseas']['price_min'], 'foreign_price') * quantity * (1+a['purchase_buffer'])
    allocation = None
    if 'shipment' in assumption:
        costs, allocation = shipment_costs(item, assumption, quantity)
        a.update(costs)
    # Declared-price proxy, NOT a customs valuation or verified HS duty rate.
    customs_base = (nonnegative(assumption['customs_value_per_sale'], 'customs_value_per_sale')
                    if assumption.get('customs_value_per_sale') is not None else
                    foreign + a['china_inland'] + a['international'] + a['insurance'])
    duty = customs_base*a['duty_rate']
    import_vat = (customs_base+duty+a['other_import_taxes'])*VAT
    landed_cash = customs_base+duty+a['other_import_taxes']+import_vat
    lines = []

    def add(name, net, taxable=False, explicit_vat=0, group='operating', basis='scenario assumption'):
        net=money(net); vat=money(net*VAT if taxable else explicit_vat)
        deductible=money(vat*credit)
        lines.append(dict(name=name,net=net,vat=vat,cash=net+vat,
                          deductible_vat=deductible,profit_cost=net+vat-deductible,
                          group=group,basis=basis))

    add('overseas_goods', foreign, group='prepaid_inventory', basis='observed KRW representative variant × assumed ratio × buffer; no Korean purchase VAT')
    add('china_inland', a['china_inland'], group='prepaid_inventory')
    add('sourcing_agent', a['sourcing_agent'], group='prepaid_inventory')
    add('international_freight', a['international'], group='prepaid_inventory', basis='consolidated shipment allocated per selling unit; zero Korean VAT assumption' if allocation else 'explicit legacy per-unit freight assumption')
    add('insurance', a['insurance'], group='prepaid_inventory')
    add('customs_duty', duty, group='prepaid_inventory', basis='assumed CIF proxy × user-configurable duty; not HS verified')
    add('other_import_taxes', a['other_import_taxes'], group='prepaid_inventory')
    add('import_vat', 0, explicit_vat=import_vat, group='prepaid_inventory', basis='(assumed customs base + duty + other import taxes) ×10%; deduction conditional on documentation')
    for name in ['clearance','inspection','packaging','label','bundling','center_inbound']:
        add(name,a[name],taxable=not (assumption.get('shipment_costs_gross') and name in {'clearance','inspection','center_inbound'}),group='prepaid_inventory',basis='gross quotation; no VAT credit inferred' if assumption.get('shipment_costs_gross') and name in {'clearance','inspection','center_inbound'} else 'per selling-unit assumption')
    # Loss reserves include all prepaid preparation, not just CIF goods.
    landed_cash=sum(l['cash'] for l in lines if l['group']=='prepaid_inventory')
    fee=price*a['fee_rate']
    if assumption['fee_rounding']=='ceil_10':
        fee=(fee/10).to_integral_value(rounding=ROUND_CEILING)*10
    elif assumption['fee_rounding']=='round_won':
        fee=fee.quantize(D(1),rounding=ROUND_HALF_UP)
    else:
        raise ValueError('Unknown fee rounding; use round_won or ceil_10')
    add('commission',fee,True,group='platform',basis='final consumer price × assumed category rate; rounding '+assumption['fee_rounding'])
    io=nonnegative(logistics['io'], 'logistics.io')*a['logistics_multiplier']
    delivery=nonnegative(logistics['delivery'], 'logistics.delivery')*a['logistics_multiplier']
    add('fulfillment_io',io,True,group='platform',basis='public starting fee × scenario multiplier; package size not measured')
    add('customer_delivery',delivery,True,group='platform',basis='public starting fee × scenario multiplier; not a WING quote')
    paid_days=max(D(0),a['held_days']-a['storage_free_days'])
    add('storage',paid_days*a['storage_daily'],True,group='platform')
    returns_per_retained=a['return_rate']/(1-a['return_rate'])
    add('return_collection',returns_per_retained*a['return_collection'],True,group='platform')
    add('return_restock',returns_per_retained*a['return_restock'],True,group='platform')
    add('returned_order_outbound',returns_per_retained*(io+delivery),True,group='platform')
    add('return_damage_reserve',returns_per_retained*a['return_writeoff_fraction']*landed_cash,
        group='reserve',basis='expected inventory-value loss; gross landed basis, no assumed VAT deduction')
    unsold_per_sold=a['unsold_fraction']/(1-a['unsold_fraction'])
    add('unsold_inventory_reserve',unsold_per_sold*landed_cash,group='reserve')
    add('withdrawal',unsold_per_sold*a['withdrawal'],True,group='platform')
    add('disposal',unsold_per_sold*a['disposal'],True,group='platform')
    add('ads',price*a['ads_rate'],True,basis='spend excluding VAT / final consumer price; conditional input tax deduction')
    add('fixed_overhead',a['fixed_overhead'],False,group='overhead',basis='assumed allocated overhead; no input VAT assumed')
    total_cash=sum(l['cash'] for l in lines)
    credit_vat=sum(l['deductible_vat'] for l in lines)
    output_vat=price-price/(1+VAT)
    vat_due=output_vat-credit_vat
    cash_after_reserves=price-total_cash
    profit=cash_after_reserves-vat_due
    net_revenue=price-output_vat
    # Independent accrual ledger, reconciled before rounding final output.
    expense=sum(l['profit_cost'] for l in lines)
    if abs(profit-(net_revenue-expense)) > D('.0001'):
        raise ValueError('Cash/VAT/accrual reconciliation failed')
    ads=next(l for l in lines if l['name']=='ads')
    fixed=next(l for l in lines if l['name']=='fixed_overhead')
    pre_ad=profit+ads['profit_cost']
    max_ad=pre_ad/(1+VAT*(1-credit)) if pre_ad>0 else None
    target_budget=(pre_ad-net_revenue*a['target_margin'])/(1+VAT*(1-credit))
    upfront=sum(l['cash'] for l in lines if l['group']=='prepaid_inventory')
    inventory=allocation['sku_selling_units'] if allocation else nonnegative(assumption['batch_units'],'batch_units')
    result=dict(final_consumer_price=price,revenue_ex_vat=net_revenue,output_vat=output_vat,
                input_vat_deductible=credit_vat,vat_due_allocated=vat_due,
                estimated_platform_payout=price-sum(l['cash'] for l in lines if l['group']=='platform'),
                cash_contribution_before_vat=cash_after_reserves,
                contribution_after_vat_before_fixed=profit+fixed['profit_cost'],
                operating_profit_after_vat=profit,profit_before_ads_after_vat=pre_ad,
                margin_on_consumer_price=profit/price,margin_on_net_revenue=profit/net_revenue,
                max_ad_spend_ex_vat=max_ad,break_even_roas=price/max_ad if max_ad else None,
                target_ad_spend_ex_vat=max(D(0),target_budget),target_margin_reachable=target_budget>=0,
                target_roas=price/target_budget if target_budget>0 else None,
                actual_scenario_roas=price/ads['net'] if ads['net'] else None,
                import_vat=import_vat,duty=duty,customs_value_proxy=customs_base,
                initial_inventory_cash=inventory*upfront,batch_units=inventory,shipment_allocation=allocation,
                inventory_days=None,capital_recovery_days_excluding_settlement=None,
                capital_recovery_days_including_settlement=None,monthly_operating_profit=None,
                credit_ratio=credit,expected_returns_per_retained_sale=returns_per_retained,
                ledger=lines)
    monthly=assumption.get('monthly_seller_units')
    if monthly is not None:
        monthly=nonnegative(monthly,'monthly_seller_units')
        result['monthly_operating_profit']=monthly*profit
        if monthly>0:
            result['inventory_days']=inventory/monthly*30
            cash_in_per_sale=profit+upfront
            recover_units=inventory*upfront/cash_in_per_sale if cash_in_per_sale>0 else None
            if recover_units is not None and recover_units<=inventory*(1-a['unsold_fraction']):
                days=recover_units/monthly*30
                result['capital_recovery_days_excluding_settlement']=days
                delay=assumption.get('settlement_delay_days')
                if delay is not None:
                    result['capital_recovery_days_including_settlement']=days+nonnegative(delay,'settlement_delay_days')
    return result


def minimum_price(item, assumption, logistics, credit_ratio=1, target_margin=0):
    """Smallest integer FINAL (post-coupon) price under a fixed fee-tier assumption.

    A real price-category-dependent logistics tariff must be supplied separately.
    """
    target=rate(target_margin,'target_margin')
    def balance(price):
        r=calculate(item,assumption,logistics,credit_ratio=credit_ratio,consumer_price=price)
        return r['operating_profit_after_vat']-r['revenue_ex_vat']*target
    low,high=0,1000
    while balance(high)<0:
        high*=2
        if high>10**9: return None
    while high-low>1:
        mid=(high+low)//2
        if balance(mid)>=0: high=mid
        else: low=mid
    return high


def serializable(value):
    if isinstance(value,Decimal): return float(value.quantize(D('.000001'), rounding=ROUND_HALF_UP))
    if isinstance(value,dict): return {k:serializable(v) for k,v in value.items()}
    if isinstance(value,list): return [serializable(v) for v in value]
    return value
