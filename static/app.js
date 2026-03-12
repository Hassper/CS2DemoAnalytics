let killsChart;
let aimChart;
let currentMatchId = null;

const statusEl = document.getElementById('status');
const uploadForm = document.getElementById('uploadForm');
const playerSelect = document.getElementById('playerSelect');

uploadForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById('demoFile');
  if (!fileInput.files.length) return;

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  statusEl.textContent = 'Загрузка и анализ...';

  try {
    const uploadResp = await fetch('/api/upload', { method: 'POST', body: formData });
    const uploadData = await uploadResp.json();
    if (!uploadResp.ok) throw new Error(uploadData.detail || 'Upload failed');

    currentMatchId = uploadData.match_id;
    statusEl.textContent = uploadData.message;
    await loadMatch(currentMatchId);
  } catch (err) {
    statusEl.textContent = `Ошибка: ${err.message}`;
  }
});

playerSelect.addEventListener('change', async () => {
  if (!currentMatchId) return;
  await loadMatch(currentMatchId, playerSelect.value);
});

async function loadMatch(matchId, playerSteamId = null) {
  const query = playerSteamId ? `?player_steam_id=${encodeURIComponent(playerSteamId)}` : '';
  const resp = await fetch(`/api/matches/${matchId}${query}`);
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.detail || 'Failed to load match');

  currentMatchId = matchId;
  renderMatchInfo(data.match_info);
  renderPlayerSelector(data.players, data.selected_player);
  renderOverview(data.overview);
  renderEngagement(data.engagement_stats);
  renderCustomMetrics(data.custom_metrics);
  renderRoundTable(data.round_stats);
  renderCharts(data.charts, data.round_stats);
}

function renderMatchInfo(info) {
  const block = document.getElementById('matchInfo');
  block.innerHTML = '';
  const fields = {
    'Файл': info.demo_filename,
    'Карта': info.map_name,
    'Раундов': info.total_rounds,
    'Длительность (сек)': info.duration_seconds,
    'Источник данных': info.parse_source,
  };

  Object.entries(fields).forEach(([k, v]) => {
    const el = document.createElement('div');
    el.className = 'match-pill';
    el.innerHTML = `<strong>${k}</strong><div>${v}</div>`;
    block.appendChild(el);
  });
}

function renderPlayerSelector(players, selectedSteam) {
  playerSelect.innerHTML = '';
  players.forEach((player) => {
    const option = document.createElement('option');
    option.value = player.steam_id;
    option.textContent = `${player.name} (${player.steam_id})`;
    if (player.steam_id === selectedSteam) option.selected = true;
    playerSelect.appendChild(option);
  });
}

function renderOverview(overview) {
  const grid = document.getElementById('overviewGrid');
  grid.innerHTML = '';
  const keys = ['kills', 'deaths', 'assists', 'headshots', 'adr', 'accuracy', 'kd_ratio', 'damage_dealt', 'damage_taken', 'shots_fired', 'shots_hit'];

  for (const key of keys) {
    const card = document.createElement('div');
    card.className = 'metric-card';
    card.innerHTML = `<div>${key.replaceAll('_', ' ').toUpperCase()}</div><div class="metric-value">${Number(overview[key] ?? 0).toFixed(2)}</div>`;
    grid.appendChild(card);
  }
}

function renderEngagement(stats) {
  const body = document.querySelector('#engagementTable tbody');
  body.innerHTML = '';
  Object.entries(stats).forEach(([k, v]) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${k}</td><td>${v}</td>`;
    body.appendChild(tr);
  });
}

function renderCustomMetrics(custom) {
  const body = document.querySelector('#customMetricsTable tbody');
  body.innerHTML = '';
  Object.entries(custom).forEach(([k, v]) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${k}</td><td>${Number(v).toFixed(3)}</td>`;
    body.appendChild(tr);
  });
}

function renderRoundTable(rounds) {
  const body = document.querySelector('#roundStatsTable tbody');
  body.innerHTML = '';
  rounds.forEach((r) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${r.round}</td><td>${r.kills}</td><td>${r.damage}</td><td>${r.survival_time}</td>`;
    body.appendChild(tr);
  });
}

function renderCharts(charts, rounds) {
  const labels = rounds.map((r) => `R${r.round}`);

  if (killsChart) killsChart.destroy();
  killsChart = new Chart(document.getElementById('killsPerRoundChart'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label: 'Kills per Round', data: charts.kills_per_round, backgroundColor: '#38bdf8' }],
    },
  });

  if (aimChart) aimChart.destroy();
  aimChart = new Chart(document.getElementById('aimDistributionChart'), {
    type: 'doughnut',
    data: {
      labels: ['Aim Consistency', 'Aim Efficiency'],
      datasets: [{ data: charts.aim_score_distribution, backgroundColor: ['#22c55e', '#f59e0b'] }],
    },
  });
}
