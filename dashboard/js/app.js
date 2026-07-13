const DATA_DIR = './data';

const state = {
  ranking: [],
  models: [],
  forecast: {},
  recommendations: [],
  sort: { key: 'priority_rank', dir: 'asc' },
};

async function fetchJSON(name) {
  const res = await fetch(`${DATA_DIR}/${name}`);
  if (!res.ok) {
    throw new Error(`Failed to load ${name}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

function badgeFor(action) {
  if (!action) return '<span class="badge badge--monitor">—</span>';
  if (action.startsWith('Clean now')) return `<span class="badge badge--clean-now">${action}</span>`;
  if (/^\d{4}-\d{2}-\d{2}$/.test(action)) return `<span class="badge badge--scheduled">${action}</span>`;
  if (action.startsWith('Stable / long')) return `<span class="badge badge--stable">${action}</span>`;
  if (action.startsWith('Stable')) return `<span class="badge badge--monitor">${action}</span>`;
  return `<span class="badge badge--monitor">${action}</span>`;
}

function fmtNum(v, digits = 3) {
  return (v === null || v === undefined || Number.isNaN(v)) ? '—' : Number(v).toFixed(digits);
}

function renderKPIs() {
  const bestModel = [...state.models].sort((a, b) => b['within_10C_%'] - a['within_10C_%'])[0];
  const topHx = [...state.recommendations].sort((a, b) => a.priority_rank - b.priority_rank)[0];
  const atRisk = state.recommendations.filter(r => r.at_risk_within_6mo).length;

  document.getElementById('kpi-best-model').textContent =
    bestModel ? `${bestModel.model} (${fmtNum(bestModel['within_10C_%'], 1)}% ±10°C)` : '—';
  document.getElementById('kpi-top-hx').textContent = topHx ? topHx.HX : '—';
  document.getElementById('kpi-at-risk').textContent = `${atRisk} / ${state.recommendations.length}`;
  document.getElementById('kpi-total-hx').textContent = state.ranking.length;
}

function sortedRecommendations() {
  const { key, dir } = state.sort;
  const mult = dir === 'asc' ? 1 : -1;
  return [...state.recommendations].sort((a, b) => {
    let va = a[key], vb = b[key];
    if (va === null || va === undefined) va = dir === 'asc' ? Infinity : -Infinity;
    if (vb === null || vb === undefined) vb = dir === 'asc' ? Infinity : -Infinity;
    if (typeof va === 'string') return va.localeCompare(vb) * mult;
    return (va - vb) * mult;
  });
}

function renderTable() {
  const tbody = document.getElementById('ranking-tbody');
  const rows = sortedRecommendations();
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td>${r.priority_rank ?? '—'}</td>
      <td><strong>${r.HX}</strong></td>
      <td>${fmtNum(r.priority_score)}</td>
      <td>${fmtNum(r.cit_shap_importance)}</td>
      <td>${fmtNum(r.Q_fouling_rate_abs, 5)}</td>
      <td>${r.effort_tier ?? '—'}</td>
      <td>${r.projected_clean_date ?? '—'}</td>
      <td>${badgeFor(r.recommended_action)}</td>
    </tr>
  `).join('');
}

function attachSortHandlers() {
  document.querySelectorAll('#ranking-table thead th').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.key;
      if (state.sort.key === key) {
        state.sort.dir = state.sort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        state.sort = { key, dir: 'asc' };
      }
      renderTable();
    });
  });
}

function renderShapChart() {
  const sorted = [...state.ranking].sort((a, b) => b.cit_shap_importance - a.cit_shap_importance);
  new Chart(document.getElementById('shap-chart'), {
    type: 'bar',
    data: {
      labels: sorted.map(r => r.HX),
      datasets: [{
        label: 'SHAP importance (Q-based features)',
        data: sorted.map(r => r.cit_shap_importance),
        backgroundColor: '#1b998b',
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { x: { title: { display: true, text: 'Aggregated |SHAP value|' } } },
    },
  });
}

function renderModelChart() {
  new Chart(document.getElementById('model-chart'), {
    type: 'bar',
    data: {
      labels: state.models.map(m => m.model),
      datasets: [{
        label: '% within ±10°C',
        data: state.models.map(m => m['within_10C_%']),
        backgroundColor: '#0b2545',
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: '% predictions within ±10°C' } } },
    },
  });

  const table = document.getElementById('model-table');
  const cols = ['model', 'R2', 'RMSE', 'MAE', 'MAPE_%', 'within_10C_%'];
  const header = `<thead><tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr></thead>`;
  const body = `<tbody>${state.models.map(m => `<tr>${cols.map(c => `<td>${typeof m[c] === 'number' ? fmtNum(m[c], 2) : m[c]}</td>`).join('')}</tr>`).join('')}</tbody>`;
  table.innerHTML = header + body;
}

let forecastChart = null;

function renderForecastChart(hx) {
  const series = state.forecast[hx];
  if (!series) return;

  const thresholdLine = series.dates.map(() => series.threshold);

  if (forecastChart) forecastChart.destroy();
  forecastChart = new Chart(document.getElementById('forecast-chart'), {
    type: 'line',
    data: {
      labels: series.dates,
      datasets: [
        {
          label: `${hx} projected deviation`,
          data: series.projected_deviation,
          borderColor: '#0b2545',
          backgroundColor: 'rgba(11,37,69,0.08)',
          pointRadius: 0,
          borderWidth: 2,
          fill: true,
        },
        {
          label: 'Cleaning threshold',
          data: thresholdLine,
          borderColor: '#c0392b',
          borderDash: [6, 4],
          pointRadius: 0,
          borderWidth: 1.5,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { ticks: { maxTicksLimit: 12 } },
        y: { title: { display: true, text: 'Fouling deviation' } },
      },
    },
  });
}

function populateHxSelect() {
  const select = document.getElementById('hx-select');
  const hxNames = Object.keys(state.forecast);
  select.innerHTML = hxNames.map(hx => `<option value="${hx}">${hx}</option>`).join('');
  const topHx = [...state.recommendations].sort((a, b) => a.priority_rank - b.priority_rank)[0];
  const defaultHx = (topHx && state.forecast[topHx.HX]) ? topHx.HX : hxNames[0];
  select.value = defaultHx;
  renderForecastChart(defaultHx);
  select.addEventListener('change', () => renderForecastChart(select.value));
}

async function init() {
  try {
    const [ranking, models, forecast, recommendations] = await Promise.all([
      fetchJSON('hx_ranking.json'),
      fetchJSON('model_metrics.json'),
      fetchJSON('forecast_6mo.json'),
      fetchJSON('cleaning_recommendations.json'),
    ]);
    state.ranking = ranking;
    state.models = models;
    state.forecast = forecast;
    state.recommendations = recommendations;

    renderKPIs();
    renderTable();
    attachSortHandlers();
    renderShapChart();
    renderModelChart();
    populateHxSelect();
  } catch (err) {
    document.querySelector('main').innerHTML =
      `<div class="panel"><strong>Failed to load dashboard data.</strong><br>${err.message}<br>
       Make sure you're serving this folder over HTTP (e.g. <code>python -m http.server</code> from
       <code>dashboard/</code>) rather than opening index.html directly via file://, and that
       6a/6b/6c notebooks have been run to populate <code>dashboard/data/</code>.</div>`;
    console.error(err);
  }
}

init();
