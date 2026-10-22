"""쿠팡 상세 아카이브 무결성 재검증기.

수집 런 폴더(하나 이상)를 받아 다음을 대조한다:
- 이미지 파일 바이트의 SHA-256 vs detail.json assets 기록
- 원본 상세 HTML의 모든 http(s) 이미지·영상 src가 assets/videos/unsupported에 대응하는지
- description.txt == detail_text
- 만족 조건은 JSON 요약으로 출력,불일치는 목록으로 남긴다(exit 1).

  python scripts/coupang_archive_revalidate.py sourcing-runs/<run> [reports/<archive>/<run> ...]
"""
import json, re, sys, html as H
from pathlib import Path

def unescape_url(s):
    return 'https:'+s if s.startswith('//') else H.unescape(s)

def check_run(run: Path):
    ok_imgs = bad_imgs = 0; bad_files = []
    html_cover = html_total = 0; desc_ok = desc_total = 0; expanded = complete = 0
    for f in sorted(run.glob('*/detail.json')):
        d = json.loads(f.read_text())
        if d.get('status') not in ('complete', 'partial'): continue
        complete += 1
        folder = f.parent
        for a in d.get('assets', []):
            if 'file' not in a: continue
            p = folder/a['file']
            import hashlib
            if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == a.get('sha256'): ok_imgs += 1
            else: bad_imgs += 1; bad_files.append(str(p))
        raw = folder/'detail-original.html.txt'
        if raw.exists():
            html_total += 1
            listed = {unescape_url(a['source_url']) for a in d.get('assets', [])}
            videos = {unescape_url(v['src']) for v in d.get('videos', []) if v.get('src')}
            srcs = {unescape_url(m) for m in re.findall(r'(?:data-src|src)="([^"]+)"', raw.read_text()) if m.startswith(('http', '//'))}
            unsupported = {unescape_url(a['source_url']) for a in d.get('assets', []) if 'file' not in a}
            if srcs <= (listed | videos | unsupported): html_cover += 1
            else: bad_files.append((folder.name, sorted(srcs-(listed|videos|unsupported))[:3]))
        desc_total += 1
        if (folder/'description.txt').exists() and (folder/'description.txt').read_text() == (d.get('detail_text') or ''): desc_ok += 1
        if d.get('expanded'): expanded += 1
    checks = {'run': str(run), 'complete_or_partial': complete, 'images_sha_ok': ok_imgs,
              'images_sha_bad': bad_imgs, 'raw_html_fully_recorded': f'{html_cover}/{html_total}',
              'description_matches': f'{desc_ok}/{desc_total}', 'expanded_true': f'{expanded}/{complete}'}
    good = bad_imgs == 0 and html_cover == html_total and desc_ok == desc_total
    return good, checks, bad_files

if __name__ == '__main__':
    runs = [Path(a) for a in sys.argv[1:]]
    if not runs: print('usage: coupang_archive_revalidate.py <run-dir> [...]', file=sys.stderr); sys.exit(2)
    all_ok = True; checks = []
    for r in runs:
        good, c, bad = check_run(r); all_ok &= good; checks.append(c)
        if bad: checks.append({'run': str(r), 'problems': bad[:10]})
    print(json.dumps(checks, ensure_ascii=False, indent=1))
    sys.exit(0 if all_ok else 1)
