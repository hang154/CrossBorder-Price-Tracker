#!/usr/bin/env python3
"""Locate the reusable repository client without embedding machine credentials."""
import argparse,os,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser(add_help=False);p.add_argument('--repo',type=Path)
a,remaining=p.parse_known_args()
repo=a.repo or (Path(os.environ['QWEN_IMAGE_REPO']) if os.environ.get('QWEN_IMAGE_REPO') else None)
if repo is None:
    for base in [Path.cwd(),*Path.cwd().parents,Path(__file__).resolve().parents[3]]:
        if (base/'scripts/qwen_image_client.py').is_file():repo=base;break
if repo is None:raise SystemExit('Supply --repo /path/to/CrossBorder-Price-Tracker or QWEN_IMAGE_REPO')
raise SystemExit(subprocess.call([sys.executable,str(repo/'scripts/qwen_image_client.py'),*remaining]))
