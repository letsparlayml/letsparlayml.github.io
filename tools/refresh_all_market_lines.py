from __future__ import annotations
import argparse, os, subprocess, sys
from pathlib import Path

def run_step(cmd: list[str], label: str) -> None:
    print(f"\n[LINES] {label}")
    print("[LINES] CMD:", " ".join(f'"{c}"' if ' ' in c else c for c in cmd))
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        print(f"[LINES] ERROR ({rc}): {label}")
        raise SystemExit(rc)
    print(f"[LINES] OK: {label}")

def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh NBA/NHL/MLB API market lines for the site repo.")
    ap.add_argument("--root", default=r"C:\python")
    ap.add_argument("--website-repo", default=r"C:\python\letsparlayml.github.io")
    ap.add_argument("--python", dest="python_exec", default=sys.executable)
    ap.add_argument("--odds-api-key", default=os.environ.get("ODDS_API_KEY", ""))
    args = ap.parse_args()
    root = Path(args.root)
    repo = Path(args.website_repo)
    py = args.python_exec
    odds_fetch = repo / 'tools' / 'fetch_market_lines_the_odds_api.py'
    print("[LINES] ================================================")
    print(f"[LINES] SOURCE ROOT : {root}")
    print(f"[LINES] SITE REPO   : {repo}")
    print("[LINES] ================================================")
    print("[LINES] INFO: NBA/NHL/MLB odds are API-only from the cutover date forward.")
    print("[LINES] INFO: CBB refresh skipped (out of season).")
    print("[LINES] INFO: NHL manual adapter is disabled in this flow.")
    if not args.odds_api_key:
        print("[LINES] ERROR: ODDS_API_KEY not set. Cannot refresh API odds.")
        return 1
    if not odds_fetch.exists():
        print(f"[LINES] ERROR: unified odds fetch script not found: {odds_fetch}")
        return 1
    run_step([py, str(odds_fetch), '--api-key', args.odds_api_key, '--website-repo', str(repo)], 'Fetch NBA/NHL/MLB market lines from The Odds API')
    print('\n[LINES] Done.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
