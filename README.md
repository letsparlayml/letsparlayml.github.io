# Sports Predictions Showcase Starter Site

This is a lightweight starter website you can host for free on GitHub Pages.

## What is included

- `index.html` - home page with today's games, props, and recent results
- `game.html` - game detail page showing prediction movement across the week
- `data/` - JSON files that drive the site
- `scripts/build_site_data.py` - a minimal helper script you can adapt to convert your local CSVs into the JSON files used by the site

## Best no-cost setup

### Option 1: GitHub Pages (simplest)

1. Create a GitHub account if you do not already have one.
2. Create a new public repository named either:
   - `YOURUSERNAME.github.io` for a main site, or
   - any public repo name such as `sports-predictions-site` for a project site.
3. Upload these files to the repo.
4. In GitHub, go to **Settings -> Pages**.
5. Set the source to deploy from the `main` branch and the `/root` folder.
6. Save. GitHub will publish the site.

### Option 2: Cloudflare Pages

1. Push this folder to a GitHub repository.
2. In Cloudflare Pages, import the GitHub repo.
3. Use no build command and set the output directory to the repository root.
4. Deploy.

## How to update the site each day

1. Run your local model files.
2. Export the cleaned website-ready data.
3. Replace the JSON files in `data/`.
4. Commit and push the update.
5. The site refreshes automatically.

## Recommended repo structure

Use two repositories:

- **Private repo**: model code, raw data, scrapers, notebooks, anything you do not want public
- **Public repo**: only the website files and cleaned outputs you want shown publicly

## Suggested next changes for your real version

- replace the demo data in `data/games.json`, `data/props.json`, and `data/results.json`
- change the site title and colors
- add your record summary to the top section
- wire the helper script to your real CSV or Excel outputs
- later add separate pages for NBA, NHL, CBB if you want

## Notes on data shape

Each object in `games.json` includes a `movement` list. That is what powers the weekly movement chart and movement table.

Example game object fields:

- `id`
- `league`
- `gameDate`
- `awayTeam`
- `homeTeam`
- `marketSpread`
- `marketTotal`
- `modelAwayScore`
- `modelHomeScore`
- `modelHomeSpread`
- `modelTotal`
- `confidence`
- `summary`
- `movement` (list of daily prediction snapshots)

## Local preview

Open the folder in VS Code and use a local server extension, or run a basic local server:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000`.
