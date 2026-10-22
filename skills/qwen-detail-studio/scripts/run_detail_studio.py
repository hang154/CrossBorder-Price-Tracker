#!/usr/bin/env python3
"""Invoke the maintained checkout; no credentials or dependencies embedded."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
p=argparse.ArgumentParser();p.add_argument('--repo',default=os.environ.get('SOURCING_REPO'));a,rest=p.parse_known_args()
repo=Path(a.repo).expanduser().resolve() if a.repo else next((x for x in [Path.cwd(),*Path.cwd().parents] if (x/'app/detail_studio.py').is_file()),None)
if repo is None or not (repo/'app/detail_studio.py').is_file():p.error('Pass --repo <CrossBorder-Price-Tracker checkout> or set SOURCING_REPO')
env=dict(os.environ);env['PYTHONPATH']=str(repo)+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
raise SystemExit(subprocess.run([sys.executable,'-m','app.detail_studio',*rest],cwd=repo,env=env).returncode)
