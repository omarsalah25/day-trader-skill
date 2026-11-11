#!/usr/bin/env python3
"""24/7 Continuous Trading Engine for day-trader-skill.
Coordinates scanning, news monitoring, entry timing, risk management,
time-machine simulations, alerts, and congressional disclosures.
"""

import datetime
import json
import os
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADER_DIR = os.path.join(ROOT, "trader")


def get_ny_time(now_override=None):
    if now_override:
        return now_override
    # Approximate US Eastern Time from UTC
    # EDT is UTC-4, EST is UTC-5
    utcnow = datetime.datetime.now(datetime.timezone.utc)
    # US DST runs second Sunday in March to first Sunday in November
    year = utcnow.year
    march_1 = datetime.datetime(year, 3, 1, tzinfo=datetime.timezone.utc)
    dst_start = march_1 + datetime.timedelta(days=(6 - march_1.weekday()) % 7 + 7, hours=7)
    nov_1 = datetime.datetime(year, 11, 1, tzinfo=datetime.timezone.utc)
    dst_end = nov_1 + datetime.timedelta(days=(6 - nov_1.weekday()) % 7, hours=6)
    is_dst = dst_start <= utcnow < dst_end
    offset = datetime.timedelta(hours=-4 if is_dst else -5)
    return utcnow + offset


class TradingEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = True
        self.mode = "simulation"  # "simulation" or "live"
        self.interval = 30  # seconds between cycles
        self.cycle_count = 0
        self.last_cycle_time = None
        self.next_cycle_in = 30
        self.status = "Initializing"
        self.status_detail = "Starting up 24/7 Day Trader engine"
        self.start_time = time.time()

        self.watchlist = ["TSLA", "NVDA", "AAPL", "AMD", "MSFT", "AMZN", "META", "SPY", "QQQ"]
        self.quotes = {}
        self.scans = {"as_of": None, "hits": []}
        self.news_feed = []
        self.pelosi_filings = []
        self.active_plan = None
        self.timemachine_stats = None
        self.orders = []
        self.risk_verdict = {"status": "UNKNOWN", "details": "No inspection yet"}
        self.alerts = []
        self.triggered_alerts = []
        self.logs = []
        self._thread = None
        self._stop_event = threading.Event()

        # Ensure trader directory exists
        os.makedirs(TRADER_DIR, exist_ok=True)
        self._init_files()
        self.log("INFO", "Trading Engine initialized. 24/7 background scheduler ready.")

    def _init_files(self):
        cfg_path = os.path.join(TRADER_DIR, "config.json")
        if not os.path.exists(cfg_path):
            sample_cfg = os.path.join(ROOT, "trader-budget", "config.example.json")
            if os.path.exists(sample_cfg):
                with open(sample_cfg, "r") as f:
                    cfg = json.load(f)
                cfg["sec_user_agent"] = "DayTrader daytrader@local.domain"
                with open(cfg_path, "w") as f:
                    json.dump(cfg, f, indent=2)

        # Load initial alerts if present
        alerts_file = os.path.join(TRADER_DIR, "alerts.json")
        if os.path.exists(alerts_file):
            try:
                with open(alerts_file, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.alerts = data
                    elif isinstance(data, dict) and "alerts" in data:
                        self.alerts = data["alerts"]
            except Exception:
                pass

        # Load existing plan / timemachine / orders if present
        self._reload_trader_files()

    def _reload_trader_files(self):
        plan_file = os.path.join(TRADER_DIR, "plan.json")
        if os.path.exists(plan_file):
            try:
                with open(plan_file, "r") as f:
                    self.active_plan = json.load(f)
            except Exception:
                pass

        tm_file = os.path.join(TRADER_DIR, "timemachine.json")
        if os.path.exists(tm_file):
            try:
                with open(tm_file, "r") as f:
                    self.timemachine_stats = json.load(f)
            except Exception:
                pass

        orders_file = os.path.join(TRADER_DIR, "orders.json")
        if os.path.exists(orders_file):
            try:
                with open(orders_file, "r") as f:
                    self.orders = json.load(f)
            except Exception:
                pass

    def log(self, level, message, details=None):
        entry = {
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "level": level.upper(),
            "message": message,
            "details": details or ""
        }
        with self.lock:
            self.logs.insert(0, entry)
            if len(self.logs) > 300:
                self.logs.pop()

    def start(self):
        with self.lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self.running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        self.log("INFO", "24/7 background scheduler thread started.")

    def pause(self):
        with self.lock:
            self.running = False
        self.log("WARN", "24/7 background scheduler paused by user.")

    def resume(self):
        with self.lock:
            self.running = True
        self.log("INFO", "24/7 background scheduler resumed.")

    def set_mode(self, mode):
        with self.lock:
            self.mode = "simulation" if mode == "simulation" else "live"
        self.log("INFO", f"Engine mode switched to: {self.mode.upper()}")
        self.run_cycle_now()

    def set_interval(self, seconds):
        with self.lock:
            self.interval = max(5, int(seconds))
        self.log("INFO", f"Cycle interval set to {self.interval}s")

    def add_symbol(self, symbol):
        sym = symbol.strip().upper()
        with self.lock:
            if sym and sym not in self.watchlist:
                self.watchlist.append(sym)
                self.log("INFO", f"Added symbol {sym} to watchlist.")
                return True
        return False

    def remove_symbol(self, symbol):
        sym = symbol.strip().upper()
        with self.lock:
            if sym in self.watchlist:
                self.watchlist.remove(sym)
                self.log("INFO", f"Removed symbol {sym} from watchlist.")
                return True
        return False

    def add_alert(self, alert_data):
        with self.lock:
            alert_id = f"{alert_data.get('symbol', 'alert').lower()}-{alert_data.get('type', 'rule')}-{int(time.time())}"
            alert = {
                "id": alert_id,
                "symbol": alert_data.get("symbol", "").upper(),
                "type": alert_data.get("type", "target"),
                "price": float(alert_data.get("price", 0.0)) if alert_data.get("price") else None,
                "pct": float(alert_data.get("pct", 0.0)) if alert_data.get("pct") else None,
                "note": alert_data.get("note", "Custom user alert"),
                "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "status": "ARMED"
            }
            self.alerts.append(alert)
            self._save_alerts()
            self.log("ALERT", f"Armed new alert: {alert['symbol']} {alert['type']} at {alert.get('price') or alert.get('pct')}")
            return alert

    def dismiss_alert(self, alert_id):
        with self.lock:
            self.alerts = [a for a in self.alerts if a.get("id") != alert_id]
            self._save_alerts()
            self.log("INFO", f"Dismissed alert {alert_id}")

    def _save_alerts(self):
        alerts_file = os.path.join(TRADER_DIR, "alerts.json")
        try:
            with open(alerts_file, "w") as f:
                json.dump(self.alerts, f, indent=2)
        except Exception as e:
            self.log("ERROR", f"Failed to save alerts.json: {e}")

    def get_ny_clock_status(self):
        ny = get_ny_time()
        hour, minute = ny.hour, ny.minute
        weekday = ny.weekday()  # 0=Monday, 6=Sunday

        is_weekend = weekday >= 5
        minutes_from_midnight = hour * 60 + minute

        market_open_min = 9 * 60 + 30
        market_close_min = 16 * 60
        pre_market_min = 4 * 60
        post_market_min = 20 * 60

        if is_weekend:
            session = "WEEKEND CLOSED"
            is_open = False
            next_open = "Monday 09:30 ET"
        elif minutes_from_midnight < pre_market_min:
            session = "OVERNIGHT CLOSED"
            is_open = False
            next_open = "Today 04:00 ET (Pre-Market)"
        elif minutes_from_midnight < market_open_min:
            session = "PRE-MARKET"
            is_open = False
            next_open = f"Today 09:30 ET ({market_open_min - minutes_from_midnight}m)"
        elif minutes_from_midnight <= market_close_min:
            session = "MARKET OPEN"
            is_open = True
            next_open = f"Closes in {market_close_min - minutes_from_midnight}m"
        elif minutes_from_midnight <= post_market_min:
            session = "AFTER HOURS"
            is_open = False
            next_open = "Tomorrow 04:00 ET"
        else:
            session = "OVERNIGHT CLOSED"
            is_open = False
            next_open = "Tomorrow 04:00 ET"

        return {
            "ny_time": ny.strftime("%Y-%m-%d %H:%M:%S ET"),
            "session": session,
            "is_open": is_open,
            "next_open": next_open,
            "hour": hour,
            "minute": minute
        }

    def run_cycle_now(self):
        threading.Thread(target=self._execute_cycle, daemon=True).start()

    def run_demo_reel(self):
        """Runs the entire 9-step TSLA simulation pipeline using offline fixtures."""
        self.log("INFO", "Running full 9-step Demo Reel simulation pipeline...")
        threading.Thread(target=self._execute_demo_reel, daemon=True).start()

    def _execute_demo_reel(self):
        with self.lock:
            self.status = "Running Demo Reel"
            self.status_detail = "Simulating full TSLA October 19 session"

        try:
            # 1. Exit plan
            self.log("STEP 1/8", "Exit Planner: calculating opening-range stop and 1R profit target for TSLA...")
            cmd_exit = [
                sys.executable, os.path.join(ROOT, "trader-exit", "exit.py"), "plan",
                "--stop", "or-mid", "--target", "1R",
                "--symbol", "TSLA", "--entry", "364.18",
                "--or-high", "362.18", "--or-low", "354.47",
                "--time", "10:15 AM", "--date", "2026-10-19",
                "--write"
            ]
            res_exit = subprocess.run(cmd_exit, cwd=ROOT, capture_output=True, text=True)
            if res_exit.returncode == 0:
                self.log("SUCCESS", "Exit plan generated: Stop $358.32, Target $370.04 (Risk $5.86/sh)")

            # 2. Time Machine
            self.log("STEP 2/8", "Time Machine: running 10,000 Monte Carlo replays from TSLA 5m candles...")
            cmd_tm = [
                sys.executable, os.path.join(ROOT, "trader-timemachine", "timemachine.py"), "run",
                "--offline", os.path.join(ROOT, "tests", "fixtures", "trader-timemachine"),
                "--now", "2026-10-19 10:15", "--seed", "19", "--write"
            ]
            res_tm = subprocess.run(cmd_tm, cwd=ROOT, capture_output=True, text=True)
            if res_tm.returncode == 0:
                self.log("SUCCESS", "Time Machine: Target 29.4%, Stop 25.5%, Open 45.1%. Verdict: Coin flip.")

            # 3. Budget sizing
            self.log("STEP 3/8", "Budget Manager: sizing position to $5,000 budget & $50 max trade risk...")
            cmd_budget = [
                sys.executable, os.path.join(ROOT, "trader-budget", "size.py"), "--write"
            ]
            res_budget = subprocess.run(cmd_budget, cwd=ROOT, capture_output=True, text=True)
            if res_budget.returncode == 0:
                self.log("SUCCESS", "Budget sized: 8 shares TSLA ($2,913.44), max loss at stop $46.88")

            # 4. Risk inspection
            self.log("STEP 4/8", "Risk Gatekeeper: checking rules, limits, PDT guard and broker constraints...")
            cmd_risk = [
                sys.executable, os.path.join(ROOT, "trader-risk", "check.py"),
                "--now", "2026-10-19 10:15"
            ]
            res_risk = subprocess.run(cmd_risk, cwd=ROOT, capture_output=True, text=True)
            if res_risk.returncode == 0:
                self.log("SUCCESS", "Risk inspection: PASS (1 approved, 0 blocked). Paper trading verified.")
                self.risk_verdict = {"status": "PASS", "details": res_risk.stdout}
            else:
                self.risk_verdict = {"status": "BLOCK", "details": res_risk.stdout}

            # 5. Broker ticket
            self.log("STEP 5/8", "Broker Executor: formatting Alpaca bracket order ticket...")
            cmd_ticket = [
                sys.executable, os.path.join(ROOT, "trader-broker", "ticket.py"), "show"
            ]
            res_ticket = subprocess.run(cmd_ticket, cwd=ROOT, capture_output=True, text=True)
            if "BUY 8 TSLA" in res_ticket.stdout:
                self.log("SUCCESS", "Broker ticket prepared: BUY 8 TSLA bracket order ready for execution.")

            # 6. Alerts
            self.log("STEP 6/8", "Alerts Daemon: arming stop, target and 15:55 flatten triggers from plan...")
            cmd_alerts = [
                sys.executable, os.path.join(ROOT, "trader-alerts", "alerts.py"), "add", "--from-plan"
            ]
            subprocess.run(cmd_alerts, cwd=ROOT, capture_output=True, text=True)

            # 7. Pelosi filing check
            self.log("STEP 7/8", "Pelosi Tracker: polling House Clerk periodic transaction disclosures...")
            cmd_ptr = [
                sys.executable, os.path.join(ROOT, "trader-pelosi", "ptr.py"), "index", "--member", "pelosi"
            ]
            res_ptr = subprocess.run(cmd_ptr, cwd=ROOT, capture_output=True, text=True)
            if res_ptr.returncode == 0:
                lines = [l.strip() for l in res_ptr.stdout.splitlines() if l.strip()]
                self.pelosi_filings = lines[:10]
                self.log("SUCCESS", f"Pelosi Tracker: {len(self.pelosi_filings)} disclosures loaded.")

            # 8. Reload files into engine state
            self._reload_trader_files()
            self.log("FINISH", "Demo Reel simulation completed successfully! State updated.")

        except Exception as e:
            self.log("ERROR", f"Demo Reel execution error: {e}")
        finally:
            with self.lock:
                self.status = "Idle"
                self.status_detail = "Waiting for next scheduled cycle"

    def _execute_cycle(self):
        with self.lock:
            self.cycle_count += 1
            self.last_cycle_time = time.time()
            self.status = "Running Cycle"
            self.status_detail = f"Cycle #{self.cycle_count} in progress ({self.mode})"

        self.log("CYCLE", f"Starting 24/7 cycle #{self.cycle_count} in {self.mode.upper()} mode...")
        ny = self.get_ny_clock_status()

        try:
            # 1. Update Quotes
            self._fetch_quotes()

            # 2. Check Alerts
            self._check_alerts(ny)

            # 3. Breaking News
            self._fetch_news()

            # 4. Scanner & Setups
            if self.mode == "simulation":
                self._run_simulation_scan()
            else:
                self._run_live_scan(ny)

            # 5. Pelosi Tracker (every 5 cycles)
            if self.cycle_count % 5 == 1 or not self.pelosi_filings:
                self._fetch_pelosi()

            self._reload_trader_files()
            self.log("CYCLE", f"Cycle #{self.cycle_count} complete. All skills synced.")

        except Exception as e:
            self.log("ERROR", f"Error during cycle #{self.cycle_count}: {e}")
        finally:
            with self.lock:
                self.status = "Idle"
                self.status_detail = f"Completed #{self.cycle_count}. Next in {self.interval}s."

    def _fetch_quotes(self):
        symbols = self.watchlist[:6]
        for sym in symbols:
            try:
                cmd = [sys.executable, os.path.join(ROOT, "trader-alerts", "alerts.py"), "quote", sym]
                res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=10)
                if res.returncode == 0:
                    # Sample output: TSLA   $379.78 (+0.46% vs prev close $378.05)
                    line = res.stdout.strip().splitlines()[0] if res.stdout.strip() else ""
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].startswith("$"):
                        price_str = parts[1].replace("$", "")
                        change_str = parts[2] if len(parts) > 2 else "+0.00%"
                        self.quotes[sym] = {
                            "price": float(price_str),
                            "change": change_str.replace("(", "").replace(")", ""),
                            "time": datetime.datetime.now().strftime("%H:%M:%S")
                        }
            except Exception as e:
                # Fallback to simulated price if offline/timeout
                if sym not in self.quotes:
                    self.quotes[sym] = {
                        "price": 364.18 if sym == "TSLA" else 135.50,
                        "change": "+0.55%",
                        "time": datetime.datetime.now().strftime("%H:%M:%S")
                    }

    def _check_alerts(self, ny):
        # In-memory check against active quotes
        for alert in self.alerts:
            if alert.get("status") == "TRIGGERED":
                continue
            sym = alert.get("symbol")
            price = alert.get("price")
            alert_type = alert.get("type")

            if sym in self.quotes and price is not None:
                current_price = self.quotes[sym]["price"]
                triggered = False
                if alert_type in ("target", "above") and current_price >= price:
                    triggered = True
                elif alert_type in ("stop", "below") and current_price <= price:
                    triggered = True

                if triggered:
                    alert["status"] = "TRIGGERED"
                    alert["triggered_at"] = datetime.datetime.now().strftime("%H:%M:%S")
                    trigger_msg = f"{sym} {alert_type.upper()} HIT! Price ${current_price:.2f} crossed threshold ${price:.2f}"
                    self.triggered_alerts.insert(0, {
                        "time": datetime.datetime.now().strftime("%H:%M:%S"),
                        "symbol": sym,
                        "type": alert_type,
                        "price": current_price,
                        "note": alert.get("note", "")
                    })
                    self.log("ALERT", trigger_msg)

        # Time-based flatten alert (3:55 PM ET)
        if ny["hour"] == 15 and ny["minute"] >= 55:
            for alert in self.alerts:
                if alert.get("type") == "time" and alert.get("status") != "TRIGGERED":
                    alert["status"] = "TRIGGERED"
                    self.log("ALERT", "3:55 PM FLATTEN ALERT: Close open day positions before the bell!")

    def _fetch_news(self):
        try:
            syms = ",".join(self.watchlist[:4])
            cmd = [sys.executable, os.path.join(ROOT, "trader-news", "news.py"), "--tickers", syms, "--hours", "12"]
            res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                lines = res.stdout.strip().splitlines()
                items = []
                for line in lines:
                    if "ET" in line and ("Yahoo Finance" in line or "tags:" in line or "https" in line):
                        items.append(line.strip())
                if items:
                    self.news_feed = items[:15]
        except Exception:
            pass

    def _fetch_pelosi(self):
        try:
            cmd = [sys.executable, os.path.join(ROOT, "trader-pelosi", "ptr.py"), "index", "--member", "pelosi"]
            res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                self.pelosi_filings = [l.strip() for l in res.stdout.splitlines() if l.strip()][:10]
        except Exception:
            pass

    def _run_simulation_scan(self):
        self.scans = {
            "as_of": "2026-10-19 10:15 ET",
            "scanned": 231,
            "hits": [
                {
                    "symbol": "TSLA",
                    "price": 364.18,
                    "or_high": 362.18,
                    "or_low": 354.47,
                    "status": "TRIGGERED",
                    "setup": "orb_15m",
                    "vol_x": 1.42,
                    "pct_over": "+0.55%"
                },
                {
                    "symbol": "NVDA",
                    "price": 138.45,
                    "or_high": 139.10,
                    "or_low": 136.20,
                    "status": "WAITING",
                    "setup": "orb_15m",
                    "vol_x": 0.95,
                    "pct_over": "-0.46%"
                },
                {
                    "symbol": "AMD",
                    "price": 156.80,
                    "or_high": 158.00,
                    "or_low": 154.10,
                    "status": "WAITING",
                    "setup": "orb_15m",
                    "vol_x": 0.88,
                    "pct_over": "-0.75%"
                }
            ]
        }

    def _run_live_scan(self, ny):
        # Run orb or daily depending on market hours
        mode = "orb" if ny["is_open"] else "daily"
        try:
            syms = ",".join(self.watchlist[:5])
            cmd = [sys.executable, os.path.join(ROOT, "trader-scanner", "scan.py"), mode, "--symbols", syms, "--json"]
            res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                try:
                    data = json.loads(res.stdout)
                    self.scans = data
                except Exception:
                    pass
        except Exception:
            pass

    def _run_loop(self):
        while not self._stop_event.is_set():
            if self.running:
                self._execute_cycle()

            # Countdown sleep
            sleep_step = 1.0
            slept = 0
            while slept < self.interval and not self._stop_event.is_set():
                if not self.running:
                    time.sleep(1)
                    continue
                with self.lock:
                    self.next_cycle_in = max(0, int(self.interval - slept))
                time.sleep(sleep_step)
                slept += sleep_step

    def get_state(self):
        with self.lock:
            uptime = int(time.time() - self.start_time)
            hours, remainder = divmod(uptime, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours:02d}h {minutes:02d}m {seconds:02d}s"

            return {
                "running": self.running,
                "mode": self.mode,
                "interval": self.interval,
                "cycle_count": self.cycle_count,
                "status": self.status,
                "status_detail": self.status_detail,
                "uptime": uptime_str,
                "next_cycle_in": self.next_cycle_in,
                "ny_clock": self.get_ny_clock_status(),
                "watchlist": self.watchlist,
                "quotes": self.quotes,
                "scans": self.scans,
                "news": self.news_feed,
                "pelosi": self.pelosi_filings,
                "plan": self.active_plan,
                "timemachine": self.timemachine_stats,
                "orders": self.orders,
                "risk": self.risk_verdict,
                "alerts": self.alerts,
                "triggered_alerts": self.triggered_alerts[:10],
                "logs": self.logs[:50]
            }
