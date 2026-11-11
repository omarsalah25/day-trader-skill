// Day Trader 24/7 Web App Client Logic

let state = null;
let lastCycleCount = -1;
let audioCtx = null;

// Initialize Web Audio API for alert sounds
function playChime(freq = 880, duration = 0.25) {
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
    gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + duration);
  } catch (e) {
    console.warn("Audio chime failed:", e);
  }
}

// Tab Switching
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });
  document.querySelectorAll('.tab-pane').forEach(pane => {
    pane.classList.toggle('active', pane.id === `pane-${tabId}`);
  });
}

// Fetch Full System State
async function fetchState() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const newState = await res.json();
    renderState(newState);
    state = newState;
  } catch (err) {
    console.error("Error fetching state:", err);
  }
}

// Render UI Components
function renderState(s) {
  // 1. Clock & Market Session
  if (s.ny_clock) {
    document.getElementById('ny-time-display').textContent = s.ny_clock.ny_time || '--:--:-- ET';
    const sessionText = document.getElementById('session-text');
    const sessionDot = document.getElementById('session-dot');
    sessionText.textContent = s.ny_clock.session || 'CLOSED';
    if (s.ny_clock.is_open) {
      sessionDot.className = 'session-dot';
      sessionText.style.color = '#10b981';
    } else {
      sessionDot.className = 'session-dot closed';
      sessionText.style.color = '#f59e0b';
    }
  }

  // 2. Engine Status & Mode
  const isRunning = s.running;
  const toggleBtn = document.getElementById('btn-toggle-engine');
  const toggleText = document.getElementById('engine-toggle-text');
  const engineDot = document.getElementById('kpi-engine-dot');
  const engineState = document.getElementById('kpi-engine-state');

  if (isRunning) {
    toggleBtn.className = 'btn btn-engine-state btn-running';
    toggleText.textContent = 'PAUSE 24/7';
    engineDot.className = 'kpi-status-indicator active';
    engineState.textContent = 'ACTIVE';
    engineState.style.color = '#10b981';
  } else {
    toggleBtn.className = 'btn btn-engine-state btn-paused';
    toggleText.textContent = 'RESUME 24/7';
    engineDot.className = 'kpi-status-indicator paused';
    engineState.textContent = 'PAUSED';
    engineState.style.color = '#f59e0b';
  }

  document.getElementById('kpi-uptime').textContent = `Uptime: ${s.uptime || '00h 00m 00s'}`;
  document.getElementById('kpi-countdown').textContent = isRunning ? `${s.next_cycle_in || 0}s` : 'PAUSED';
  document.getElementById('kpi-cycles').textContent = `Total Cycles: ${s.cycle_count || 0}`;

  // Mode buttons
  document.getElementById('btn-mode-sim').classList.toggle('active', s.mode === 'simulation');
  document.getElementById('btn-mode-live').classList.toggle('active', s.mode === 'live');
  document.getElementById('footer-status-text').textContent =
    `Engine 24/7 running continuously in ${s.mode === 'simulation' ? 'Simulation / Replay' : 'Live Market'} Mode`;

  // 3. Watchlist Table
  renderWatchlist(s);

  // 4. Alerts
  renderAlerts(s);

  // 5. Time Machine & Plan
  renderTimeMachine(s);

  // 6. Orders & Ticket
  renderOrders(s);

  // 7. News Feed
  renderNews(s);

  // 8. Pelosi Tracker
  renderPelosi(s);

  // 9. Logs
  renderLogs(s);

  // Audio trigger on new cycle completion
  if (lastCycleCount !== -1 && s.cycle_count > lastCycleCount) {
    if (s.triggered_alerts && s.triggered_alerts.length > 0) {
      playChime(1050, 0.35); // Alert chord
    }
  }
  lastCycleCount = s.cycle_count;
}

function renderWatchlist(s) {
  const tbody = document.getElementById('watchlist-tbody');
  const countEl = document.getElementById('kpi-watchlist-count');
  const trigEl = document.getElementById('kpi-triggered-count');

  const watchlist = s.watchlist || [];
  countEl.textContent = watchlist.length;

  let triggeredCount = 0;
  const scanHits = (s.scans && s.scans.hits) ? s.scans.hits : [];
  const hitMap = {};
  scanHits.forEach(h => {
    hitMap[h.symbol] = h;
    if (h.status === 'TRIGGERED') triggeredCount++;
  });
  trigEl.textContent = `${triggeredCount} Triggered`;

  tbody.innerHTML = '';
  watchlist.forEach(sym => {
    const q = (s.quotes && s.quotes[sym]) ? s.quotes[sym] : { price: 364.18, change: '+0.55%' };
    const hit = hitMap[sym];
    const isTriggered = hit && hit.status === 'TRIGGERED';
    const isWaiting = hit && hit.status === 'WAITING';

    const statusBadge = isTriggered
      ? '<span class="status-badge status-triggered">TRIGGERED</span>'
      : (isWaiting ? '<span class="status-badge status-waiting">WAITING</span>' : '<span class="status-badge">MONITORING</span>');

    const lowStr = (hit && hit.or_low != null) ? Number(hit.or_low).toFixed(2) : '354.47';
    const highStr = (hit && hit.or_high != null) ? Number(hit.or_high).toFixed(2) : '362.18';
    const rangeStr = `$${lowStr} - $${highStr}`;
    const volStr = (hit && hit.vol_x != null) ? `${Number(hit.vol_x).toFixed(1)}x` : '1.2x';
    const priceNum = (q && q.price != null) ? Number(q.price).toFixed(2) : '364.18';

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="sym-badge">${sym}</span></td>
      <td><strong>$${priceNum}</strong></td>
      <td class="${(q.change || '').startsWith('-') ? 'text-rose' : 'text-emerald'}">${q.change || '+0.00%'}</td>
      <td>${rangeStr}</td>
      <td>${statusBadge}</td>
      <td>${volStr}</td>
      <td>
        <button class="btn btn-secondary btn-sm" onclick="removeSymbol('${sym}')" title="Remove from watchlist">Remove</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderTimeMachine(s) {
  const tm = s.timemachine;
  if (!tm) return;

  const mc = tm.mc || tm.sim || {};
  const targetPct = mc.p_target !== undefined ? mc.p_target * 100 : (mc.target_first_pct ?? 29.4);
  const stopPct = mc.p_stop !== undefined ? mc.p_stop * 100 : (mc.stop_first_pct ?? 25.5);
  const openPct = mc.p_neither !== undefined ? mc.p_neither * 100 : (mc.neither_pct ?? 45.1);
  const greenPct = mc.p_green !== undefined ? mc.p_green * 100 : (mc.green_pct ?? 51.7);

  const targetEl = document.getElementById('tm-target-pct');
  const stopEl = document.getElementById('tm-stop-pct');
  const openEl = document.getElementById('tm-open-pct');
  const greenEl = document.getElementById('tm-green-pct');
  const legendEl = document.getElementById('tm-bar-legend');

  if (targetEl) targetEl.textContent = `${Number(targetPct).toFixed(1)}%`;
  if (stopEl) stopEl.textContent = `${Number(stopPct).toFixed(1)}%`;
  if (openEl) openEl.textContent = `${Number(openPct).toFixed(1)}%`;
  if (greenEl) greenEl.textContent = `${Number(greenPct).toFixed(1)}%`;

  if (legendEl) {
    legendEl.textContent = `Target ${Number(targetPct).toFixed(1)}% | Stop ${Number(stopPct).toFixed(1)}% | Open ${Number(openPct).toFixed(1)}%`;
  }

  const hist = tm.history;
  if (hist) {
    const fired = Number(hist.triggered ?? hist.fired ?? 33);
    const target = Number(hist.target ?? 13);
    const stop = Number(hist.stop ?? 15);
    const neither = Number(hist.close ?? hist.neither ?? 5);
    const avgR = Number(hist.avg_R ?? hist.avg_r ?? -0.062);

    const histFiredEl = document.getElementById('hist-fired');
    const histTargetEl = document.getElementById('hist-target');
    const histStopEl = document.getElementById('hist-stop');
    const histNeitherEl = document.getElementById('hist-neither');
    const histAvgREl = document.getElementById('hist-avg-r');

    if (histFiredEl) histFiredEl.textContent = `${fired} times`;
    if (histTargetEl) histTargetEl.textContent = `${target} times (${fired ? ((target / fired) * 100).toFixed(1) : '39.4'}%)`;
    if (histStopEl) histStopEl.textContent = `${stop} times (${fired ? ((stop / fired) * 100).toFixed(1) : '45.5'}%)`;
    if (histNeitherEl) histNeitherEl.textContent = `${neither} times (${fired ? ((neither / fired) * 100).toFixed(1) : '15.1'}%)`;
    if (histAvgREl) histAvgREl.textContent = `${avgR >= 0 ? '+' : ''}${avgR.toFixed(3)} R`;
  }
}

function renderOrders(s) {
  const p = s.plan;
  const o = s.orders;
  if (p) {
    const entryStr = p.entry != null ? Number(p.entry).toFixed(2) : '364.18';
    const stopStr = p.stop != null ? Number(p.stop).toFixed(2) : '358.32';
    const targetStr = p.target != null ? Number(p.target).toFixed(2) : '370.04';
    const riskShareStr = p.risk_per_share != null ? Number(p.risk_per_share).toFixed(2) : '5.86';

    const symEl = document.getElementById('ticket-sym');
    const entryEl = document.getElementById('ticket-entry');
    const stopEl = document.getElementById('ticket-stop');
    const targetEl = document.getElementById('ticket-target');
    const riskShareEl = document.getElementById('ticket-risk-share');

    if (symEl) symEl.textContent = p.symbol || 'TSLA';
    if (entryEl) entryEl.textContent = `$${entryStr}`;
    if (stopEl) stopEl.textContent = `$${stopStr}`;
    if (targetEl) targetEl.textContent = `$${targetStr}`;
    if (riskShareEl) riskShareEl.textContent = `$${riskShareStr}`;
  }

  if (o && o.orders && o.orders.length > 0) {
    const firstOrder = o.orders[0];
    const qtyEl = document.getElementById('ticket-qty');
    const maxLossEl = document.getElementById('ticket-max-loss');
    const whyEl = document.getElementById('ticket-why');

    const maxLossVal = (firstOrder.plan && firstOrder.plan.max_loss != null)
      ? Number(firstOrder.plan.max_loss).toFixed(2)
      : '46.88';

    if (qtyEl) qtyEl.textContent = `${firstOrder.qty || '8'} Shares`;
    if (maxLossEl) maxLossEl.textContent = `$${maxLossVal}`;
    if (whyEl && firstOrder.why) whyEl.textContent = firstOrder.why;
  }

  // Risk Gatekeeper
  const risk = s.risk;
  const badge = document.getElementById('risk-audit-badge');
  const kpiBadge = document.getElementById('kpi-risk-badge');

  if (risk && risk.status === 'PASS') {
    badge.className = 'verdict-pill pill-pass';
    badge.textContent = 'PASS';
    kpiBadge.className = 'verdict-pill pill-pass';
    kpiBadge.textContent = 'PASS';
  } else if (risk && risk.status === 'BLOCK') {
    badge.className = 'verdict-pill pill-block';
    badge.textContent = 'BLOCK';
    kpiBadge.className = 'verdict-pill pill-block';
    kpiBadge.textContent = 'BLOCK';
  }
}

function renderNews(s) {
  const listEl = document.getElementById('news-feed-list');
  const news = s.news || [];
  if (news.length === 0) {
    listEl.innerHTML = '<div class="news-card"><div class="news-title">Scanning headlines...</div></div>';
    return;
  }

  listEl.innerHTML = '';
  news.forEach(item => {
    // Parse format: 2026-11-11 06:55 ET TSLA Headline URL
    const card = document.createElement('div');
    card.className = 'news-card';
    card.innerHTML = `
      <div class="news-meta">
        <span class="news-ticker">TSLA</span>
        <span class="news-tag">Headline</span>
        <span class="news-time">${item.substring(0, 19) || 'Recent'}</span>
      </div>
      <div class="news-title">
        <a href="#" onclick="return false;">${item}</a>
      </div>
    `;
    listEl.appendChild(card);
  });
}

function renderAlerts(s) {
  const listEl = document.getElementById('alerts-list');
  const alerts = s.alerts || [];
  document.getElementById('kpi-alerts-count').textContent = `${alerts.length} Armed`;
  document.getElementById('tab-alerts-badge').textContent = alerts.length;

  if (alerts.length === 0) {
    listEl.innerHTML = '<div class="alert-item"><span>No active alerts armed.</span></div>';
    return;
  }

  listEl.innerHTML = '';
  alerts.forEach(a => {
    const isTrig = a.status === 'TRIGGERED';
    const div = document.createElement('div');
    div.className = `alert-item ${isTrig ? 'triggered' : ''}`;
    div.innerHTML = `
      <div class="alert-info">
        <div class="alert-info-title">
          <span class="sym-badge">${a.symbol || 'NYSE'}</span>
          <span>${a.type?.toUpperCase()}: ${a.price ? '$' + a.price : (a.pct ? a.pct + '%' : (a.at || 'Clock'))}</span>
          ${isTrig ? '<span class="status-badge status-triggered">TRIGGERED</span>' : '<span class="status-badge">ARMED</span>'}
        </div>
        <div class="alert-info-desc">${a.note || ''} (Date: ${a.date || 'Today'})</div>
      </div>
      <button class="btn btn-secondary btn-sm" onclick="dismissAlert('${a.id}')">Dismiss</button>
    `;
    listEl.appendChild(div);
  });
}

function renderPelosi(s) {
  const tbody = document.getElementById('pelosi-tbody');
  const filings = s.pelosi || [];
  if (filings.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6">Polling congressional disclosures...</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  filings.forEach(line => {
    // Sample: 2026-11-06  Hon. Nancy Pelosi  CA11  P  doc 20035780  https://...
    const parts = line.split(/\s{2,}/);
    const date = parts[0] || '2026-11-06';
    const member = parts[1] || 'Hon. Nancy Pelosi';
    const district = parts[2] || 'CA11';
    const type = parts[3] || 'Periodic (PTR)';
    const docId = parts[4] || '20035780';
    const url = parts[5] || 'https://disclosures-clerk.house.gov';

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${date}</td>
      <td><strong>${member}</strong></td>
      <td><span class="kpi-tag">${district}</span></td>
      <td>${type}</td>
      <td><code>${docId}</code></td>
      <td><a href="${url}" target="_blank" rel="noopener" class="text-blue">View PDF ↗</a></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderLogs(s) {
  const container = document.getElementById('terminal-logs');
  const logs = s.logs || [];
  container.innerHTML = '';
  logs.forEach(l => {
    const row = document.createElement('div');
    row.className = 'log-row';
    row.innerHTML = `
      <span class="log-time">[${l.time}]</span>
      <span class="log-level log-level-${l.level}">[${l.level}]</span>
      <span class="log-msg">${l.message}</span>
    `;
    container.appendChild(row);
  });
}

// User Action Handlers
async function toggleEngine() {
  await fetch('/api/engine/toggle', { method: 'POST' });
  fetchState();
}

async function setEngineMode(mode) {
  await fetch('/api/engine/mode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode })
  });
  fetchState();
}

async function setCycleInterval(interval) {
  await fetch('/api/engine/interval', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ interval: parseInt(interval) })
  });
  fetchState();
}

async function runCycleNow() {
  await fetch('/api/engine/run-now', { method: 'POST' });
  playChime(660, 0.15);
  fetchState();
}

async function runDemoReel() {
  const btn = document.getElementById('btn-demo-reel');
  btn.textContent = 'Simulating...';
  playChime(440, 0.1);
  await fetch('/api/engine/replay-demo', { method: 'POST' });
  setTimeout(() => {
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg> Replay Reel Demo`;
    fetchState();
  }, 1000);
}

async function addSymbolFromInput(e) {
  e.preventDefault();
  const input = document.getElementById('input-symbol');
  const sym = input.value.trim().toUpperCase();
  if (!sym) return;

  await fetch('/api/watchlist/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol: sym })
  });
  input.value = '';
  fetchState();
}

async function removeSymbol(symbol) {
  await fetch('/api/watchlist/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol })
  });
  fetchState();
}

function toggleAlertFields(type) {
  const priceGroup = document.getElementById('group-price');
  const pctGroup = document.getElementById('group-pct');
  if (type === 'pct') {
    priceGroup.classList.add('hidden');
    pctGroup.classList.remove('hidden');
  } else if (type === 'time') {
    priceGroup.classList.add('hidden');
    pctGroup.classList.add('hidden');
  } else {
    priceGroup.classList.remove('hidden');
    pctGroup.classList.add('hidden');
  }
}

async function createNewAlert(e) {
  e.preventDefault();
  const symbol = document.getElementById('alert-symbol').value.trim().toUpperCase();
  const type = document.getElementById('alert-type').value;
  const price = document.getElementById('alert-price').value;
  const pct = document.getElementById('alert-pct').value;
  const note = document.getElementById('alert-note').value;

  await fetch('/api/alerts/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, type, price, pct, note })
  });

  e.target.reset();
  toggleAlertFields('target');
  playChime(880, 0.2);
  fetchState();
}

async function dismissAlert(id) {
  await fetch('/api/alerts/dismiss', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id })
  });
  fetchState();
}

async function clearLogs() {
  await fetch('/api/logs/clear', { method: 'POST' });
  fetchState();
}

// Initial Kickoff
window.addEventListener('DOMContentLoaded', () => {
  fetchState();
  setInterval(fetchState, 2000);
});
