#!/usr/bin/env python3
"""Run the existing local Qwen agent and merge requested comparison reports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, help='CrossBorder-Price-Tracker checkout; or SOURCING_REPO')
    p.add_argument('--opencli-main', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--include-report', type=Path, action='append', default=[])
    a = p.parse_args()
    repo = a.repo or (Path(os.environ['SOURCING_REPO']) if os.environ.get('SOURCING_REPO') else None)
    if repo is None:
        for parent in Path(__file__).resolve().parents:
            if (parent/'app/sourcing_agent.py').is_file():
                repo = parent
                break
    if repo is None or not (repo/'app/sourcing_agent.py').is_file():
        p.error('Provide --repo pointing to the existing CrossBorder-Price-Tracker checkout')
    repo = repo.resolve()
    out = a.output_dir.resolve()
    args = [sys.executable, '-m', 'app.sourcing_agent', '--config', str(a.config.resolve()),
            '--opencli-main', str(a.opencli_main.resolve()), '--output-dir', str(out)]
    if a.resume:
        args.append('--resume')
    run = subprocess.run(args, cwd=repo, check=False)
    reports = list(a.include_report)
    reports += sorted(out.glob('*/reviewed-report.json'))
    unique = {}
    for path in reports:
        path = path.resolve()
        data = json.loads(path.read_text())
        if not data.get('agent_product_id') or not isinstance(data.get('jobs'), list):
            raise ValueError('Expected a source-linked agent reviewed-report.json: '+str(path))
        product = data['agent_product_id']
        if product in unique and unique[product][1].read_bytes() != path.read_bytes():
            raise ValueError('Different reports for the same product require explicit selection: '+product)
        unique[product] = (data, path)
    if unique:
        sys.path.insert(0, str(repo))
        from app.sourcing_agent import render_html
        from app.sourcing_excel import export_workbook
        merged = out/'combined'
        merged.mkdir(exist_ok=True)
        values = list(unique.values())
        render_html([data for data, _ in values], merged/'index.html')
        exported = export_workbook([path for _, path in values], merged/'research.xlsx')
        manifest = {'agent_exit_code': run.returncode, 'products': list(unique), 'export': exported,
                    'source_reports': [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for _, path in values]}
        (merged/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({'html': str(merged/'index.html'), 'xlsx': str(merged/'research.xlsx'),
                          'product_count': len(unique), 'agent_exit_code': run.returncode}, ensure_ascii=False))
    return run.returncode


if __name__ == '__main__':
    raise SystemExit(main())
