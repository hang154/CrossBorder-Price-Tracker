"""Evidence contracts for observed 1688 category -> offer -> Coupang discovery."""
from urllib.parse import urlsplit,parse_qs


def observed_categories(snapshot):
    result=[];seen=set()
    for link in snapshot.get('links',[]):
        u=urlsplit(link.get('href',''));q=parse_qs(u.query)
        if u.scheme!='https' or u.hostname!='air.1688.com' or u.path!='/kapp/1688-global/sales/search':continue
        keyword=(q.get('keywords') or [''])[0].strip();label=link.get('text','').strip()
        if not keyword or not label or keyword in seen:continue
        seen.add(keyword);result.append(dict(id=str(len(result)+1),label=label,keyword=keyword,url=link['href'],status='queued',taxonomy_level='observed_home_main_category'))
    return result


def validate_selections(selections,offers,limit):
    if len(selections)>limit:raise ValueError('Candidate selection exceeded configured sample')
    known={str(x['offer_id']):x for x in offers};seen=set()
    for p in selections:
        pid=p['offer_id']
        if pid not in known or pid in seen:raise ValueError('Use distinct observed offer IDs')
        if not p['query_ko'].strip() or len(p['query_ko'])>100:raise ValueError('Short Korean product query required')
        if not p.get('title_quote') or p['title_quote'] not in known[pid]['title']:raise ValueError('Exact observed title evidence required')
        seen.add(pid)
    return selections


def scoped_categories(observed, searches):
    """Derive explicit user-scoped queries from an observed official search route."""
    from urllib.parse import urlencode
    if not observed:
        raise ValueError('Observed 1688 search route required')
    result=[]
    for item in searches:
        keyword=item['keyword'].strip()
        if not keyword or not item['label'].strip():
            raise ValueError('Scope label and keyword required')
        result.append(dict(id=str(len(result)+1),label=item['label'],keyword=keyword,
            url='https://air.1688.com/kapp/1688-global/sales/search?'+urlencode({'keywords':keyword}),
            status='queued',taxonomy_level='user_scoped_search',
            derived_from_observed_url=observed[0]['url']))
    return result
