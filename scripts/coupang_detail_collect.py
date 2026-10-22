"""Coupang 상품 상세 아카이브 수집기.

검색 job JSON(`{"products":[{product_id,rank,title,price,url}]}`)을 받아 각 상품의
`.product-detail-content` 원문 HTML·표시 텍스트·선택 옵션·원본 이미지를 저장한다.
이미지는 origin 검사(coupangcdn) 후 바이트·SHA-256·크기를 기록하고, 각 상품 폴더에 detail.json, detail-original.html.txt, description.txt, images/,
index.html로 남긴다. 차단(Akamai/접근제한) 상품은 status=failed 스캐폴더와 에러만
남기고 계속한다(정책: 제한 재시도는 상품당 1회).

필요: OpenCLI dist와 연결된 Chrome, 실행 위치는 자유롭지만 OpenCLI는 빌드되어 있어야 한다.

  python scripts/coupang_detail_collect.py --source job.json \
    --output-dir sourcing-runs/<new-run> --opencli-main ../OpenCLI/dist/src/main.js \
    --keyword 검색어 [--max 10]
"""
import argparse, datetime as dt, hashlib, html, io, json, sys, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import httpx
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.coupang_reviews import Browser, CollectionCoordinator, KST
from app.sourcing_pipeline import atomic_json

EXTRACT = r'''(() => {
 const d=document.querySelector('.product-detail-content');
 if (!d) return {error:'detail_content_missing',title:document.title};
 const product=location.pathname.match(/\/vp\/products\/(\d+)/)?.[1];
 const ld=[...document.querySelectorAll('script[type="application/ld+json"]')].flatMap(e=>{try{const v=JSON.parse(e.textContent);return Array.isArray(v)?v:v['@graph']||[v]}catch{return []}}).find(d=>d['@type']==='Product');
 const images=[...d.querySelectorAll('img')].map((e,i)=>({index:i+1,src:e.getAttribute('data-src')||e.getAttribute('src')||e.currentSrc,alt:e.alt||'',width:e.naturalWidth,height:e.naturalHeight}));
 const main=[...document.querySelectorAll('img')].find(e=>e.currentSrc?.includes('/492x492'));
 return {product_id:product,url:location.href,title:document.querySelector('h1')?.innerText||document.title,
 price:ld?.offers?.price??null,currency:ld?.offers?.priceCurrency??null,
 selected_options:document.querySelector('.option-picker-container')?.innerText||null,
 product_identifiers:document.querySelector('.product-description')?.innerText||null,
 mandatory_information:document.querySelector('#itemBrief')?.innerText||null,
 detail_text:d.innerText,detail_html:d.innerHTML,detail_images:images,
 main_image:main?{src:main.currentSrc,alt:main.alt}:null,
 videos:[...document.querySelectorAll('video,source,iframe')].map(e=>({tag:e.tagName,src:e.getAttribute('src')})),
 expanded:![...document.querySelectorAll('button')].some(e=>e.innerText.trim()==='상품정보 더보기')};
})()'''

class SafeHTML(HTMLParser):
    def __init__(self, images):
        super().__init__(convert_charrefs=True); self.images = images; self.parts = []; self.block = 0
    def handle_starttag(self, tag, attrs):
        if tag in ['script','style','iframe','object','video','svg']: self.block += 1; return
        if self.block: return
        a = dict(attrs)
        if tag == 'img':
            original = a.get('data-src') or a.get('src'); file = self.images.get(original)
            if file: self.parts.append('<img loading="lazy" src="'+html.escape(file,quote=True)+'" alt="'+html.escape(a.get('alt',''),quote=True)+'">')
            else: self.parts.append('<p class="missing">이미지 미확보</p>')
        elif tag in ['p','div','span','br','hr','strong','b','em','i','u','h1','h2','h3','h4','table','tbody','tr','td','th','ul','ol','li','blockquote']:
            self.parts.append('<'+tag+'>')
    def handle_endtag(self, tag):
        if tag in ['script','style','iframe','object','video','svg']: self.block = max(0,self.block-1); return
        if not self.block and tag in ['p','div','span','strong','b','em','i','u','h1','h2','h3','h4','table','tbody','tr','td','th','ul','ol','li','blockquote']: self.parts.append('</'+tag+'>')
    def handle_data(self, data):
        if not self.block: self.parts.append(html.escape(data))

def document(title, body):
    return ('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
     "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'\">"
     '<title>'+html.escape(title)+'</title>'
     '<style>body{font:16px/1.7 system-ui;max-width:1050px;margin:30px auto;padding:16px;background:#f5f6f8;color:#203344}article,section{background:white;padding:20px;margin:20px 0;border-radius:12px}img{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#176ca2}td,th{border:1px solid #ddd;padding:8px}.missing{color:#b45c00}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}.thumb{width:200px;max-height:240px;object-fit:contain}</style>'+body+'</html>')

def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--source', required=True, type=Path, help='검색 job JSON (products: [{product_id,rank,title,price,url}, ...])')
    p.add_argument('--output-dir', required=True, type=Path, help='신규런 폴더(신규 폴더 권장; 재실행 시 complete/partial 상품 자동 skip)')
    p.add_argument('--opencli-main', required=True, type=Path, help='OpenCLI dist/src/main.js 경로')
    p.add_argument('--keyword', default='', help='실행 식별용 검색어(파일명·매니페스트 기록)')
    p.add_argument('--max', type=int, default=10, help='최대 상품 수')
    p.add_argument('--workers', type=int, default=2, help='동시 브라우저 수(차단 재점화 방지를 위해 2 이하 권장)')
    return p.parse_args()

def main():
    args = parse_args()
    root = args.output_dir.resolve(); root.mkdir(parents=True, exist_ok=True)
    prefix = ['node', str(args.opencli_main.resolve())]
    source = args.source.resolve(); manifest_path = root/'manifest.json'
    state = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'results': []}
    done = {r['product_id'] for r in state['results'] if r.get('status') in ('complete', 'partial')}
    job_products = json.loads(source.read_text())['products'][:args.max]
    products = [p for p in job_products if str(p['product_id']) not in done]
    started = time.monotonic()
    coordinator = CollectionCoordinator(2, 'background')
    asset_pool = ThreadPoolExecutor(max_workers=6)
    client = httpx.Client(timeout=40, follow_redirects=True)
    def asset(entry, folder, index):
        original = entry.get('src') or ''
        u = urlsplit('https:'+original if original.startswith('//') else original)
        if u.scheme not in ['http','https'] or not u.hostname or not u.hostname.endswith('.coupangcdn.com'):
            return {'source_url': original, 'error': 'Unsupported image origin; URL retained'}
        url = urlunsplit(('https', u.netloc, u.path, u.query, ''))
        try:
            response = client.get(url); response.raise_for_status(); data = response.content
            with Image.open(io.BytesIO(data)) as im:
                width, height = im.size; fmt = im.format; im.verify()
            ext = {'JPEG':'jpg','PNG':'png','WEBP':'webp','GIF':'gif','AVIF':'avif'}.get(fmt,'img')
            file = f'images/{index:03d}.{ext}'; (folder/'images').mkdir(exist_ok=True); (folder/file).write_bytes(data)
            return {'source_url': original, 'requested_url': url, 'http_status': response.status_code, 'file': file,
                    'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'width': width, 'height': height, 'format': fmt}
        except Exception as exc:
            return {'source_url': original, 'requested_url': url, 'error': str(exc)}
    def one(product):
        folder = root/str(product['product_id']); folder.mkdir(exist_ok=True)
        result = {'product_id': str(product['product_id']), 'search_rank': product.get('rank'),
                  'search_title': product.get('title'), 'search_price': product.get('price'),
                  'product_url': f"https://www.coupang.com/vp/products/{product['product_id']}",
                  'source_job': str(source), 'session_kind': 'coupang_detail_collect'}
        coordinator.admit()
        b = Browser(prefix, 'cp-detail-'+str(product['product_id'])+'-'+uuid.uuid4().hex[:6], coordinator)
        try:
            b.call('open', product.get('url') or result['product_url'])
            ready = None
            for attempt in range(8):
                ready = b.call('eval', "(() => ({blocked:/access denied|captcha|접속이.*제한/i.test(document.title+' '+document.body.innerText.slice(0,1000)),detail:!!document.querySelector('.product-detail-content'),more:[...document.querySelectorAll('button')].some(e=>e.innerText.trim()==='상품정보 더보기')}))()")
                if ready['blocked']: coordinator.stopped.set(); raise ValueError('Access restriction detected')
                if ready['detail']: break
                time.sleep(.5)
            if ready and ready.get('more'): b.call('click','--role','button','--name','상품정보 더보기')
            data = b.call('eval', EXTRACT)
            if data.get('error') or str(data.get('product_id')) != str(product['product_id']): raise ValueError(str(data))
            if not data['expanded']: raise ValueError('Detail still collapsed')
            raw = data.pop('detail_html'); (folder/'detail-original.html.txt').write_text(raw)
            (folder/'description.txt').write_text(data['detail_text'])
            result.update(data, observed_at_kst=dt.datetime.now(KST).isoformat())
        except Exception as exc:
            result.update(status='failed', error=str(exc)); atomic_json(folder/'detail.json', result); return result
        finally:
            try: b.call('close')
            except Exception: pass
        entries = data['detail_images'] + ([data['main_image']] if data['main_image'] else [])
        unique = list({e['src']: e for e in entries if e.get('src')}.values())
        assets = [f.result() for f in [asset_pool.submit(asset, e, folder, i+1) for i, e in enumerate(unique)]]
        result['assets'] = assets
        local = {a['source_url']: a['file'] for a in assets if 'file' in a}
        safe = SafeHTML(local); safe.feed(raw); safe.close()
        result['status'] = 'complete' if len(local) == len(unique) and data['detail_images'] else 'partial'
        result['limitations'] = ['선택된 옵션의 상세페이지입니다. 모든 옵션을 각각 방문한 자료가 아닙니다.',
                                 '판매자 상세 설명의 주장과 효능은 검증하지 않았습니다.',
                                 '별도 동영상·iframe 자료는 URL만 기록합니다.']
        body = ('<a href="../index.html">← 목록</a><h1>'+html.escape(data['title'])+'</h1><p><a href="'+html.escape(data['url'],quote=True)+'">쿠팡 원본</a> · 검색 순위 '+str(product.get('rank'))+'</p>'
            +'<section><p>페이지 표시 가격: '+html.escape(str(data['price']))+' '+html.escape(str(data['currency']))+' · 검색 시 가격: '+str(product.get('price'))+'원</p>'
            +'<pre>'+html.escape(data['selected_options'] or '옵션 정보 미확인')+'</pre><pre>'+html.escape(data['mandatory_information'] or '')+'</pre>'
            +'<p>수집 '+result['observed_at_kst']+' · '+result['status']+'</p></section><article>'+''.join(safe.parts)+'</article>')
        (folder/'index.html').write_text(document(data['title'], body)); atomic_json(folder/'detail.json', result)
        print(json.dumps({'product_id': result['product_id'], 'status': result['status'], 'detail_images': len(data['detail_images']), 'downloaded': len(local), 'text_chars': len(data['detail_text'])}, ensure_ascii=False), flush=True)
        return result
    if products:
        results = []
        try:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for r in pool.map(one, products):
                    results.append(r)
                    state['results'] = [x for x in state['results'] if x['product_id'] != r['product_id']] + [r]
                    atomic_json(manifest_path, {**state, 'keyword': args.keyword, 'source_job': str(source),
                        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
        finally:
            asset_pool.shutdown(); client.close()
    state = json.loads(manifest_path.read_text())
    state.update(keyword=args.keyword, source_job=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                 elapsed_seconds=round(time.monotonic()-started,3))
    atomic_json(manifest_path, state)
    rows = []
    for r in sorted(state['results'], key=lambda r: r.get('search_rank') or 999):
        thumb = next((a['file'] for a in r.get('assets', []) if r.get('main_image') and a['source_url'] == r['main_image']['src'] and a.get('file')), None)
        rows.append('<section><h2>'+str(r.get('search_rank'))+'. <a href="'+r['product_id']+'/index.html">'+html.escape(r.get('title', r.get('search_title') or r['product_id']))+'</a></h2>'
            + (('<img class="thumb" src="'+r['product_id']+'/'+thumb+'">') if thumb else '')
            +'<p>'+r['status']+' · 상세 이미지 '+str(len(r.get('detail_images', [])))+'장 · <a href="'+r['product_id']+'/detail.json">원본 관측 JSON</a></p></section>')
    (root/'index.html').write_text(document((args.keyword or '쿠팡')+' 상세 아카이브', '<h1>'+html.escape(args.keyword or '쿠팡')+' 상세 아카이브</h1><p>원본 상세 설명의 텍스트·이미지를 저장했으며 판매자 주장의 사실 여부는 별도 검증하지 않았습니다. 페이지에 선택된 옵션 기준입니다.</p><div class="grid">'+''.join(rows)+'</div>'))
    print(json.dumps({'elapsed_seconds': state['elapsed_seconds'], 'statuses': [r['status'] for r in state['results']]}, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
