
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def pick_first(*paths: Path) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def run_step(cmd: list[str], label: str, warn_only: bool = False) -> bool:
    print(f"\n[LINES] {label}")
    print("[LINES] CMD:", " ".join(f'\"{c}\"' if ' ' in c else c for c in cmd))
    rc = subprocess.run(cmd).returncode
    if rc == 0:
        print(f"[LINES] OK: {label}")
        return True
    print(f"[LINES] {'WARN' if warn_only else 'ERROR'} ({rc}): {label}")
    if warn_only:
        return False
    raise SystemExit(rc)


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh NBA/CBB/NHL/MLB market lines for the site repo.")
    ap.add_argument("--root", default=r"C:\python")
    ap.add_argument("--website-repo", default=r"C:\Docs\letsparlayml.github.io")
    ap.add_argument("--mlb-out", default=r"C:\python\mlb_model_outputs")
    ap.add_argument("--python", dest="python_exec", default=sys.executable)
    ap.add_argument("--odds-api-key", default=os.environ.get("ODDS_API_KEY", ""))
    args = ap.parse_args()

    root = Path(args.root)
    repo = Path(args.website_repo)
    mlb_out = Path(args.mlb_out)
    py = args.python_exec
    if not repo.exists():
        print(f"[LINES] ERROR: website repo not found: {repo}")
        return 1

    update_lines = pick_first(root / 'update_market_lines_v2_fixed.py', root / 'update_market_lines_v2.py')
    odds_fetch = repo / 'tools' / 'fetch_market_lines_the_odds_api.py'

    print("[LINES] ================================================")
    print(f"[LINES] SOURCE ROOT : {root}")
    print(f"[LINES] SITE REPO   : {repo}")
    print(f"[LINES] MLB OUTPUTS : {mlb_out}")
    print("[LINES] ================================================")

    if update_lines:
        cmd = [py, str(update_lines), '--website-repo', str(repo), '--cbb-dir', str(root / 'cbb_data'), '--only-cbb']
        run_step(cmd, 'Refresh CBB market lines', warn_only=False)
    else:
        print('[LINES] WARN: update_market_lines_v2(.py) not found. Skipping CBB refresh.')

    if args.odds_api_key:
        if odds_fetch.exists():
            cmd = [
                py, str(odds_fetch),
                '--api-key', args.odds_api_key,
                '--website-repo', str(repo),
            ]
            run_step(cmd, 'Fetch NBA/NHL/MLB market lines from The Odds API', warn_only=False)
        else:
            print(f'[LINES] WARN: unified odds fetch script not found: {odds_fetch}')
    else:
        print('[LINES] INFO: ODDS_API_KEY not set. Skipping NBA/NHL/MLB odds fetch.')

    print('\n[LINES] Done.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
