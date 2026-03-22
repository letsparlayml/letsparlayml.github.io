async function fetchJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}`);
  return res.json();
}

function gameCard(game) {
  const href = `game.html?id=${encodeURIComponent(game.id)}`;
  return `
    <a class="card-link" href="${href}">
      <article class="card">
        <div class="card-head">
          <span class="league-pill">${game.league}</span>
          <span class="game-date">${game.date}</span>
        </div>
        <h3>${game.awayTeam} @ ${game.homeTeam}</h3>
        <p class="pred-line">Model: ${game.modelAwayScore} - ${game.modelHomeScore}</p>
        <p class="market-line">Market: ${game.marketSpreadText || ""} ${game.marketTotalText || ""}</p>
        <p>${game.summary || ""}</p>
      </article>
    </a>
  `;
}

function propRow(prop) {
  return `
    <tr>
      <td>${prop.league || ""}</td>
      <td>${prop.game || ""}</td>
      <td>${prop.player || ""}</td>
      <td>${prop.stat || ""}</td>
      <td>${prop.line ?? ""}</td>
      <td>${prop.model ?? ""}</td>
      <td>${prop.edge ?? ""}</td>
      <td>${prop.note || ""}</td>
    </tr>
  `;
}

function resultRow(result) {
  return `
    <tr>
      <td>${result.league || ""}</td>
      <td>${result.matchup || ""}</td>
      <td>${result.predicted || result.pick || ""}</td>
      <td>${result.actual || ""}</td>
      <td>${result.status || ""}</td>
    </tr>
  `;
}

async function init() {
  const [site, games, props, results] = await Promise.all([
    fetchJson("data/site.json"),
    fetchJson("data/games.json"),
    fetchJson("data/props.json"),
    fetchJson("data/results.json"),
  ]);

  document.getElementById("site-title").textContent = site.title || "Sports Predictions";
  document.getElementById("site-subtitle").textContent =
    site.subtitle || "Daily model predictions and results";
  document.getElementById("last-updated").textContent =
    `Last updated: ${site.lastUpdated || ""}`;

  document.getElementById("games-grid").innerHTML = games.map(gameCard).join("");

  document.getElementById("props-body").innerHTML = props.map(propRow).join("");

  document.getElementById("results-body").innerHTML = results.map(resultRow).join("");
}

init().catch((err) => {
  console.error(err);
  const el = document.getElementById("games-grid");
  if (el) el.innerHTML = `<p>Failed to load site data.</p>`;
});
