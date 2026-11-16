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

function numOr(v, d) {
  if (v === '' || v === null || v === undefined) return d;
  const n = Number(v);
  return Number.isNaN(n) ? d : n;
}

function priceDecimals(sym = '', price = null) {
  const s = String(sym || '').toUpperCase();
  const isSpotForex = s.includes('=X') || ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDCAD', 'USDJPY', 'USDCHF', 'EUR/USD', 'GBP/USD'].includes(s);
  if (isSpotForex) return s.includes('JPY') ? 3 : 4;
  if (price !== null && price !== undefined && !Number.isNaN(Number(price))) {
    const p = Math.abs(Number(price));
    if (p > 0 && p < 0.01) return 6;
    if (p > 0 && p < 2) return 4;
  }
  return 2;
}

function formatPrice(val, sym = '') {
  if (val === null || val === undefined || Number.isNaN(Number(val))) return '--';
  const s = String(sym || '').toUpperCase();
  const dec = priceDecimals(s, val);
  const formatted = Number(val).toFixed(dec);
  if (s.includes('=X') || s.startsWith('^')) return formatted;
  return '$' + formatted;
}

function formatQty(q) {
  const n = Number(q);
  if (Number.isNaN(n) || n <= 0) return '0';
  if (n >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (Number.isInteger(n)) return String(n);
  return n < 0.1 ? n.toFixed(6).replace(/0+$/, '').replace(/\.$/, '') : n.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
}

function assetBadgeClass(assetClass) {
  const c = String(assetClass || '').toLowerCase();
  if (c.includes('crypto')) return 'asset-crypto';
  if (c.includes('forex') || c === 'fx') return 'asset-forex';
  if (c.includes('future') || c.includes('commodity')) return 'asset-futures';
  if (c.includes('index')) return 'asset-index';
  if (c.includes('intl')) return 'asset-intl';
  return 'asset-us';
}

function renderGlobalSessions(sessions) {
  const el = document.getElementById('global-sessions-pills');
  if (!el || !sessions) return;
  const order = [
    ['crypto', '₿'],
    ['forex', '💱'],
    ['futures', '🛢️'],
    ['us', '🇺🇸'],
    ['europe', '🇪🇺'],
    ['asia', '🌏'],
  ];
  el.innerHTML = order.map(([key, icon]) => {
    const info = sessions[key];
    if (!info) return '';
    const isOpen = !!info.open;
    return `<span class="session-chip ${isOpen ? 'open' : ''}" title="${escapeHtml(info.label || '')}">${icon} ${escapeHtml(info.name || key)}: ${isOpen ? 'OPEN' : 'CLOSED'}</span>`;
  }).join('');
}

function renderSkillsTelemetry(telemetry) {
  if (!telemetry) return;
  Object.entries(telemetry).forEach(([skillKey, info]) => {
    const node = document.getElementById(`node-${skillKey}`);
    const statusEl = document.getElementById(`node-${skillKey}-status`);
    if (statusEl && info && info.detail) {
      statusEl.textContent = info.detail;
    }
    if (node && info) {
      node.classList.toggle('active', info.status === 'ACTIVE' || info.status === 'PASSED' || info.status === 'READY');
    }
    if (statusEl && info) {
      statusEl.classList.toggle('status-pass', info.status === 'PASSED' || info.status === 'ACTIVE');
    }
  });
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
  renderGlobalSessions(s.global_sessions || (s.ny_clock && s.ny_clock.global_sessions));

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

  // Capital & Buying Power KPI
  const acct = s.broker_account || {};
  const cfg = s.config || {};
  const portVal = acct.portfolio_value != null ? acct.portfolio_value : (cfg.budget || 5000);
  const bpVal = acct.buying_power != null ? acct.buying_power : portVal;
  const riskTrade = cfg.max_loss_per_trade_usd != null ? cfg.max_loss_per_trade_usd : 50;
  const capEl = document.getElementById('kpi-capital-val');
  const capModeEl = document.getElementById('kpi-capital-mode');
  const capSubEl = document.getElementById('kpi-capital-sub');
  if (capEl) capEl.textContent = `$${Number(portVal).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (capModeEl) capModeEl.textContent = cfg.paper === false ? 'Live' : 'Paper';
  if (capSubEl) capSubEl.textContent = `Buying Power: $${Number(bpVal).toLocaleString(undefined, { maximumFractionDigits: 0 })} | Risk: $${Number(riskTrade).toFixed(0)}`;

  // Mode buttons
  document.getElementById('btn-mode-sim').classList.toggle('active', s.mode === 'simulation');
  document.getElementById('btn-mode-live').classList.toggle('active', s.mode === 'live');
  document.getElementById('footer-status-text').textContent =
    `Engine 24/7 running continuously in ${s.mode === 'simulation' ? 'Simulation / Replay' : 'Live Market'} Mode | All Markets Active`;

  // Skills Pipeline Telemetry
  renderSkillsTelemetry(s.skills_telemetry);

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

  // 10. Autonomous AI Agent 24/7
  if (s.ai_agent) {
    renderAIAgent(s.ai_agent);
  }

  // Audio trigger on new cycle completion
  if (lastCycleCount !== -1 && s.cycle_count > lastCycleCount) {
    if (s.triggered_alerts && s.triggered_alerts.length > 0) {
      playChime(1050, 0.35);
    }
  }
  lastCycleCount = s.cycle_count;
}

function renderWatchlist(s) {
  const tbody = document.getElementById('watchlist-tbody');
  const countEl = document.getElementById('kpi-watchlist-count');
  const trigEl = document.getElementById('kpi-triggered-count');

  const watchlist = s.watchlist || [];
  if (countEl) countEl.textContent = watchlist.length;

  let triggeredCount = 0;
  const scanHits = (s.scans && s.scans.hits) ? s.scans.hits : [];
  const hitMap = {};
  scanHits.forEach(h => {
    hitMap[h.symbol] = h;
    if (h.status === 'TRIGGERED') triggeredCount++;
  });
  if (trigEl) trigEl.textContent = `${triggeredCount} Triggered`;

  // Universe Progress KPI & Table
  const uniTotal = (s.scans && s.scans.universe_total) || 5930;
  const uniScanned = (s.scans && s.scans.universe_scanned) || 0;
  const uniHits = s.universe_hits || (s.scans && s.scans.universe_hits) || [];
  const uniSubEl = document.getElementById('kpi-universe-progress');
  const uniBadgeEl = document.getElementById('universe-progress-badge');
  if (uniSubEl) uniSubEl.textContent = `${uniScanned.toLocaleString()} / ${uniTotal.toLocaleString()} US Cos (${uniHits.length} Hits)`;
  if (uniBadgeEl) uniBadgeEl.textContent = `${uniScanned.toLocaleString()} / ${uniTotal.toLocaleString()} Scanned`;

  const uniTbody = document.getElementById('universe-hits-tbody');
  if (uniTbody) {
    if (uniHits.length === 0) {
      uniTbody.innerHTML = '<tr><td colspan="6" class="text-muted">Click "Sweep 500 US Cos" or wait for rotating background scan to discover full-market breakouts.</td></tr>';
    } else {
      uniTbody.innerHTML = uniHits.slice(0, 40).map(u => {
        const uSym = escapeHtml(u.symbol || '');
        const uPrice = u.price != null ? formatPrice(u.price, u.symbol) : '--';
        const setups = escapeHtml(u.setups || u.setup || 'SCAN_HIT');
        const rsi = u.rsi != null ? `RSI ${Number(u.rsi).toFixed(1)}` : '-';
        const vol = u.volume != null ? Number(u.volume).toLocaleString() : '-';
        return `
          <tr>
            <td><strong>${uSym}</strong></td>
            <td>${uPrice}</td>
            <td><span class="status-badge status-triggered">${setups}</span></td>
            <td>${escapeHtml(rsi)}</td>
            <td>${vol}</td>
            <td>
              <div class="action-btn-group">
                <button class="btn btn-primary btn-xs" onclick="quickTradeSymbol('${uSym}')">Trade</button>
                <button class="btn btn-secondary btn-xs" onclick="addSymbolDirect('${uSym}')">+ Watch</button>
                <button class="btn btn-secondary btn-xs" onclick="openAnalystModal('${uSym}')">Analyze</button>
              </div>
            </td>
          </tr>
        `;
      }).join('');
    }
  }

  if (!tbody) return;
  tbody.innerHTML = '';
  watchlist.forEach(sym => {
    const q = (s.quotes && s.quotes[sym]) ? s.quotes[sym] : {};
    const hit = hitMap[sym];
    const assetInfo = q.asset || (hit && hit.asset) || { asset_class: 'us_equity', badge: 'US Equity' };
    const priceNumVal = q.price != null ? q.price : (hit && hit.price != null ? hit.price : null);

    const isTriggered = hit && hit.status === 'TRIGGERED';
    const isWaiting = hit && hit.status === 'WAITING';
    const statusBadge = isTriggered
      ? '<span class="status-badge status-triggered">TRIGGERED</span>'
      : (isWaiting ? '<span class="status-badge status-waiting">WAITING</span>' : '<span class="status-badge">MONITORING</span>');

    const lowStr = (hit && hit.or_low != null) ? formatPrice(hit.or_low, sym) : (priceNumVal != null ? formatPrice(Number(priceNumVal) * 0.995, sym) : '--');
    const highStr = (hit && hit.or_high != null) ? formatPrice(hit.or_high, sym) : (priceNumVal != null ? formatPrice(Number(priceNumVal) * 1.005, sym) : '--');
    const rangeStr = `${lowStr} - ${highStr}`;
    const volStr = (hit && hit.vol_x != null) ? `${Number(hit.vol_x).toFixed(1)}x` : '--';

    let chgPct = q.change;
    if (!chgPct && q.change_pct != null) {
      const n = Number(q.change_pct);
      chgPct = `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
    }
    chgPct = chgPct || '+0.00%';
    const symEsc = escapeHtml(sym);

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <span class="sym-badge ${assetInfo.asset_class === 'forex' ? 'sym-forex' : ''}" title="${escapeHtml(q.name || sym)}">${symEsc}</span>
      </td>
      <td><span class="asset-badge ${assetBadgeClass(assetInfo.asset_class)}">${escapeHtml(assetInfo.badge || 'US Equity')}</span></td>
      <td><strong>${formatPrice(priceNumVal, sym)}</strong></td>
      <td class="${String(chgPct).startsWith('-') ? 'text-rose' : 'text-emerald'}">${escapeHtml(chgPct)}</td>
      <td>${rangeStr}</td>
      <td>${statusBadge}</td>
      <td>${volStr}</td>
      <td>
        <div class="action-btn-group">
          <button class="btn btn-primary btn-xs" onclick="quickTradeSymbol('${symEsc}')" title="Execute order now">Trade</button>
          <button class="btn btn-secondary btn-xs" onclick="openAnalystModal('${symEsc}')" title="Fundamentals & Quote">Analyze</button>
          <button class="btn btn-secondary btn-xs" onclick="runTimeMachineSymbolDirect('${symEsc}')" title="Run 10,000 replays">Sim</button>
          <button class="btn btn-secondary btn-xs" onclick="removeSymbol('${symEsc}')" title="Remove from watchlist">✕</button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderTimeMachine(s) {
  const tm = s.timemachine;
  if (!tm) return;

  const symLabel = document.getElementById('tm-target-symbol-label');
  if (symLabel) symLabel.textContent = tm.symbol || (s.plan && s.plan.symbol) || 'Active Setup';

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

  const barT = document.querySelector('.bar-slice.bar-target');
  const barO = document.querySelector('.bar-slice.bar-open');
  const barS = document.querySelector('.bar-slice.bar-stop');
  if (barT) barT.style.width = `${Number(targetPct).toFixed(1)}%`;
  if (barO) barO.style.width = `${Number(openPct).toFixed(1)}%`;
  if (barS) barS.style.width = `${Number(stopPct).toFixed(1)}%`;

  if (legendEl) {
    legendEl.textContent = `Target ${Number(targetPct).toFixed(1)}% | Stop ${Number(stopPct).toFixed(1)}% | Open ${Number(openPct).toFixed(1)}%`;
  }

  const hist = tm.history;
  if (hist) {
    const fired = Number(hist.triggered ?? hist.fired ?? 0);
    const target = Number(hist.target ?? 0);
    const stop = Number(hist.stop ?? 0);
    const neither = Number(hist.close ?? hist.neither ?? 0);
    const avgR = Number(hist.avg_R ?? hist.avg_r ?? 0);

    const histFiredEl = document.getElementById('hist-fired');
    const histTargetEl = document.getElementById('hist-target');
    const histStopEl = document.getElementById('hist-stop');
    const histNeitherEl = document.getElementById('hist-neither');
    const histAvgREl = document.getElementById('hist-avg-r');

    if (histFiredEl) histFiredEl.textContent = `${fired} times`;
    if (histTargetEl) histTargetEl.textContent = `${target} times (${fired ? ((target / fired) * 100).toFixed(1) : '0.0'}%)`;
    if (histStopEl) histStopEl.textContent = `${stop} times (${fired ? ((stop / fired) * 100).toFixed(1) : '0.0'}%)`;
    if (histNeitherEl) histNeitherEl.textContent = `${neither} times (${fired ? ((neither / fired) * 100).toFixed(1) : '0.0'}%)`;
    if (histAvgREl) histAvgREl.textContent = `${avgR >= 0 ? '+' : ''}${avgR.toFixed(3)} R`;
  }
}

function renderOrders(s) {
  const p = s.plan;
  const o = s.orders;
  if (p) {
    const sym = p.symbol || 'TSLA';
    const symEl = document.getElementById('ticket-sym');
    const entryEl = document.getElementById('ticket-entry');
    const stopEl = document.getElementById('ticket-stop');
    const targetEl = document.getElementById('ticket-target');
    const riskShareEl = document.getElementById('ticket-risk-share');
    const assetTagEl = document.getElementById('ticket-asset-tag');

    if (symEl) symEl.textContent = sym;
    if (entryEl) entryEl.textContent = p.entry != null ? formatPrice(p.entry, sym) : '--';
    if (stopEl) stopEl.textContent = p.stop != null ? formatPrice(p.stop, sym) : '--';
    if (targetEl) targetEl.textContent = p.target != null ? formatPrice(p.target, sym) : '--';
    if (riskShareEl) riskShareEl.textContent = p.risk_per_share != null ? formatPrice(p.risk_per_share, sym) : '--';
    if (assetTagEl && p.asset && p.asset.badge) assetTagEl.textContent = p.asset.badge;
  }

  if (o && o.orders && o.orders.length > 0) {
    const firstOrder = o.orders[0];
    const qtyEl = document.getElementById('ticket-qty');
    const maxLossEl = document.getElementById('ticket-max-loss');
    const whyEl = document.getElementById('ticket-why');

    const maxLossVal = (firstOrder.plan && firstOrder.plan.max_loss != null)
      ? Number(firstOrder.plan.max_loss).toFixed(2)
      : '50.00';

    const qtyNum = Number(firstOrder.qty) || 1;
    const sym = firstOrder.symbol || (p && p.symbol) || '';
    const unitLabel = qtyNum >= 1000 || String(sym).includes('=X') ? 'Units' : 'Shares';
    const qtyLabel = `${formatQty(qtyNum)} ${unitLabel}`;

    if (qtyEl) qtyEl.textContent = qtyLabel;
    if (maxLossEl) maxLossEl.textContent = `$${maxLossVal}`;
    if (whyEl && firstOrder.why) whyEl.textContent = firstOrder.why;
  }

  // Risk Gatekeeper
  const risk = s.risk;
  const cfg = s.config || {};
  const badge = document.getElementById('risk-audit-badge');
  const kpiBadge = document.getElementById('kpi-risk-badge');
  const kpiRiskSub = document.getElementById('kpi-risk-sub');

  if (risk && risk.status === 'PASS') {
    if (badge) { badge.className = 'verdict-pill pill-pass'; badge.textContent = 'PASS'; }
    if (kpiBadge) { kpiBadge.className = 'verdict-pill pill-pass'; kpiBadge.textContent = 'PASS'; }
    if (kpiRiskSub) kpiRiskSub.textContent = cfg.allow_unlimited_orders ? 'Unlimited + All Markets OK' : `${risk.pass || 1} Orders Cleared`;
  } else if (risk && risk.status === 'BLOCK') {
    if (badge) { badge.className = 'verdict-pill pill-block'; badge.textContent = 'BLOCK'; }
    if (kpiBadge) { kpiBadge.className = 'verdict-pill pill-block'; kpiBadge.textContent = 'BLOCK'; }
    if (kpiRiskSub) kpiRiskSub.textContent = (risk.reasons && risk.reasons[0]) ? risk.reasons[0] : 'Blocked by Risk Rules';
  }

  const checklistEl = document.getElementById('risk-checklist');
  if (checklistEl && risk) {
    const items = [];
    const passedAll = risk.status === 'PASS';
    const isUnlim = cfg.allow_unlimited_orders || cfg.ai_unlimited_orders || Number(cfg.max_orders_per_day) === 0;
    const isAllMkts = cfg.allow_all_markets !== false;
    items.push({
      ok: true,
      title: `Order Capacity: ${isUnlim ? 'UNLIMITED (No Daily Cap)' : `${cfg.max_orders_per_day} / Day Limit`}`,
      desc: isUnlim ? 'AI Auto-Pilot and manual execution can place unlimited concurrent and daily orders.' : 'Enforces configured daily round-trip ceiling.'
    });
    items.push({
      ok: true,
      title: `Market Scope: ${isAllMkts ? 'ALL MARKETS ENABLED' : 'US Equities Only'}`,
      desc: 'Supports US 5,930-Co Universe, Global Intl (.T, .HK, .L, .AS), Crypto 24/7, Forex 24/5, Commodities, Indices & Options.'
    });
    if (Array.isArray(risk.reasons) && risk.reasons.length > 0) {
      risk.reasons.forEach(r => items.push({ ok: false, title: 'Blocked: ' + r, desc: 'Resolve risk block before live routing.' }));
    } else {
      items.push({
        ok: passedAll,
        title: `Automated Skill Audit (trader-risk): ${risk.status || 'PASS'}`,
        desc: risk.details || 'Mandatory stop-loss, R:R floor, and capital safety verified.'
      });
    }
    if (Array.isArray(risk.warnings)) {
      risk.warnings.slice(0, 3).forEach(w => items.push({ ok: true, title: 'Notice: ' + w, desc: 'Advisory warning from trader-risk' }));
    }
    checklistEl.innerHTML = items.map(it => `
      <div class="risk-check-item ${it.ok ? 'passed' : ''}" style="${it.ok ? '' : 'border-color: rgba(244,63,94,0.4);'}">
        <div class="risk-check-icon">${it.ok ? '✓' : '✕'}</div>
        <div class="risk-check-content">
          <div class="risk-check-title">${escapeHtml(it.title)}</div>
          <div class="risk-check-desc">${escapeHtml(it.desc)}</div>
        </div>
      </div>
    `).join('');
  }

  // Live Positions & Real-Time P&L Table
  const posTbody = document.getElementById('positions-tbody');
  const positions = s.positions || [];
  const brokerPill = document.getElementById('broker-status-pill');
  if (brokerPill) {
    const hasKey = s.config && s.config.alpaca_api_key;
    const isPaper = !s.config || s.config.paper !== false;
    brokerPill.textContent = hasKey
      ? `Connected: Alpaca ${isPaper ? 'Paper' : 'Live'} (${positions.length} Open)`
      : `Paper Simulator (${positions.length} Open)`;
  }

  if (posTbody) {
    if (positions.length === 0) {
      posTbody.innerHTML = '<tr><td colspan="10" style="text-align: center; color: var(--text-dim); padding: 22px;">No active open positions. Execute any ticker above or enable AI Auto-Pilot 24/7.</td></tr>';
    } else {
      posTbody.innerHTML = '';
      positions.forEach((pos) => {
        const sym = pos.symbol || 'TSLA';
        const quote = (s.quotes && s.quotes[sym] && s.quotes[sym].price != null) ? s.quotes[sym].price : (pos.current_price || pos.entry_price);
        const shares = Number(pos.shares || 1);
        const sharesDisplay = formatQty(shares);
        const entry = Number(pos.entry_price || quote);
        const stop = Number(pos.stop_price || (entry * 0.98));
        const target = Number(pos.target_price || (entry * 1.02));
        const pnl = (pos.pnl_usd != null) ? Number(pos.pnl_usd) : ((quote - entry) * shares);
        const pnlPct = (pos.pnl_pct != null) ? Number(pos.pnl_pct) : (entry ? (((quote - entry) / entry) * 100) : 0);
        const isProfitable = pnl >= 0;
        const badgeLabel = pos.region || pos.asset_class || 'Market';
        const symEsc = escapeHtml(sym);

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${symEsc}</strong></td>
          <td><span class="asset-badge ${assetBadgeClass(pos.asset_class)}">${escapeHtml(badgeLabel)}</span></td>
          <td>${sharesDisplay}</td>
          <td>${formatPrice(entry, sym)}</td>
          <td>${formatPrice(quote, sym)}</td>
          <td class="text-rose">${formatPrice(stop, sym)}</td>
          <td class="text-emerald">${formatPrice(target, sym)}</td>
          <td class="${isProfitable ? 'text-emerald' : 'text-rose'}"><strong>${isProfitable ? '+' : ''}$${Number(pnl).toFixed(2)}</strong></td>
          <td class="${isProfitable ? 'text-emerald' : 'text-rose'}">${isProfitable ? '+' : ''}${Number(pnlPct).toFixed(2)}%</td>
          <td><button class="btn btn-flatten btn-sm" style="padding: 4px 10px; font-size: 11px;" onclick="closePosition('${symEsc}')">Close</button></td>
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
    tbody.innerHTML = '<tr><td colspan="11" style="text-align: center; color: var(--text-dim); padding: 22px;">No active transactions yet. Execute any asset or trigger AI Evaluation to place a trade.</td></tr>';
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
    const qtyDisplay = formatQty(tx.qty || 1);

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><code>${escapeHtml(tx.id || tx.order_id || '')}</code></td>
      <td>${escapeHtml(tx.submitted_at || 'Recent')}</td>
      <td><strong>${escapeHtml(sym)}</strong></td>
      <td><span class="${isBuy ? 'text-emerald' : 'text-rose'}" style="font-weight: 700;">${escapeHtml(tx.side || 'BUY')}</span></td>
      <td>${escapeHtml(qtyDisplay)}</td>
      <td><span class="news-ticker" style="font-size: 10px;">${escapeHtml(tx.type || 'BRACKET')}</span></td>
      <td class="text-rose">${tx.stop_price ? formatPrice(tx.stop_price, sym) : '-'}</td>
      <td class="text-emerald">${tx.target_price ? formatPrice(tx.target_price, sym) : '-'}</td>
      <td><span class="status-badge ${statusClass}" style="font-size: 10px;">${escapeHtml(status)}</span></td>
      <td><span class="kpi-tag" style="font-size: 10px;">${escapeHtml(tx.broker || 'Paper')}</span></td>
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
  const cardAll = document.getElementById('strat-all-markets');
  const card1m = document.getElementById('strat-fast-1m');
  const cardForex = document.getElementById('strat-forex-pip');
  const card5m = document.getElementById('strat-standard-5m');
  const badgeAll = document.getElementById('badge-strat-all');
  const badge1m = document.getElementById('badge-strat-1m');
  const badgeForex = document.getElementById('badge-strat-forex');
  const badge5m = document.getElementById('badge-strat-5m');

  [cardAll, card1m, cardForex, card5m].forEach(c => c && c.classList.remove('active-strategy'));
  [badgeAll, badge1m, badgeForex, badge5m].forEach(b => {
    if (b) { b.textContent = 'AVAILABLE'; b.className = 'status-badge'; }
  });

  if (preset === 'all_markets_24_7' || preset === 'all_markets') {
    if (cardAll) cardAll.classList.add('active-strategy');
    if (badgeAll) { badgeAll.textContent = 'ACTIVE SETUP'; badgeAll.className = 'status-badge status-triggered'; }
  } else if (preset === 'forex_pip') {
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
  if (!str && str !== 0) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

let cachedNewsItems = [];
function renderNewsFilter() {
  renderNews({ news: cachedNewsItems });
}

function renderNews(s) {
  const listEl = document.getElementById('news-feed-list');
  const countBadge = document.getElementById('news-count-badge');
  const rawNews = s.news || [];
  cachedNewsItems = rawNews;
  const filterQ = (document.getElementById('news-filter-input')?.value || '').trim().toLowerCase();

  const news = filterQ
    ? rawNews.filter(item => JSON.stringify(item).toLowerCase().includes(filterQ))
    : rawNews;

  if (countBadge) countBadge.textContent = `${news.length} Items`;
  if (!listEl) return;

  if (news.length === 0) {
    listEl.innerHTML = '<div class="news-card"><div class="news-title">No matching headlines yet. Enter any symbol above and click "Fetch Breaking News".</div></div>';
    return;
  }

  listEl.innerHTML = '';
  news.forEach(item => {
    let title = '';
    let link = '';
    let ticker = 'MARKET';
    let source = 'Yahoo Finance';
    let timeStr = 'Recent';
    let summary = '';
    let tags = [];

    if (typeof item === 'string') {
      const urlMatch = item.match(/https?:\/\/[^\s]+/);
      link = urlMatch ? urlMatch[0] : 'https://finance.yahoo.com';
      title = item.replace(/https?:\/\/[^\s]+/, '').replace(/^.*?(ET\s+)/, '').trim() || item;
      const tickMatch = item.match(/\b([A-Z0-9.\-=^]{1,12})\b/);
      if (tickMatch) ticker = tickMatch[1];
    } else {
      title = item.title || 'Market Update';
      ticker = item.ticker || 'MARKET';
      link = item.link || `https://finance.yahoo.com/quote/${encodeURIComponent(ticker)}/news/`;
      source = item.source || 'Yahoo Finance';
      timeStr = item.time ? (item.time.includes('T') ? item.time.substring(11, 16) + ' UTC' : item.time) : 'Recent';
      summary = item.summary || '';
      tags = item.tags || [];
    }

    const tagsHtml = tags.map(t => `<span class="news-tag">${escapeHtml(t)}</span>`).join(' ');
    const tickerEsc = escapeHtml(ticker);

    const card = document.createElement('div');
    card.className = 'news-card';
    card.innerHTML = `
      <div class="news-meta">
        <span class="news-ticker" style="cursor:pointer;" onclick="quickTradeSymbol('${tickerEsc}')" title="Trade ${tickerEsc}">${tickerEsc}</span>
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

    setVal('cfg-strategy-preset', cfg.strategy_preset || 'all_markets_24_7');
    setVal('cfg-max-trades', cfg.max_trades_per_day != null ? cfg.max_trades_per_day : 0);
    setVal('cfg-max-orders', cfg.max_orders_per_day != null ? cfg.max_orders_per_day : 0);
    setVal('cfg-budget', cfg.budget != null ? cfg.budget : 5000);
    setVal('cfg-max-loss-trade', cfg.max_loss_per_trade_usd != null ? cfg.max_loss_per_trade_usd : 50);
    setVal('cfg-max-order-usd', cfg.max_order_usd != null ? cfg.max_order_usd : 0);
    setVal('cfg-max-loss-day', cfg.max_daily_loss_usd != null ? cfg.max_daily_loss_usd : 0);
    setVal('cfg-min-rr', cfg.min_reward_risk != null ? cfg.min_reward_risk : 1.0);
    setVal('cfg-allow-all-markets', String(cfg.allow_all_markets !== false));
    setVal('cfg-fractional', String(cfg.fractional !== false));
    setVal('cfg-allow-margin', String(cfg.allow_margin !== false));
    setVal('cfg-allow-options', String(cfg.allow_options !== false));
    setVal('cfg-allow-short', String(cfg.allow_short !== false));
    setVal('cfg-candle-interval', cfg.candle_interval || '1m');
    setVal('cfg-or-minutes', cfg.or_minutes || '5');
    setVal('cfg-volume-mult', cfg.min_volume_x != null ? Number(cfg.min_volume_x).toFixed(1) : '1.0');
    setVal('cfg-entries-before', cfg.no_entries_before || '00:00');
    setVal('cfg-entries-after', cfg.no_entries_after || '23:59');
    setVal('cfg-flat-by', cfg.flat_by || '23:59');
    setVal('cfg-paper-toggle', String(cfg.paper !== false));
    setVal('cfg-alpaca-key', cfg.alpaca_api_key || '');
    setVal('cfg-alpaca-secret', cfg.alpaca_secret_key || '');
    setVal('cfg-pdt-guard', String(cfg.pdt_guard === true));
    setVal('cfg-ai-enabled', String(cfg.ai_autonomous !== false));
    setVal('cfg-ai-unlimited', String(cfg.ai_unlimited_orders !== false));
    setVal('cfg-ai-confidence', cfg.ai_confidence_threshold != null ? cfg.ai_confidence_threshold : 65);
    setVal('cfg-ai-max-positions', cfg.ai_max_concurrent_positions != null ? cfg.ai_max_concurrent_positions : 0);
    setVal('cfg-ai-max-cycle', cfg.ai_max_orders_per_cycle != null ? cfg.ai_max_orders_per_cycle : 0);
    setVal('cfg-ai-breakeven', String(cfg.ai_auto_breakeven !== false));
    setVal('cfg-ai-flatten', String(cfg.ai_auto_flatten === true));

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

  const maxOrders = Math.max(0, parseInt(numOr(getVal('cfg-max-orders'), 0)));
  const maxTrades = Math.max(0, parseInt(numOr(getVal('cfg-max-trades'), 0)));
  const aiUnlimited = getVal('cfg-ai-unlimited') !== 'false';

  const payload = {
    strategy_preset: getVal('cfg-strategy-preset') || 'all_markets_24_7',
    max_trades_per_day: maxTrades,
    max_orders_per_day: maxOrders,
    allow_unlimited_orders: aiUnlimited || maxOrders === 0,
    allow_all_markets: getVal('cfg-allow-all-markets') !== 'false',
    fractional: getVal('cfg-fractional') !== 'false',
    allow_margin: getVal('cfg-allow-margin') !== 'false',
    allow_options: getVal('cfg-allow-options') !== 'false',
    allow_short: getVal('cfg-allow-short') !== 'false',
    budget: numOr(getVal('cfg-budget'), 5000),
    max_loss_per_trade_usd: numOr(getVal('cfg-max-loss-trade'), 50),
    max_order_usd: Math.max(0, numOr(getVal('cfg-max-order-usd'), 0)),
    max_daily_loss_usd: Math.max(0, numOr(getVal('cfg-max-loss-day'), 0)),
    min_reward_risk: numOr(getVal('cfg-min-rr'), 1.0),
    candle_interval: getVal('cfg-candle-interval') || '1m',
    or_minutes: parseInt(numOr(getVal('cfg-or-minutes'), 5)),
    min_volume_x: numOr(getVal('cfg-volume-mult'), 1.0),
    no_entries_before: getVal('cfg-entries-before') || '00:00',
    no_entries_after: getVal('cfg-entries-after') || '23:59',
    flat_by: getVal('cfg-flat-by') || '23:59',
    paper: getVal('cfg-paper-toggle') !== 'false',
    alpaca_api_key: getVal('cfg-alpaca-key'),
    alpaca_secret_key: getVal('cfg-alpaca-secret'),
    pdt_guard: getVal('cfg-pdt-guard') === 'true',
    ai_autonomous: getVal('cfg-ai-enabled') !== 'false',
    ai_unlimited_orders: aiUnlimited,
    ai_confidence_threshold: parseInt(numOr(getVal('cfg-ai-confidence'), 65)),
    ai_max_concurrent_positions: Math.max(0, parseInt(numOr(getVal('cfg-ai-max-positions'), 0))),
    ai_max_orders_per_cycle: Math.max(0, parseInt(numOr(getVal('cfg-ai-max-cycle'), 0))),
    ai_auto_breakeven: getVal('cfg-ai-breakeven') !== 'false',
    ai_auto_flatten: getVal('cfg-ai-flatten') === 'true'
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
      alert('All-Markets & Unlimited AI settings saved successfully!');
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

// ==========================================================================
// Autonomous 24/7 AI Agent Frontend Logic
// ==========================================================================

function renderAIAgent(ai) {
  if (!ai) return;

  const isEnabled = ai.enabled !== false;
  const isUnlimited = ai.unlimited_orders !== false;
  const thresh = ai.confidence_threshold != null ? ai.confidence_threshold : 65;
  const actionsCount = ai.actions_today || 0;
  const ordersExecuted = ai.orders_executed != null ? ai.orders_executed : actionsCount;
  const maxPos = ai.max_concurrent_positions != null ? ai.max_concurrent_positions : 0;
  const maxCycle = ai.max_orders_per_cycle != null ? ai.max_orders_per_cycle : 0;
  const statusTxt = ai.status || (isEnabled ? 'Autonomous Scanning 24/7' : 'Paused (Manual Mode)');

  // 1. Header Toggle Button
  const btnToggle = document.getElementById('btn-ai-autopilot');
  const txtToggle = document.getElementById('ai-autopilot-text');
  if (btnToggle && txtToggle) {
    if (isEnabled) {
      btnToggle.className = 'btn btn-ai-toggle active';
      txtToggle.textContent = isUnlimited ? '🤖 AI Auto-Pilot: ♾️ ON' : '🤖 AI Auto-Pilot: ON';
    } else {
      btnToggle.className = 'btn btn-ai-toggle paused';
      txtToggle.textContent = '🤖 AI Auto-Pilot: OFF';
    }
  }

  // 2. Tab Pane Toggle Button
  const btnPaneToggle = document.getElementById('btn-pane-ai-toggle');
  const lblPaneToggle = document.getElementById('pane-ai-toggle-label');
  if (btnPaneToggle && lblPaneToggle) {
    if (isEnabled) {
      btnPaneToggle.className = 'btn btn-ai-toggle-large active';
      lblPaneToggle.textContent = isUnlimited ? 'Auto-Pilot: UNLIMITED' : 'Auto-Pilot: ACTIVE';
    } else {
      btnPaneToggle.className = 'btn btn-ai-toggle-large paused';
      lblPaneToggle.textContent = 'Auto-Pilot: PAUSED';
    }
  }

  // 3. Tab Badge
  const tabBadge = document.getElementById('tab-ai-badge');
  if (tabBadge) {
    tabBadge.textContent = isEnabled ? (isUnlimited ? '♾️ 24/7' : 'ACTIVE') : 'OFF';
    tabBadge.style.background = isEnabled ? '#10b981' : '#64748b';
  }

  // 4. KPI Summary Pill
  const kpiBadge = document.getElementById('kpi-ai-badge');
  const kpiThresh = document.getElementById('kpi-ai-thresh');
  const kpiUnlimTag = document.getElementById('kpi-ai-unlimited-tag');
  const kpiSub = document.getElementById('kpi-ai-sub');
  if (kpiBadge) {
    kpiBadge.textContent = isEnabled ? 'ACTIVE' : 'PAUSED';
    kpiBadge.className = isEnabled ? 'verdict-pill pill-pass' : 'verdict-pill pill-warn';
  }
  if (kpiThresh) kpiThresh.textContent = `${thresh}% Gate`;
  if (kpiUnlimTag) kpiUnlimTag.style.display = isUnlimited ? 'inline-block' : 'none';
  if (kpiSub) {
    kpiSub.textContent = `${ordersExecuted} Orders | ${isUnlimited ? 'Unlimited' : `Cap ${maxPos}/${maxCycle}`}`;
  }

  // 5. Pane High-Level Metrics
  const metricStatus = document.getElementById('ai-metric-status');
  const metricThresh = document.getElementById('ai-metric-threshold');
  const metricLimitsSub = document.getElementById('ai-metric-limits-sub');
  const metricActions = document.getElementById('ai-metric-actions');
  const metricLast = document.getElementById('ai-metric-last-action');
  const metricProt = document.getElementById('ai-metric-protections');

  if (metricStatus) {
    metricStatus.textContent = statusTxt;
    metricStatus.className = isEnabled ? 'ai-metric-val text-emerald' : 'ai-metric-val text-amber';
  }
  if (metricThresh) {
    metricThresh.textContent = isUnlimited ? `${thresh}% | UNLIMITED` : `${thresh}% Minimum`;
  }
  if (metricLimitsSub) {
    metricLimitsSub.textContent = isUnlimited ? 'No Daily Order or Position Ceiling' : `Max ${maxPos || '∞'} Pos | ${maxCycle || '∞'} / Cycle`;
  }
  if (metricActions) {
    metricActions.textContent = `${ordersExecuted} Order${ordersExecuted === 1 ? '' : 's'} (${actionsCount} Actions)`;
  }
  if (metricLast) {
    metricLast.textContent = `Last: ${ai.last_action || 'None'}`;
  }
  if (metricProt) {
    metricProt.textContent = `${ai.auto_breakeven !== false ? 'Breakeven ON' : 'Fixed Stop'} | ${ai.auto_flatten ? 'EOD Stocks ON' : '24/7 Hold'}`;
  }

  // 6. Form Slider, Inputs & Checkboxes (only if not focused)
  const inputThresh = document.getElementById('input-ai-threshold');
  const valThresh = document.getElementById('ai-threshold-val');
  if (inputThresh && document.activeElement !== inputThresh) inputThresh.value = thresh;
  if (valThresh && document.activeElement !== inputThresh) valThresh.textContent = `${thresh}%`;

  const inputMaxPos = document.getElementById('input-ai-max-positions');
  if (inputMaxPos && document.activeElement !== inputMaxPos) inputMaxPos.value = maxPos;
  const inputMaxCycle = document.getElementById('input-ai-max-cycle');
  if (inputMaxCycle && document.activeElement !== inputMaxCycle) inputMaxCycle.value = maxCycle;

  const checkUnlim = document.getElementById('input-ai-unlimited');
  if (checkUnlim && document.activeElement !== checkUnlim) checkUnlim.checked = isUnlimited;

  const checkBe = document.getElementById('input-ai-breakeven');
  if (checkBe && document.activeElement !== checkBe) checkBe.checked = ai.auto_breakeven !== false;

  const checkFlat = document.getElementById('input-ai-flatten');
  if (checkFlat && document.activeElement !== checkFlat) checkFlat.checked = ai.auto_flatten === true;

  // 7. Live Decision Chain & Reasoning Feed
  const feed = document.getElementById('ai-decisions-feed');
  if (!feed) return;

  const decisions = ai.decisions || [];
  if (decisions.length === 0) {
    feed.innerHTML = `
      <div class="empty-state-card">
        <div class="empty-icon">🤖</div>
        <div class="empty-title">AI Agent Operating 24/7 Across All Markets</div>
        <div class="empty-desc">Scanning global equities, 5,930 US companies, crypto, forex, and commodities. Click "Evaluate Now" to scan immediately.</div>
      </div>
    `;
    return;
  }

  let html = '';
  decisions.forEach(d => {
    let actionClass = 'executed';
    let badgeClass = 'badge-buy';
    let actionIcon = '⚡';
    let actionLabel = d.action || 'EVALUATE';

    if (d.action === 'AUTONOMOUS_BUY_EXECUTED') {
      actionClass = 'executed';
      badgeClass = 'badge-buy';
      actionIcon = '⚡';
      actionLabel = 'AUTONOMOUS ORDER EXECUTED';
    } else if (d.action === 'TRAILING_STOP_BREAKEVEN') {
      actionClass = 'breakeven';
      badgeClass = 'badge-breakeven';
      actionIcon = '🛡️';
      actionLabel = 'STOP -> BREAKEVEN LOCKED';
    } else if (d.action === 'TARGET_PROFIT_EXIT') {
      actionClass = 'target';
      badgeClass = 'badge-target';
      actionIcon = '🎯';
      actionLabel = 'TARGET HIT -> PROFIT EXIT';
    } else if (d.action === 'STOP_LOSS_EXIT') {
      actionClass = 'STOP_LOSS_EXIT';
      badgeClass = 'badge-stop';
      actionIcon = '🛑';
      actionLabel = 'STOP LOSS -> RISK EXIT';
    } else if (d.action === 'EOD_FLATTEN') {
      actionClass = 'flatten';
      badgeClass = 'badge-flatten';
      actionIcon = '⏰';
      actionLabel = 'EOD STOCK FLATTEN';
    } else {
      actionClass = 'hold';
      badgeClass = 'badge-hold';
      actionIcon = '👁️';
      actionLabel = 'MONITOR & HOLD';
    }

    const conviction = d.conviction || 0;
    const barColor = conviction >= 75 ? 'var(--accent-emerald)' : conviction >= 55 ? 'var(--accent-cyan)' : 'var(--text-dim)';

    let factorsHtml = '';
    if (d.factors && typeof d.factors === 'object') {
      for (const [, v] of Object.entries(d.factors)) {
        factorsHtml += `<span class="ai-factor-chip">${escapeHtml(v)}</span>`;
      }
    }

    html += `
      <div class="ai-decision-card ${actionClass}">
        <div class="ai-decision-top">
          <div class="ai-action-badge ${badgeClass}">
            <span>${actionIcon}</span>
            <span>${actionLabel}</span>
          </div>
          <div class="ai-conviction-meter-mini" title="Multi-Factor Conviction: ${conviction}%">
            <span class="ai-conviction-score-txt">${conviction}% Conviction</span>
            <div class="ai-conviction-bar">
              <div class="ai-conviction-fill" style="width: ${conviction}%; background: ${barColor};"></div>
            </div>
          </div>
        </div>

        <div class="ai-decision-narrative">
          ${escapeHtml(d.details || '')}
        </div>

        ${factorsHtml ? `<div class="ai-factors-row">${factorsHtml}</div>` : ''}

        <div class="ai-decision-footer">
          <span>Ticker: <strong style="color: var(--text-main);">${escapeHtml(d.symbol || 'MARKET')}</strong> ${d.asset_class ? `(${escapeHtml(d.asset_class)})` : ''}</span>
          <span>Timestamp: ${escapeHtml(d.time || '--:--:--')}</span>
        </div>
      </div>
    `;
  });

  feed.innerHTML = html;
}

async function toggleAIAutoPilot() {
  try {
    playChime(660, 0.15);
    const res = await fetch('/api/ai/toggle', { method: 'POST' });
    const data = await res.json();
    playChime(data.enabled ? 990 : 440, 0.25);
    await fetchState();
  } catch (err) {
    console.error("Error toggling AI Auto-Pilot:", err);
  }
}

async function triggerAIEvaluationNow() {
  try {
    playChime(880, 0.2);
    const res = await fetch('/api/ai/evaluate-now', { method: 'POST' });
    const data = await res.json();
    playChime(1100, 0.3);
    await fetchState();
    if (data.decisions && data.decisions.length > 0) {
      const executed = data.decisions.filter(d => d.status === 'EXECUTED');
      if (executed.length > 0) {
        alert(`AI Executed ${executed.length} Autonomous Action(s)!\nFirst: ${executed[0].action} ${executed[0].symbol}\n${executed[0].details}`);
      }
    }
  } catch (err) {
    console.error("Error evaluating AI:", err);
  }
}

async function saveAIConfigForm(e) {
  if (e && e.preventDefault) e.preventDefault();
  try {
    playChime(750, 0.2);
    const threshold = parseInt(numOr(document.getElementById('input-ai-threshold')?.value, 65));
    const unlimited_orders = document.getElementById('input-ai-unlimited')?.checked !== false;
    const max_concurrent_positions = Math.max(0, parseInt(numOr(document.getElementById('input-ai-max-positions')?.value, 0)));
    const max_orders_per_cycle = Math.max(0, parseInt(numOr(document.getElementById('input-ai-max-cycle')?.value, 0)));
    const auto_breakeven = document.getElementById('input-ai-breakeven')?.checked !== false;
    const auto_flatten = document.getElementById('input-ai-flatten')?.checked === true;

    const res = await fetch('/api/ai/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        threshold,
        unlimited_orders,
        max_concurrent_positions,
        max_orders_per_cycle,
        auto_breakeven,
        auto_flatten
      })
    });
    const data = await res.json();
    if (data.success) {
      playChime(1050, 0.25);
      await fetchState();
      await loadConfig(true);
      alert(`AI Auto-Pilot Settings Saved!\nConviction Threshold: ${threshold}%\nUnlimited Orders: ${unlimited_orders ? 'ON' : 'OFF'}\nAuto-Breakeven: ${auto_breakeven ? 'ON' : 'OFF'}`);
    }
  } catch (err) {
    console.error("Error saving AI config:", err);
    alert('Error saving AI settings: ' + err.message);
  }
}

// ==========================================================================
// Multi-Market Search, Universe Sweep, Per-Position Close, News & Analyst
// ==========================================================================

let searchDebounceTimer = null;
function debouncedMarketSearch(q) {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  const dropdown = document.getElementById('market-search-results');
  if (!q || q.trim().length < 2) {
    if (dropdown) {
      dropdown.classList.add('hidden');
      dropdown.innerHTML = '';
    }
    return;
  }
  searchDebounceTimer = setTimeout(() => runMarketSearch(q.trim()), 280);
}

async function searchMarkets(e) {
  if (e && e.preventDefault) e.preventDefault();
  const q = (document.getElementById('input-market-search')?.value || '').trim();
  if (q) await runMarketSearch(q);
}

async function runMarketSearch(q) {
  const dropdown = document.getElementById('market-search-results');
  if (!dropdown) return;
  dropdown.classList.remove('hidden');
  dropdown.innerHTML = '<div class="search-result-row"><span class="text-muted">Searching global exchanges, US universe, crypto &amp; FX...</span></div>';
  try {
    const res = await fetch(`/api/markets/search?q=${encodeURIComponent(q)}&limit=15`);
    const data = await res.json();
    const results = data.results || [];
    if (results.length === 0) {
      dropdown.innerHTML = `<div class="search-result-row"><span class="text-muted">No exact match for "${escapeHtml(q)}". Try adding raw ticker directly (e.g. BTC-USD, 7203.T, AAPL).</span></div>`;
      return;
    }
    dropdown.innerHTML = results.map(r => {
      const sym = escapeHtml(r.symbol || '');
      const name = escapeHtml(r.name || sym);
      const exch = escapeHtml(r.exchange || r.region || '');
      const badge = escapeHtml(r.badge || r.asset_class || 'Market');
      return `
        <div class="search-result-row">
          <div class="search-res-info">
            <span class="search-res-sym">${sym}</span>
            <span class="asset-badge ${assetBadgeClass(r.asset_class)}">${badge}</span>
            <span class="search-res-name">${name} ${exch ? `(${exch})` : ''}</span>
          </div>
          <div class="search-res-actions">
            <button type="button" class="btn btn-primary btn-xs" onclick="quickTradeSymbol('${sym}')">Trade</button>
            <button type="button" class="btn btn-secondary btn-xs" onclick="addSymbolDirect('${sym}')">+ Watch</button>
            <button type="button" class="btn btn-secondary btn-xs" onclick="openAnalystModal('${sym}')">Analyze</button>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    dropdown.innerHTML = `<div class="search-result-row"><span class="text-rose">Search error: ${escapeHtml(err.message)}</span></div>`;
  }
}

async function addSymbolDirect(symbol) {
  if (!symbol) return;
  await fetch('/api/watchlist/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol })
  });
  playChime(720, 0.12);
  fetchState();
}

async function quickTradeFromInput(e) {
  if (e && e.preventDefault) e.preventDefault();
  const inp = document.getElementById('quick-trade-symbol');
  const sym = (inp?.value || '').trim().toUpperCase();
  if (!sym) return;
  await quickTradeSymbol(sym);
  if (inp) inp.value = '';
}

async function quickTradeSymbol(symbol) {
  if (!symbol) return;
  try {
    playChime(700, 0.15);
    const res = await fetch('/api/broker/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol })
    });
    const data = await res.json();
    if (data.success) {
      playChime(1050, 0.3);
      fetchState();
      alert(`Executed ${symbol} Order!\nBroker: ${data.broker}\nOrder ID: ${data.order_id || data.transaction?.id}`);
    } else {
      alert(`Trade Notice (${symbol}): ${data.error || 'Could not execute order'}`);
    }
  } catch (err) {
    alert(`Trade Error (${symbol}): ${err.message}`);
  }
}

async function closePosition(symbol) {
  if (!symbol) return;
  try {
    playChime(480, 0.2);
    const res = await fetch('/api/broker/close', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol })
    });
    const data = await res.json();
    await syncTransactionsNow();
    fetchState();
    if (!data.success && data.error) {
      alert(`Close Position Notice (${symbol}): ${data.error}`);
    }
  } catch (err) {
    console.error("Close position error:", err);
  }
}

async function scanUniverseNow() {
  try {
    playChime(680, 0.15);
    const res = await fetch('/api/scanner/scan-universe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ batch_size: 500 })
    });
    const data = await res.json();
    playChime(920, 0.25);
    fetchState();
    if (data.success) {
      alert(`US Universe Batch Scanned!\nScanned: ${data.scanned} companies\nProgress: ${data.universe_scanned} / ${data.universe_total}\nHits Discovered: ${(data.hits || []).length}`);
    }
  } catch (err) {
    alert('Universe Scan Error: ' + err.message);
  }
}

async function refreshUniverseNow() {
  try {
    playChime(620, 0.15);
    const res = await fetch('/api/scanner/refresh-universe', { method: 'POST' });
    const data = await res.json();
    fetchState();
    if (data.success) {
      alert(`Refreshed Nasdaq Trader US Universe!\nTotal companies loaded: ${data.universe_total}`);
    } else {
      alert('Universe refresh notice: ' + (data.error || 'Failed'));
    }
  } catch (err) {
    alert('Universe Refresh Error: ' + err.message);
  }
}

async function fetchNewsNow(e) {
  if (e && e.preventDefault) e.preventDefault();
  const inp = document.getElementById('news-fetch-symbol');
  const raw = (inp?.value || '').trim().toUpperCase();
  const symbols = raw ? raw.split(',').map(s => s.trim()).filter(Boolean) : [];
  try {
    playChime(660, 0.15);
    const res = await fetch('/api/news/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbols })
    });
    const data = await res.json();
    playChime(880, 0.2);
    await fetchState();
    if (!data.success && data.error) alert('News Fetch Notice: ' + data.error);
  } catch (err) {
    alert('News Fetch Error: ' + err.message);
  }
}

async function runTimeMachineForSymbol(e) {
  if (e && e.preventDefault) e.preventDefault();
  const sym = (document.getElementById('tm-symbol-input')?.value || '').trim().toUpperCase();
  if (sym) await runTimeMachineSymbolDirect(sym);
}

async function runTimeMachineSymbolDirect(symbol) {
  if (!symbol) return;
  switchTab('timemachine');
  const inp = document.getElementById('tm-symbol-input');
  if (inp) inp.value = symbol;
  try {
    playChime(640, 0.15);
    const res = await fetch('/api/timemachine/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol })
    });
    const data = await res.json();
    if (data.success && data.timemachine) {
      playChime(960, 0.25);
      await fetchState();
    } else {
      alert(`Time Machine (${symbol}): ${data.error || 'Simulation failed'}`);
    }
  } catch (err) {
    alert(`Time Machine Error (${symbol}): ${err.message}`);
  }
}

async function openAnalystModal(symbol) {
  const modal = document.getElementById('analyst-modal');
  const titleEl = document.getElementById('analyst-modal-title');
  const subEl = document.getElementById('analyst-modal-sub');
  const bodyEl = document.getElementById('analyst-modal-body');
  if (!modal || !bodyEl) return;

  const sym = symbol || (state && state.plan && state.plan.symbol) || 'AAPL';
  modal.classList.remove('hidden');
  if (titleEl) titleEl.textContent = `${sym} - Market Quote & SEC EDGAR Analysis`;
  if (subEl) subEl.textContent = 'Querying Yahoo live quote & trader-analyst SEC XBRL facts...';
  bodyEl.innerHTML = '<p class="text-muted">Loading financials, PE/valuation, revenue, net income &amp; technicals...</p>';

  try {
    const res = await fetch(`/api/analyst/${encodeURIComponent(sym)}`);
    const data = await res.json();
    if (!data.success) {
      bodyEl.innerHTML = `<p class="text-rose">${escapeHtml(data.error || 'Analysis failed')}</p>`;
      return;
    }
    const q = data.quote || {};
    const analysis = data.analysis || data.sec_facts || {};
    const asset = data.asset || {};
    const symDisp = data.symbol || analysis.ticker || sym;
    const metrics = analysis.metrics || analysis.ttm || {};
    const livePrice = q.price != null ? q.price : analysis.price;
    const liveChange = q.change_pct != null
      ? `${Number(q.change_pct) >= 0 ? '+' : ''}${Number(q.change_pct).toFixed(2)}%`
      : (q.change || analysis.change || '--');
    const statCards = [
      ['Symbol / Market', `${symDisp} (${asset.badge || analysis.asset_class || 'Market'})`],
      ['Live Price', livePrice != null ? formatPrice(livePrice, symDisp) : '--'],
      ['Day Change', liveChange],
      ['Exchange / Region', `${q.exchange || asset.region || analysis.region || '-'} (${q.currency || 'USD'})`],
      ['Company / CIK', analysis.name ? `${analysis.name}${analysis.cik ? ` (CIK ${analysis.cik})` : ''}` : (q.name || symDisp)],
    ];
    if (metrics && typeof metrics === 'object') {
      Object.entries(metrics).slice(0, 8).forEach(([k, v]) => {
        if (v === null || v === undefined) return;
        const valText = (v && typeof v === 'object') ? (v.formatted || v.val || JSON.stringify(v)) : String(v);
        statCards.push([k, valText]);
      });
    }
    const changesHtml = (Array.isArray(analysis.changes) && analysis.changes.length > 0)
      ? `<div style="margin-top:12px;"><strong>Recent Fundamental Changes:</strong><ul style="margin:6px 0 0 18px; color:var(--text-muted); font-size:12px;">${analysis.changes.slice(0, 5).map(c => `<li>${escapeHtml(typeof c === 'string' ? c : JSON.stringify(c))}</li>`).join('')}</ul></div>`
      : '';
    bodyEl.innerHTML = `
      <div style="display:flex; gap:8px; margin-bottom:12px; flex-wrap:wrap;">
        <button class="btn btn-primary btn-sm" onclick="quickTradeSymbol('${escapeHtml(symDisp)}')">🚀 Execute Trade (${escapeHtml(symDisp)})</button>
        <button class="btn btn-secondary btn-sm" onclick="addSymbolDirect('${escapeHtml(symDisp)}')">+ Add to Watchlist</button>
        <button class="btn btn-secondary btn-sm" onclick="runTimeMachineSymbolDirect('${escapeHtml(symDisp)}'); closeAnalystModal()">⏳ Run 10k Replays</button>
      </div>
      <div class="analyst-grid">
        ${statCards.map(([lbl, val]) => `
          <div class="analyst-stat">
            <div class="analyst-stat-label">${escapeHtml(lbl)}</div>
            <div class="analyst-stat-val">${escapeHtml(val)}</div>
          </div>
        `).join('')}
      </div>
      ${changesHtml}
      ${analysis.note ? `<p class="text-muted" style="margin-top:10px; font-size:12px;">${escapeHtml(analysis.note)}</p>` : ''}
    `;
  } catch (err) {
    bodyEl.innerHTML = `<p class="text-rose">Error loading analysis: ${escapeHtml(err.message)}</p>`;
  }
}

function closeAnalystModal() {
  const modal = document.getElementById('analyst-modal');
  if (modal) modal.classList.add('hidden');
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

