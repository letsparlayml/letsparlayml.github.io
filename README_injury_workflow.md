# NBA injury workflow

1. Fill in `data/nba_injuries.xlsx` each day.
2. Run:
   `python tools/build_nba_injuries_json.py --website-repo C:\python\letsparlayml.github.io`
3. Commit and push:
   `git add data\nba_injuries.xlsx data\nba_injuries.json assets\app.js assets\props_lab.js assets\style.css index.html props_lab.html`
4. Push live.

Site behavior:
- Out / Doubtful: hidden from homepage props and props lab
- Questionable / Probable: kept visible, with a status badge on the site
