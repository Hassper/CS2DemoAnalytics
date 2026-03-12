let killsChart;
let aimChart;

const statusEl = document.getElementById('status');
const uploadForm = document.getElementById('uploadForm');

uploadForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById('demoFile');
  if (!fileInput.files.length) return;

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  statusEl.textContent = 'Uploading and analyzing...';

  try {
    const uploadResp = await fetch('/api/upload', { method: 'POST', body: formData });
    if (!uploadResp.ok) {
      const err = await uploadResp.json();
      throw new Error(err.detail || 'Upload failed');
    }
    const uploadData = await uploadResp.json();
    statusEl.textContent = uploadData.message;
    await loadMatch(uploadData.match_id);
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
});

async function loadMatch(matchId) {
  const resp = await fetch(`/api/matches/${matchId}`);
  const data = await resp.json();

  renderOverview(data.overview);
  renderCustomMetrics(data.custom_metrics);
  renderRoundTable(data.round_stats);
  renderCharts(data.charts, data.round_stats);
}

function renderOverview(overview) {
  const grid = document.getElementById('overviewGrid');
  grid.innerHTML = '';
  const keys = ['kills', 'deaths', 'adr', 'accuracy', 'kd_ratio', 'damage_dealt'];
  for (const key of keys) {
    const card = document.createElement('div');
    card.className = 'metric-card';
    card.innerHTML = `<div>${key.replace('_', ' ').toUpperCase()}</div><div class="metric-value">${Number(overview[key] ?? 0).toFixed(2)}</div>`;
    grid.appendChild(card);
  }
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
  rounds.forEach(r => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${r.round}</td><td>${r.kills}</td><td>${r.damage}</td><td>${r.survival_time}</td>`;
    body.appendChild(tr);
  });
}

function renderCharts(charts, rounds) {
  const labels = rounds.map(r => `R${r.round}`);

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
