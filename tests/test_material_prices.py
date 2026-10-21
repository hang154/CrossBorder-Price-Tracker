from app.material_prices import rank, validate_item, canonical_material


def item(key, **changes):
    return {'key':key,'material':'호안석','material_quote':'호안석','unit':'single_bead','unit_quote':'낱알','size':'8mm','size_quote':'8mm','grade':'unspecified','grade_quote':'',**changes}


def row(key,price,currency='KRW'):
    return {'key':key,'price':price,'currency':currency,'moq':20,'url':'https://example.com/'+key,'title':'호안석 낱알 8mm','site':'1688'}


def test_minimum_never_combines_different_unit_size_grade_or_currency():
    rows=[row('a',100),row('b',80),row('c',1),row('d',2),row('e',3),row('f',0.01,'USD')]
    items=[item('a'),item('b'),item('c',unit='finished_bracelet'),item('d',size='6mm'),item('e',grade='7A'),item('f')]
    groups=rank(rows,items)
    comparable=next(g for g in groups if g['count']==2)
    assert comparable['winner_keys']==['b']
    assert comparable['minimum_listing_price']==80
    assert len(groups)==5


def test_ties_are_retained_and_unknown_size_does_not_claim_comparable_spec():
    groups=rank([row('a',80),row('b',80)],[item('a',size='unknown'),item('b',size='unknown')])
    assert groups[0]['winner_keys']==['a','b']
    assert groups[0]['status']=='size_unconfirmed'


def test_fabricated_unit_and_material_quotes_cannot_enter_ranking():
    value=validate_item(item('a',material_quote='순은',unit_quote='100개 묶음'),row('a',100))
    assert value['material']=='unknown'
    assert value['unit']=='unknown'
    assert rank([row('a',100)],[value])==[]


def test_material_mapping_uses_observed_claim_not_model_guess():
    v=validate_item(item('a',material='자단',material_quote='복숭아 나무'),{**row('a',100),'title':'복숭아 나무 팔찌'})
    assert v['material'].startswith('복숭아나무')
    assert '자단' not in v['material']
    assert canonical_material('은도금') != canonical_material('순은')
    assert canonical_material('Tiger Eye') == canonical_material('호랑이 눈 돌') == '호안석'
