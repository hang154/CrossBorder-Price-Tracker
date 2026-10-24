import pytest
from app.upstream_first import observed_categories,validate_selections


def test_only_observed_official_categories_and_deduplicate():
    url='https://air.1688.com/kapp/1688-global/sales/search?keywords=Hardware'
    snapshot={'links':[{'text':'Hardware','href':url},{'text':'Duplicate','href':url},{'text':'Injected','href':url.replace('air.1688.com','evil.example')},{'text':'Other','href':'https://www.1688.com/'}]}
    rows=observed_categories(snapshot)
    assert len(rows)==1
    assert rows[0]['url']==url and rows[0]['status']=='queued'


def test_selection_requires_observed_id_and_exact_title_evidence():
    offers=[{'offer_id':'123','title':'Cotton cleaning cloth'}]
    valid={'offer_id':'123','query_ko':'면 청소 걸레','title_quote':'Cotton cleaning','comparison_traits':'material'}
    assert validate_selections([valid],offers,3)==[valid]
    for change in [{'offer_id':'999'},{'title_quote':'invented silk'},{'query_ko':''}]:
        with pytest.raises(ValueError):validate_selections([dict(valid,**change)],offers,3)
    with pytest.raises(ValueError):validate_selections([valid,valid],offers,3)
    with pytest.raises(ValueError):validate_selections([valid],offers,0)


def test_scoped_queries_require_observed_route_and_escape_query():
    from app.upstream_first import scoped_categories
    from urllib.parse import parse_qs,urlsplit
    observed=[{'url':'https://air.1688.com/kapp/1688-global/sales/search?keywords=tools'}]
    result=scoped_categories(observed,[{'label':'방풍 문풍지','keyword':'冬季 门窗 密封条'}])
    assert result[0]['derived_from_observed_url']==observed[0]['url']
    assert result[0]['taxonomy_level']=='user_scoped_search'
    assert parse_qs(urlsplit(result[0]['url']).query)['keywords']==['冬季 门窗 密封条']
    with pytest.raises(ValueError):scoped_categories([], [{'label':'winter','keyword':'winter'}])
    with pytest.raises(ValueError):scoped_categories(observed,[{'label':'','keyword':'winter'}])
