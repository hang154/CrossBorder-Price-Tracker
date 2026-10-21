"""Resumable keyword -> domestic reference images -> overseas image search -> XLSX."""
import argparse
import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

import httpx
from app.sourcing import normalize_rows, image_provenance, browser_ready
from app.sourcing_excel import export_workbook


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atomic_json(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def compare_pair(pair, candidates, fx):
    """Explicit product IDs + units; never invent a visual match or unit count."""
    def side(name):
        spec = pair[name]
        rows = [r for r in candidates if r['platform'] == spec['platform'] and str(r['product_id']) == str(spec['product_id'])]
        if not rows:
            raise ValueError('Comparison product missing: ' + name)
        if len({(r.get('currency'), r.get('price')) for r in rows}) > 1:
            raise ValueError('Conflicting price observations require review: ' + name)
        r = rows[0]
        quantity = float(spec['units'])
        price = r.get('price')
        if not math.isfinite(quantity) or quantity <= 0 or isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            raise ValueError('Comparison requires positive units and observed price')
        rate = 1 if r['currency'] == 'KRW' else fx.get(r['currency'])
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
            raise ValueError('Explicit positive KRW exchange rate required')
        return r, r['price'] * rate / quantity
    if not pair.get('match_evidence') or not pair.get('limitations'):
        raise ValueError('Matching evidence and limitations required')
    d, dp = side('domestic')
    o, op = side('overseas')
    return {'category': pair['category'], 'domestic': d, 'overseas': o,
        'domestic_unit_count_assumed': pair['domestic']['units'], 'domestic_unit_price_krw': dp,
        'overseas_price_krw': op, 'difference_krw': dp-op, 'domestic_multiple': dp/op,
        'cheaper_percent': (1-op/dp)*100, 'match_evidence': pair['match_evidence'],
        'limitations': pair['limitations'], 'status': 'explicit_pair_not_identical_sku_certification'}


def fetch_reference(url, target):
    # Only marketplace CDN product images; no arbitrary local-network downloads.
    host = urlsplit(url).hostname or ''
    if urlsplit(url).scheme != 'https' or not any(host == h or host.endswith('.'+h) for h in ['pstatic.net', 'alicdn.com']):
        raise ValueError('Reference must be an HTTPS marketplace CDN image')
    data = bytearray()
    with httpx.stream('GET', url, timeout=30, follow_redirects=False) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > 10*1024*1024:
                raise ValueError('Image exceeds 10 MiB')
    ext = '.png' if data.startswith(bytes.fromhex('89504e470d0a1a0a')) else '.jpg' if data.startswith(bytes.fromhex('ffd8ff')) else '.webp' if data[:4] == b'RIFF' and data[8:12] == b'WEBP' else None
    if ext is None:
        raise ValueError('Unsupported reference image content')
    target = target.with_suffix(ext)
    target.write_bytes(data)
    return target, image_provenance(target)


def run_pipeline(config_path, out, prefix, resume=False, retry_failed=False):
    config = json.loads(Path(config_path).read_text())
    products = config['products']
    ids = [p['id'] for p in products]
    if len(ids) != len(set(ids)) or any(not x or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in x) for x in ids):
        raise ValueError('Product IDs must be unique safe filename identifiers')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    state_path = out/'report.json'
    fingerprint = digest({'config': config, 'prefix': prefix, 'pipeline_version': 1})
    if state_path.exists() and not resume:
        raise ValueError('Output already exists; use --resume or a fresh directory')
    state = json.loads(state_path.read_text()) if state_path.exists() else {'fingerprint': fingerprint, 'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'jobs': [], 'comparisons': [], 'comparison_errors': []}
    if state['fingerprint'] != fingerprint:
        raise ValueError('Configuration/CLI changed; use a fresh output directory')
    if not browser_ready(prefix)['ready']:
        raise ValueError('Existing browser extension is not connected')

    def checkpoint():
        state['updated_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        atomic_json(state_path, state)

    def collect(category, site, method, query, provenance=None):
        if method == 'image':
            query = Path(query).resolve()
        argv = [*prefix, 'naver-shopping' if site == 'naver' else site,
            'image-search' if method == 'image' else 'search', str(query), '--limit', str(config.get('limit', 8)), '-f', 'json']
        key = digest({'category': category, 'argv': argv, 'image': provenance})
        old = next((j for j in state['jobs'] if j['key'] == key), None)
        if old:
            if old['state'] == 'collected':
                raw = Path(old['output_file'])
                if not raw.exists() or hashlib.sha256(raw.read_bytes()).hexdigest() != old['response_sha256']:
                    raise ValueError('Saved response missing/changed: '+str(raw))
                return old['products']
            if not retry_failed:
                return []
        job = {'key': key, 'site': site, 'category': category, 'search_type': method, 'state': 'running', 'argv': argv, 'started_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'attempt': (old or {}).get('attempt', 0)+1}
        if old:
            job['previous_attempts'] = old.get('previous_attempts', []) + [{k:v for k,v in old.items() if k != 'previous_attempts'}]
            state['jobs'][state['jobs'].index(old)] = job
        else:
            state['jobs'].append(job)
        checkpoint()
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=config.get('timeout_seconds', 120), check=False)
            raw = out/(key+'.json')
            raw.write_text(r.stdout)
            job.update(exit_code=r.returncode, output_file=str(raw.resolve()), response_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
            payload = json.loads(r.stdout)
            if r.returncode:
                raise ValueError(str(payload.get('error', {}).get('message', 'OpenCLI failed')))
            rows = normalize_rows(site, payload)
            if provenance and (image_provenance(Path(query)) != provenance or any(r['search_type'] != 'image' or r['query_image_sha256'] != provenance['sha256'] for r in rows)):
                raise ValueError('Image changed or response lacks matching image provenance')
            job.update(state='collected', products=rows)
        except (ValueError, OSError, subprocess.TimeoutExpired) as e:
            job.update(state='failed', error=str(e))
        finally:
            job['finished_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            checkpoint()
        print(json.dumps({'category': category, 'site': site, 'method': method, 'state': job['state']}, ensure_ascii=False), flush=True)
        return job.get('products', [])

    for product in products:
        category = product['id']
        domestic = collect(category, 'naver', 'keyword', product['query_ko'])
        for site, lang in [('1688', 'zh'), ('alibaba', 'en')]:
            if product.get('query_'+lang):
                collect(category, site, 'keyword', product['query_'+lang])
        references = []
        for local in product.get('images', []):
            f = (Path(config_path).resolve().parent/local).resolve()
            references.append((f, image_provenance(f)))
        for i in product.get('domestic_image_indices', []):
            ref_path = out/(category+'-reference-'+str(i)+'.json')
            try:
                if ref_path.exists():
                    ref = json.loads(ref_path.read_text())
                    f = Path(ref['path'])
                    meta = image_provenance(f)
                    if meta != ref['provenance']:
                        raise ValueError('Saved reference image changed')
                else:
                    row = domestic[i]
                    f, meta = fetch_reference(row['image_url'], out/(category+'-reference-'+str(i)))
                    atomic_json(ref_path, {'path': str(f.resolve()), 'provenance': meta, 'source_listing': row})
                references.append((f, meta))
                state.get('reference_errors', {}).pop(category+':'+str(i), None)
            except (IndexError, KeyError, ValueError, OSError, httpx.HTTPError) as e:
                state.setdefault('reference_errors', {})[category+':'+str(i)] = str(e)
                checkpoint()
        for f, meta in references:
            for site in product.get('image_sites', ['1688', 'alibaba']):
                if site not in ['1688', 'alibaba']:
                    raise ValueError('Unsupported image marketplace')
                collect(category, site, 'image', f, meta)
    candidates = [r for j in state['jobs'] for r in j.get('products', [])]
    state['comparisons'] = []
    state['comparison_errors'] = []
    for pair in config.get('comparisons', []):
        try:
            state['comparisons'].append(compare_pair(pair, candidates, config.get('krw_per_currency', {})))
        except (KeyError, ValueError, TypeError) as e:
            state['comparison_errors'].append({'pair': pair, 'error': str(e)})
    checkpoint()
    summary = export_workbook([state_path], out/'research.xlsx')
    summary['complete'] = all(j['state'] == 'collected' for j in state['jobs']) and not state.get('reference_errors') and not state['comparison_errors']
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    e = sub.add_parser('export')
    e.add_argument('--report', action='append', required=True)
    e.add_argument('--output', type=Path, required=True)
    r = sub.add_parser('run')
    r.add_argument('--config', type=Path, required=True)
    r.add_argument('--output-dir', type=Path, required=True)
    r.add_argument('--opencli-main', type=Path)
    r.add_argument('--resume', action='store_true')
    r.add_argument('--retry-failed', action='store_true')
    c = sub.add_parser('compare', help='Apply reviewed IDs/units to saved observations without new searches')
    c.add_argument('--report', type=Path, required=True)
    c.add_argument('--pairs', type=Path, required=True)
    c.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    if a.action == 'export':
        result = export_workbook(a.report, a.output)
    elif a.action == 'compare':
        data = json.loads(a.report.read_text())
        config = json.loads(a.pairs.read_text())
        candidates = [r for j in data.get('jobs', []) for r in j.get('products', [])]
        if not candidates:
            raise ValueError('Saved job observations required')
        data['comparisons'] = [compare_pair(pair, candidates, config.get('krw_per_currency', {})) for pair in config['comparisons']]
        data['comparison_source_sha256'] = hashlib.sha256(a.report.read_bytes()).hexdigest()
        a.output_dir.mkdir(parents=True, exist_ok=True)
        dest = a.output_dir/'reviewed-report.json'
        if dest.resolve() == a.report.resolve():
            raise ValueError('Keep the original search report unchanged')
        atomic_json(dest, data)
        result = export_workbook([dest], a.output_dir/'research.xlsx')
    else:
        prefix = ['node', str(a.opencli_main.resolve())] if a.opencli_main else ['opencli']
        result = run_pipeline(a.config, a.output_dir, prefix, a.resume, a.retry_failed)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get('complete') is False else 0


if __name__ == '__main__':
    raise SystemExit(main())
