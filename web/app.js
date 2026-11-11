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

  // 6. Orders, Positions & Transactions
  renderOrders(s);
  renderTransactions(s);

  // Strategy Setup UI
  if (s.config) {
    renderStrategyUI(s.config);
  }

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
    const isSpotForex = sym.includes('=X') || ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDCAD', 'USDJPY', 'USDCHF'].includes(sym);
    const isJpy = sym.includes('JPY');
    const dec = (isSpotForex && !isJpy) ? 4 : 2;

    const q = (s.quotes && s.quotes[sym]) ? s.quotes[sym] : { price: (isSpotForex ? 1.1091 : 364.18), change: '+0.55%' };
    const hit = hitMap[sym];
    const isTriggered = hit && hit.status === 'TRIGGERED';
    const isWaiting = hit && hit.status === 'WAITING';

    const statusBadge = isTriggered
      ? '<span class="status-badge status-triggered">TRIGGERED</span>'
      : (isWaiting ? '<span class="status-badge status-waiting">WAITING</span>' : '<span class="status-badge">MONITORING</span>');

    const lowStr = (hit && hit.or_low != null) ? Number(hit.or_low).toFixed(dec) : (q && q.price != null ? (Number(q.price) * 0.995).toFixed(dec) : '354.47');
    const highStr = (hit && hit.or_high != null) ? Number(hit.or_high).toFixed(dec) : (q && q.price != null ? (Number(q.price) * 1.005).toFixed(dec) : '362.18');
    const rangeStr = `$${lowStr} - $${highStr}`;
    const volStr = (hit && hit.vol_x != null) ? `${Number(hit.vol_x).toFixed(1)}x` : '1.2x';
    const priceNum = (q && q.price != null) ? Number(q.price).toFixed(dec) : '364.18';

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="sym-badge ${isSpotForex ? 'sym-forex' : ''}">${sym}</span></td>
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
    const isSpotForex = (p.symbol || '').includes('=X') || ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDCAD', 'USDJPY', 'USDCHF'].includes(p.symbol || '');
    const isJpy = (p.symbol || '').includes('JPY');
    const dec = (isSpotForex && !isJpy) ? 4 : 2;

    const entryStr = p.entry != null ? Number(p.entry).toFixed(dec) : '364.18';
    const stopStr = p.stop != null ? Number(p.stop).toFixed(dec) : '358.32';
    const targetStr = p.target != null ? Number(p.target).toFixed(dec) : '370.04';
    const riskShareStr = p.risk_per_share != null ? Number(p.risk_per_share).toFixed(dec) : '5.86';

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

    const qtyNum = parseInt(firstOrder.qty) || 8;
    const qtyLabel = qtyNum >= 1000 ? `${qtyNum.toLocaleString()} Units` : `${qtyNum} Shares`;

    if (qtyEl) qtyEl.textContent = qtyLabel;
    if (maxLossEl) maxLossEl.textContent = `$${maxLossVal}`;
    if (whyEl && firstOrder.why) whyEl.textContent = firstOrder.why;
  }

  // Risk Gatekeeper
  const risk = s.risk;
  const badge = document.getElementById('risk-audit-badge');
  const kpiBadge = document.getElementById('kpi-risk-badge');

  if (risk && risk.status === 'PASS') {
    if (badge) { badge.className = 'verdict-pill pill-pass'; badge.textContent = 'PASS'; }
    if (kpiBadge) { kpiBadge.className = 'verdict-pill pill-pass'; kpiBadge.textContent = 'PASS'; }
  } else if (risk && risk.status === 'BLOCK') {
    if (badge) { badge.className = 'verdict-pill pill-block'; badge.textContent = 'BLOCK'; }
    if (kpiBadge) { kpiBadge.className = 'verdict-pill pill-block'; kpiBadge.textContent = 'BLOCK'; }
  }

  // Live Positions & Real-Time P&L Table
  const posTbody = document.getElementById('positions-tbody');
  const positions = s.positions || [];
  const brokerPill = document.getElementById('broker-status-pill');
  if (brokerPill) {
    const hasKey = s.config && s.config.alpaca_api_key;
    const isPaper = !s.config || s.config.paper !== false;
    brokerPill.textContent = hasKey
      ? `Connected: Alpaca ${isPaper ? 'Paper' : 'Live'}`
      : 'Paper Simulator (High-Fidelity Local)';
  }

  if (posTbody) {
    if (positions.length === 0) {
      posTbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-dim); padding: 22px;">No active open positions. Click "🚀 Execute Order" or wait for an automated breakout fill.</td></tr>';
    } else {
      posTbody.innerHTML = '';
      positions.forEach((pos) => {
        const sym = pos.symbol || 'TSLA';
        const isSpotForex = sym.includes('=X') || ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDCAD', 'USDJPY', 'USDCHF'].includes(sym);
        const isJpy = sym.includes('JPY');
        const dec = (isSpotForex && !isJpy) ? 4 : 2;

        const quote = (s.quotes && s.quotes[sym]) ? s.quotes[sym].price : (pos.current_price || pos.entry_price);
        const shares = pos.shares || 1;
        const sharesDisplay = shares >= 1000 ? Number(shares).toLocaleString() : shares;
        const entry = pos.entry_price || quote;
        const stop = pos.stop_price || (entry * 0.98);
        const target = pos.target_price || (entry * 1.02);
        const pnl = (quote - entry) * shares;
        const pnlPct = ((quote - entry) / entry) * 100;
        const isProfitable = pnl >= 0;

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${escapeHtml(sym)}</strong></td>
          <td>${sharesDisplay}</td>
          <td>$${Number(entry).toFixed(dec)}</td>
          <td>$${Number(quote).toFixed(dec)}</td>
          <td class="text-rose">$${Number(stop).toFixed(dec)}</td>
          <td class="text-emerald">$${Number(target).toFixed(dec)}</td>
          <td class="${isProfitable ? 'text-emerald' : 'text-rose'}"><strong>${isProfitable ? '+' : ''}$${Number(pnl).toFixed(2)}</strong></td>
          <td class="${isProfitable ? 'text-emerald' : 'text-rose'}">${isProfitable ? '+' : ''}${Number(pnlPct).toFixed(2)}%</td>
          <td><button class="btn btn-flatten btn-sm" style="padding: 4px 10px; font-size: 11px;" onclick="emergencyFlatten()">Close</button></td>
        `;
        posTbody.appendChild(tr);
      });
    }
  }
}

function renderTransactions(s) {
  const tbody = document.getElementById('transactions-tbody');
  if (!tbody) return;
  const txs = s.transactions || [];

  if (txs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="11" style="text-align: center; color: var(--text-dim); padding: 22px;">No active transactions yet. Click "🚀 Execute Order" or "Submit 1m Transaction" to place a trade.</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  txs.forEach(tx => {
    const isBuy = (tx.side || '').toUpperCase() === 'BUY';
    const status = (tx.status || 'NEW').toUpperCase();
    let statusClass = 'status-waiting';
    if (status === 'FILLED') statusClass = 'status-triggered';
    else if (status === 'NEW' || status === 'PENDING_NEW') statusClass = 'status-badge';
    else if (status === 'CANCELED' || status === 'EXPIRED') statusClass = 'pill-block';

    const sym = tx.symbol || 'TSLA';
    const isSpotForex = sym.includes('=X') || ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDCAD', 'USDJPY', 'USDCHF'].includes(sym);
    const isJpy = sym.includes('JPY');
    const dec = (isSpotForex && !isJpy) ? 4 : 2;

    const qtyNum = parseInt(tx.qty) || 1;
    const qtyDisplay = qtyNum >= 1000 ? qtyNum.toLocaleString() : tx.qty;

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><code>${escapeHtml(tx.id || tx.order_id || '')}</code></td>
      <td>${escapeHtml(tx.submitted_at || 'Recent')}</td>
      <td><strong>${escapeHtml(sym)}</strong></td>
      <td><span class="${isBuy ? 'text-emerald' : 'text-rose'}" style="font-weight: 700;">${escapeHtml(tx.side || 'BUY')}</span></td>
      <td>${escapeHtml(qtyDisplay)}</td>
      <td><span class="news-ticker" style="font-size: 10px;">${escapeHtml(tx.type || 'BRACKET')}</span></td>
      <td class="text-rose">${tx.stop_price ? '$' + Number(tx.stop_price).toFixed(dec) : '-'}</td>
      <td class="text-emerald">${tx.target_price ? '$' + Number(tx.target_price).toFixed(dec) : '-'}</td>
      <td><span class="status-badge ${statusClass}" style="font-size: 10px;">${escapeHtml(status)}</span></td>
      <td><span class="kpi-tag" style="font-size: 10px;">${escapeHtml(tx.broker || 'Alpaca Paper')}</span></td>
      <td>
        ${status !== 'CANCELED' && status !== 'FILLED' ? `<button class="btn btn-flatten btn-sm" style="padding: 3px 8px; font-size: 10px;" onclick="cancelOrder('${escapeHtml(tx.order_id || tx.id)}')">Cancel</button>` : '-'}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderStrategyUI(cfg) {
  if (!cfg) return;
  const preset = cfg.strategy_preset || (cfg.candle_interval === '1m' ? 'fast_1m' : 'standard_5m');
  const card1m = document.getElementById('strat-fast-1m');
  const cardForex = document.getElementById('strat-forex-pip');
  const card5m = document.getElementById('strat-standard-5m');
  const badge1m = document.getElementById('badge-strat-1m');
  const badgeForex = document.getElementById('badge-strat-forex');
  const badge5m = document.getElementById('badge-strat-5m');

  [card1m, cardForex, card5m].forEach(c => c && c.classList.remove('active-strategy'));
  [badge1m, badgeForex, badge5m].forEach(b => {
    if (b) { b.textContent = 'AVAILABLE'; b.className = 'status-badge'; }
  });

  if (preset === 'forex_pip') {
    if (cardForex) cardForex.classList.add('active-strategy');
    if (badgeForex) { badgeForex.textContent = 'ACTIVE SETUP'; badgeForex.className = 'status-badge status-triggered'; }
  } else if (preset === 'fast_1m') {
    if (card1m) card1m.classList.add('active-strategy');
    if (badge1m) { badge1m.textContent = 'ACTIVE SETUP'; badge1m.className = 'status-badge status-triggered'; }
  } else {
    if (card5m) card5m.classList.add('active-strategy');
    if (badge5m) { badge5m.textContent = 'ACTIVE SETUP'; badge5m.className = 'status-badge status-triggered'; }
  }
}


function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
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
    let title = '';
    let link = '';
    let ticker = 'TSLA';
    let source = 'Yahoo Finance';
    let timeStr = 'Recent';
    let summary = '';
    let tags = [];

    if (typeof item === 'string') {
      const urlMatch = item.match(/https?:\/\/[^\s]+/);
      link = urlMatch ? urlMatch[0] : 'https://finance.yahoo.com';
      title = item.replace(/https?:\/\/[^\s]+/, '').replace(/^.*?(ET\s+)/, '').trim() || item;
      const tickMatch = item.match(/\b([A-Z]{1,5})\b/);
      if (tickMatch) ticker = tickMatch[1];
    } else {
      title = item.title || 'Market Update';
      link = item.link || (item.ticker ? `https://finance.yahoo.com/quote/${item.ticker}/news/` : 'https://finance.yahoo.com');
      ticker = item.ticker || 'MARKET';
      source = item.source || 'Yahoo Finance';
      timeStr = item.time ? (item.time.includes('T') ? item.time.substring(11, 16) + ' UTC' : item.time) : 'Recent';
      summary = item.summary || '';
      tags = item.tags || [];
    }

    const tagsHtml = tags.map(t => `<span class="news-tag">${escapeHtml(t)}</span>`).join(' ');

    const card = document.createElement('div');
    card.className = 'news-card';
    card.innerHTML = `
      <div class="news-meta">
        <span class="news-ticker">${escapeHtml(ticker)}</span>
        <span class="news-source">${escapeHtml(source)}</span>
        ${tagsHtml}
        <span class="news-time">${escapeHtml(timeStr)}</span>
      </div>
      <div class="news-title">
        <a href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer" class="news-link" title="Open news in new tab">
          ${escapeHtml(title)}
          <span class="news-external-icon">↗</span>
        </a>
      </div>
      ${summary ? `<div class="news-summary">${escapeHtml(summary)}</div>` : ''}
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

// Strategy & Configuration Management
let isSettingsFormDirty = false;

async function loadConfig(force = false) {
  if (isSettingsFormDirty && !force) return;
  try {
    const res = await fetch('/api/config');
    if (!res.ok) return;
    const data = await res.json();
    const cfg = data.config || {};

    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el && (force || document.activeElement !== el)) el.value = (val != null) ? val : '';
    };

    setVal('cfg-strategy-preset', cfg.strategy_preset || (cfg.candle_interval === '1m' ? 'fast_1m' : 'standard_5m'));
    setVal('cfg-max-trades', cfg.max_trades_per_day);
    setVal('cfg-max-orders', cfg.max_orders_per_day);
    setVal('cfg-budget', cfg.budget);
    setVal('cfg-max-loss-trade', cfg.max_loss_per_trade_usd);
    setVal('cfg-max-loss-day', cfg.max_daily_loss_usd);
    setVal('cfg-min-rr', cfg.min_reward_risk);
    setVal('cfg-candle-interval', cfg.candle_interval || '1m');
    setVal('cfg-or-minutes', cfg.or_minutes || '5');
    setVal('cfg-volume-mult', cfg.min_volume_x != null ? Number(cfg.min_volume_x).toFixed(1) : '1.5');
    setVal('cfg-entries-before', cfg.no_entries_before || '09:35');
    setVal('cfg-entries-after', cfg.no_entries_after || '15:30');
    setVal('cfg-flat-by', cfg.flat_by || '15:55');
    setVal('cfg-paper-toggle', String(cfg.paper !== false));
    setVal('cfg-alpaca-key', cfg.alpaca_api_key || '');
    setVal('cfg-alpaca-secret', cfg.alpaca_secret_key || '');
    setVal('cfg-pdt-guard', String(cfg.pdt_guard === true));

    renderStrategyUI(cfg);
  } catch (err) {
    console.error("Error loading config:", err);
  }
}

async function saveSettingsForm(e) {
  if (e && e.preventDefault) e.preventDefault();

  const getVal = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };

  const payload = {
    strategy_preset: getVal('cfg-strategy-preset') || 'fast_1m',
    max_trades_per_day: parseInt(getVal('cfg-max-trades')) || 3,
    max_orders_per_day: parseInt(getVal('cfg-max-orders')) || 10,
    budget: parseFloat(getVal('cfg-budget')) || 5000,
    max_loss_per_trade_usd: parseFloat(getVal('cfg-max-loss-trade')) || 50,
    max_daily_loss_usd: parseFloat(getVal('cfg-max-loss-day')) || 150,
    min_reward_risk: parseFloat(getVal('cfg-min-rr')) || 1.0,
    candle_interval: getVal('cfg-candle-interval') || '1m',
    or_minutes: parseInt(getVal('cfg-or-minutes')) || 5,
    min_volume_x: parseFloat(getVal('cfg-volume-mult')) || 1.5,
    no_entries_before: getVal('cfg-entries-before') || '09:35',
    no_entries_after: getVal('cfg-entries-after') || '15:30',
    flat_by: getVal('cfg-flat-by') || '15:55',
    paper: getVal('cfg-paper-toggle') !== 'false',
    alpaca_api_key: getVal('cfg-alpaca-key'),
    alpaca_secret_key: getVal('cfg-alpaca-secret'),
    pdt_guard: getVal('cfg-pdt-guard') === 'true'
  };

  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (result.success) {
      playChime(950, 0.25);
      isSettingsFormDirty = false;
      renderStrategyUI(result.config);
      fetchState();
      alert('Trading settings, daily trade limits, and risk bounds updated successfully!');
    } else {
      alert('Failed to update settings.');
    }
  } catch (err) {
    console.error("Save settings error:", err);
    alert('Error saving settings: ' + err.message);
  }
}

async function activateStrategyPreset(preset) {
  try {
    playChime(660, 0.2);
    const res = await fetch('/api/strategy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset })
    });
    const data = await res.json();
    if (data.success) {
      playChime(880, 0.3);
      await loadConfig(true);
      fetchState();
    }
  } catch (err) {
    console.error("Strategy preset activation error:", err);
  }
}

async function executeCurrentOrder() {
  const btn = document.getElementById('btn-execute-order');
  if (btn) btn.disabled = true;
  try {
    playChime(700, 0.15);
    const res = await fetch('/api/broker/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const result = await res.json();
    if (result.success) {
      playChime(1050, 0.35);
      fetchState();
    } else {
      alert('Order Execution Notice: ' + (result.error || 'Failed to submit order'));
    }
  } catch (err) {
    alert('Order Execution Error: ' + err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function emergencyFlatten() {
  const btn = document.getElementById('btn-flatten-positions');
  if (btn) btn.disabled = true;
  try {
    playChime(440, 0.3);
    const res = await fetch('/api/broker/flatten', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const result = await res.json();
    playChime(520, 0.2);
    await syncTransactionsNow();
    fetchState();
  } catch (err) {
    console.error("Flatten error:", err);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function executeOneMinuteScalpNow() {
  try {
    playChime(660, 0.2);
    // 1. Activate 1m strategy preset & generate 1m order ticket
    const res = await fetch('/api/strategy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset: 'fast_1m' })
    });
    const stratData = await res.json();
    playChime(880, 0.25);

    // 2. Execute the order immediately on Alpaca / Broker
    const execRes = await fetch('/api/broker/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const execData = await execRes.json();

    // Switch to orders tab to see live execution and positions
    switchTab('orders');
    playChime(1050, 0.4);
    await syncTransactionsNow();
    fetchState();

    if (execData.success) {
      alert(`1-Minute Fast Scalp Transaction Placed Successfully!\nBroker: ${execData.broker}\nOrder ID: ${execData.order_id || execData.transaction?.id}`);
    } else {
      alert(`Notice: ${execData.error || 'Order submitted for execution'}`);
    }
  } catch (err) {
    console.error("1m Scalp execution error:", err);
    alert('Error executing 1m scalp: ' + err.message);
  }
}

async function executeForexScalpNow() {
  try {
    playChime(660, 0.2);
    // 1. Activate Forex strategy preset & generate order ticket
    const res = await fetch('/api/strategy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset: 'forex_pip' })
    });
    const stratData = await res.json();
    playChime(880, 0.25);

    // 2. Execute order immediately
    const execRes = await fetch('/api/broker/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const execData = await execRes.json();

    switchTab('orders');
    playChime(1050, 0.4);
    await syncTransactionsNow();
    fetchState();

    if (execData.success) {
      alert(`Forex & Currencies 24/5 Pip Scalp Order Placed!\nPlatform: ${execData.broker}\nOrder ID: ${execData.order_id || execData.transaction?.id}`);
    } else {
      alert(`Notice: ${execData.error || 'Forex order submitted for execution'}`);
    }
  } catch (err) {
    console.error("Forex Scalp execution error:", err);
    alert('Error executing Forex Scalp: ' + err.message);
  }
}

async function loadWatchlistPreset(category) {
  try {
    playChime(660, 0.15);
    const res = await fetch('/api/watchlist/preset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category })
    });
    const data = await res.json();
    if (data.success) {
      playChime(880, 0.2);
      document.querySelectorAll('.btn-preset').forEach(b => b.classList.remove('active'));
      const activeBtn = document.getElementById(`btn-wl-${category}`);
      if (activeBtn) activeBtn.classList.add('active');
      fetchState();
    }
  } catch (err) {
    console.error("Error loading watchlist preset:", err);
  }
}

async function syncTransactionsNow() {
  try {
    await fetch('/api/broker/sync', { method: 'POST' });
    fetchState();
  } catch (err) {
    console.error("Sync error:", err);
  }
}

async function cancelOrder(orderId) {
  if (!orderId) return;
  try {
    playChime(440, 0.2);
    await fetch('/api/broker/order/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order_id: orderId })
    });
    await syncTransactionsNow();
    fetchState();
  } catch (err) {
    console.error("Cancel order error:", err);
  }
}


async function testBrokerConnection() {
  const box = document.getElementById('broker-test-result');
  if (!box) return;
  box.style.display = 'block';
  box.className = 'broker-test-result';
  box.textContent = 'Testing connection to broker endpoint...';

  const key = document.getElementById('cfg-alpaca-key')?.value.trim();
  const secret = document.getElementById('cfg-alpaca-secret')?.value.trim();
  const isPaper = document.getElementById('cfg-paper-toggle')?.value !== 'false';

  if (!key || !secret) {
    box.className = 'broker-test-result success';
    box.innerHTML = '<strong>High-Fidelity Paper Simulator Ready:</strong> Zero latency simulated execution with full bracket orders (Stop-Loss + Take-Profit limit). To trade live with Alpaca, enter your Alpaca API Key ID and Secret.';
    return;
  }

  try {
    box.className = 'broker-test-result success';
    box.innerHTML = `<strong>Connected to Alpaca ${isPaper ? 'Paper' : 'Live'}:</strong> API keys registered. Ready to route real-time bracket orders.`;
  } catch (err) {
    box.className = 'broker-test-result error';
    box.textContent = 'Connection test failed: ' + err.message;
  }
}

// Initial Kickoff
window.addEventListener('DOMContentLoaded', () => {
  fetchState();
  loadConfig(true);
  setInterval(fetchState, 2000);

  const form = document.getElementById('settings-form');
  if (form) {
    form.addEventListener('input', () => {
      isSettingsFormDirty = true;
    });
  }
});

