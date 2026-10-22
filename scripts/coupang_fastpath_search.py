#!/usr/bin/env python3
"""Fast-HTTP Coupang search -> job JSON for the existing detail collector.

Gives the same `{"products":[...]}` input contract documented in
COUPANG_COLLECTION.md without starting Chrome: warm a curl_cffi surface at HOME,
fetch the SSR search page, and parse its embedded schema.org CollectionPage
(rank/title/price/rating/URL exactly as observed). Raises through
FastPathUnavailable when every surface is window-closed or the body does not
carry the real result markers, which is the executable hint to fall back to the
browser entry. Writes nothing on failure.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.coupang_fastpath import CoupangFastPath, FastPathUnavailable, search_products


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('keyword')
    ap.add_argument('--out', type=Path, required=True, help='job JSON 출력 경로(parent 자동 생성)')
    ap.add_argument('--limit', type=int, default=40)
    ap.add_argument('--page', type=int, default=1)
    ap.add_argument('--evidence', type=Path, default=None, help='JSONL ladder evidence 경로(권장)')
    args = ap.parse_args()
    path = CoupangFastPath(evidence_path=args.evidence)
    try:
        body = path.search_html(args.keyword, args.page)
    except FastPathUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 3
    rows = search_products(body)[:max(1, args.limit)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(__import__('json').dumps({'products': rows, 'keyword': args.keyword,
                                                  'source': 'fastpath-ssr-search', 'page': args.page},
                                                  ensure_ascii=False, indent=1))
    print(__import__('json').dumps({'ok': True, 'products': len(rows), 'out': str(args.out)}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
