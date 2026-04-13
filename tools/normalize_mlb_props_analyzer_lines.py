#!/usr/bin/env python3
import argparse, json, math
from pathlib import Path

def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))

def poisson_sf_at_least(k, lam):
    if lam is None or lam < 0:
        return None
    n = int(math.floor(k))
    # P(X >= n+1) for line n+0.5
    cdf = 0.0
    for i in range(n + 1):
        cdf += math.exp(-lam) * (lam ** i) / math.factorial(i)
    return clamp(1.0 - cdf)

def line_set_for_stat(stat, mean, player_type='batter'):
    stat = str(stat or '').upper()
    if player_type == 'pitcher':
        if stat == 'K':
            center = mean if mean is not None else 5.0
            base = max(2.5, math.floor(center - 1.0) + 0.5)
            return [round(base + i, 1) for i in range(0, 4)]
        if stat in {'BB', 'HA', 'ER'}:
            center = mean if mean is not None else 2.0
            base = max(0.5, math.floor(center - 0.5) + 0.5)
            return [round(base + i, 1) for i in range(0, 3)]
        if stat in {'OUTS', 'IP'}:
            center = mean if mean is not None else 15.0
            if stat == 'IP':
                return [4.5, 5.5, 6.5]
            base = max(11.5, math.floor(center - 2.0) + 0.5)
            return [round(base + 1.0*i, 1) for i in range(0, 4)]
    # batter defaults
    if stat in {'H', 'BB', 'K'}:
        return [0.5, 1.5, 2.5]
    if stat == 'HR':
        return [0.5, 1.5]
    if stat == 'TB':
        return [1.5, 2.5, 3.5]
    if stat == 'HRR':
        return [0.5, 1.5, 2.5]
    if stat in {'RBI', 'R'}:
        return [0.5, 1.5, 2.5]
    if stat == 'SB':
        return [0.5, 1.5]
    return [0.5]

def pred_mean(entry):
    for key in ('pred_anchor','mu_cons','modelPrediction','average','avg_anchor','avg'):
        v = entry.get(key)
        if isinstance(v, (int,float)) and math.isfinite(v):
            return float(v)
        try:
            n = float(v)
            if math.isfinite(n):
                return n
        except:
            pass
    return None

def normalize_entries(entries):
    out = []
    for e in entries:
        stat = str(e.get('stat') or '').upper()
        player_type = str(e.get('playerType') or 'batter').lower()
        mean = pred_mean(e)
        lines = line_set_for_stat(stat, mean, player_type)
        if not lines:
            out.append(e)
            continue
        for line in lines:
            row = dict(e)
            row['line'] = line
            if mean is not None:
                prob = poisson_sf_at_least(line, mean)
                if prob is not None:
                    row['prob_cons'] = prob
                    row['probability'] = prob
            out.append(row)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--path', default='data/mlb_props_analyzer.json')
    args = ap.parse_args()
    path = Path(args.path)
    data = json.loads(path.read_text(encoding='utf-8'))
    entries = data.get('entries') or []
    data['entries'] = normalize_entries(entries)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(f'Normalized MLB analyzer lines -> {path} ({len(entries)} base entries -> {len(data["entries"])} expanded)')
if __name__ == '__main__':
    main()
