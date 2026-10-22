import hashlib
import json

from openpyxl import load_workbook
import pytest

from app.sourcing_pipeline import atomic_json
from scripts.finalize_coupang_purchase_audit import finalize


def fixture_run(tmp_path):
    run = tmp_path / 'run'
    audit = run / 'virtual-audit'
    audit.mkdir(parents=True)
    atomic_json(run / 'queue.json', {'as_of': '2026-10-23', 'products': [dict(
        product_id='1', title='상품', price=1000, review_status='pending', detail_status='pending')]})
    source = tmp_path / 'results.json'
    atomic_json(source, {'items': [dict(pair_id='a', quantity_verified=False,
        domestic=dict(product_id='1', title='상품', url='https://www.coupang.com/vp/products/1'),
        scenarios={'base': {'estimated_profit': 100}})]})
    manifest = dict(as_of='2026-10-23', finished_at_kst='2026-10-23T05:00:00+09:00',
        source_sha256=hashlib.sha256((run / 'queue.json').read_bytes()).hexdigest(),
        profile_removed=True, virtual_display_removed=True, products={})
    atomic_json(audit / 'manifest.json', manifest)
    return run, source, manifest


def test_offline_finalize_is_repeatable_and_preserves_unknown_sales(tmp_path):
    run, source, _ = fixture_run(tmp_path)
    first = finalize(run, source)
    second = finalize(run, source)
    assert first['collection_is_complete'] is False
    assert second['monthly_sales_nonnull'] == 0
    wb = load_workbook(run / 'research.xlsx', data_only=True)
    assert wb.worksheets[0]['F2'].value is None
    assert len(wb.worksheets) == 3
    assert (run / 'virtual-audit/source-queue.json').exists()
    for name, expected in second['artifact_sha256'].items():
        assert hashlib.sha256((run / name).read_bytes()).hexdigest() == expected


def test_cleanup_failure_rejects_export_before_existing_report_changes(tmp_path):
    run, source, manifest = fixture_run(tmp_path)
    (run / 'index.html').write_text('existing report')
    manifest['profile_removed'] = False
    atomic_json(run / 'virtual-audit/manifest.json', manifest)
    original = (run / 'queue.json').read_bytes()
    with pytest.raises(ValueError, match='cleanup'):
        finalize(run, source)
    assert (run / 'index.html').read_text() == 'existing report'
    assert (run / 'queue.json').read_bytes() == original


def test_corrupt_archive_does_not_replace_existing_report(tmp_path):
    run, source, manifest = fixture_run(tmp_path)
    manifest['products'] = {'1': {'attempts': [], 'detail_status': 'partial'}}
    atomic_json(run / 'virtual-audit/manifest.json', manifest)
    detail = run / 'virtual-audit/details/1'
    detail.mkdir(parents=True)
    (detail / 'detail-original.html.txt').write_text('changed')
    atomic_json(detail / 'detail.json', dict(product_id='1', raw_html_sha256='wrong', assets=[]))
    (run / 'index.html').write_text('existing report')
    with pytest.raises(ValueError, match='Archive verification failed'):
        finalize(run, source)
    assert (run / 'index.html').read_text() == 'existing report'
