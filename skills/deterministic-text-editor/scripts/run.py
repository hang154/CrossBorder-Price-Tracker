#!/usr/bin/env python3
import argparse,os,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser(add_help=False);p.add_argument('--repo',type=Path,required=True);a,rest=p.parse_known_args()
raise SystemExit(subprocess.call([sys.executable,'-m','app.text_edit_agent',*rest],cwd=a.repo))
