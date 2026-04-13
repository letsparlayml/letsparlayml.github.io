#!/usr/bin/env python3
from __future__ import annotations
import argparse
import glob
import json
from pathlib import Path
import pandas as pd


def latest_csv(pattern: str) -> str:
    matches = sorted(glob.glob(pattern))
    return matches[-1] if matches else ''


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MLB pitcher averages JSON for game detail page.")
    parser.add_argument("--predictions-file", default="")
    parser.add_argument("--mlb-output-dir", default=r"C:\python\mlb_model_outputs")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    pred_file = args.predictions_file or latest_csv(str(Path(args.mlb_output_dir) / 'pitcher_predictions_*.csv'))
    if not pred_file or not Path(pred_file).exists():
      print('[MLB AVG] No pitcher predictions file found. Skipping pitcher averages JSON build.')
      return 0

    out_path = Path(args.out) if args.out else Path(args.mlb_output_dir).parent / 'letsparlayml.github.io' / 'data' / 'mlb_pitcher_averages.json'
    df = pd.read_csv(pred_file)
    if df.empty:
      out_path.parent.mkdir(parents=True, exist_ok=True)
      out_path.write_text('{}', encoding='utf-8')
      print(f'[MLB AVG] Empty input. Wrote {out_path}')
      return 0

    def choose(row, *cols):
      for col in cols:
        if col in row and pd.notna(row[col]):
          return row[col]
      return None

    rows = {}
    for _, r in df.iterrows():
      pid = choose(r, 'player_id')
      name = str(choose(r, 'player_name', 'fullName') or '').strip()
      if not pid and not name:
        continue
      key = f'id:{int(pid)}' if pd.notna(pid) else f'name:{name.lower()}'
      avg_ip = None
      outs_r10 = choose(r, 'outs_r10')
      if pd.notna(outs_r10):
        avg_ip = round(float(outs_r10) / 3.0, 1)
      rows[key] = {
        'avgIP': avg_ip,
        'avgK': round(float(choose(r, 'strikeOuts_r10') or 0), 1) if pd.notna(choose(r, 'strikeOuts_r10')) else None,
        'avgBB': round(float(choose(r, 'baseOnBalls_r10') or 0), 1) if pd.notna(choose(r, 'baseOnBalls_r10')) else None,
        'avgHitsAllowed': round(float(choose(r, 'hits_allowed_r10') or 0), 1) if pd.notna(choose(r, 'hits_allowed_r10')) else None,
        'avgER': round(float(choose(r, 'earnedRuns_r10') or 0), 1) if pd.notna(choose(r, 'earnedRuns_r10')) else None,
      }
      if name:
        rows.setdefault(f'name:{name.lower()}', rows[key])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(f'[MLB AVG] Wrote {len(rows)} pitcher average lookups to {out_path}')
    return 0


if __name__ == '__main__':
  raise SystemExit(main())
