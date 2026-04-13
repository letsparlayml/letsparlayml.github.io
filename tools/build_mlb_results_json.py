#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description='Temporary safe MLB results stub while launch gate is off.')
    parser.add_argument('--website-repo', default='.')
    parser.add_argument('--enable', action='store_true')
    parser.add_argument('--live-start-date', default='')
    _ = parser.parse_args()

    repo = Path(_.website_repo)
    launch_file = repo / 'data' / 'mlb_results_launch_date.txt'
    if not launch_file.exists() or not launch_file.read_text(encoding='utf-8').strip():
        print('[MLB RESULTS] Launch date not set. Skipping MLB results settlement.')
        return 0

    print('[MLB RESULTS] Launch date is set, but temporary safe stub is installed. Skipping settlement.')
    print('[MLB RESULTS] Replace build_mlb_results_json.py with the live settlement version when you are ready to enable MLB results.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
