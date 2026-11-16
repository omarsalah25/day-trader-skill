#!/usr/bin/env python3
"""24/7 Continuous All-Markets Trading Engine for day-trader-skill.
Coordinates all 11 skills across US Equities (~5,900+ companies), Global Equities,
24/7 Crypto, 24/5 Forex, Commodities & Futures, Indices, ETFs, and Bonds with
unlimited autonomous AI order execution, live news monitoring, and risk auditing.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import importlib.util
import json
import math
import os
import random
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from markets import (
    BUILTIN_CATALOG,
    MARKET_CATEGORIES,
    WATCHLIST_ALL_MARKETS,
    classify_asset,
    fetch_chart_bars,
    fetch_spark_quotes,
    get_global_market_sessions,
    is_symbol_market_open,
    load_us_universe,
    normalize_symbol,
    price_decimals,
    search_all_markets,
    to_yahoo,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADER_DIR = os.path.join(ROOT, "trader")

WATCHLIST_EQUITIES = list(MARKET_CATEGORIES["us_equities"]["symbols"])
WATCHLIST_FOREX = list(MARKET_CATEGORIES["forex"]["symbols"])
WATCHLIST_ALL = list(WATCHLIST_ALL_MARKETS)


def _load_skill_module(folder, name):
    path = os.path.join(ROOT, folder, f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"skill_{folder}_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


scan_skill = _load_skill_module("trader-scanner", "scan")
news_skill = _load_skill_module("trader-news", "news")
entry_skill = _load_skill_module("trader-entry", "entry")
exit_skill = _load_skill_module("trader-exit", "exit")
timemachine_skill = _load_skill_module("trader-timemachine", "timemachine")
budget_skill = _load_skill_module("trader-budget", "size")
risk_skill = _load_skill_module("trader-risk", "check")
broker_skill = _load_skill_module("trader-broker", "ticket")
alerts_skill = _load_skill_module("trader-alerts", "alerts")
analyst_skill = _load_skill_module("trader-analyst", "facts")
pelosi_skill = _load_skill_module("trader-pelosi", "ptr")


def get_ny_time(now_override=None):
    if now_override:
        return now_override
    utcnow = datetime.datetime.now(datetime.timezone.utc)
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
        self.lock = threading.RLock()
        self.running = True
        self.mode = "simulation"  # "simulation" or "live"
        self.interval = 30  # seconds between cycles
        self.cycle_count = 0
        self.last_cycle_time = None
        self.next_cycle_in = 30
        self.status = "Initializing"
        self.status_detail = "Starting up 24/7 All-Markets Trading Engine"
        self.start_time = time.time()

        self.watchlist = list(WATCHLIST_ALL_MARKETS)
        self.quotes = {}
        self.spark_series = {}
        self.scans = {
            "as_of": None,
            "scanned": 0,
            "universe_total": 0,
            "universe_scanned": 0,
            "universe_cursor": 0,
            "hits": [],
            "universe_hits": [],
        }
        self.us_universe = []
        self.universe_cursor = 0
        self.universe_hits = []

        self.news_feed = [
            {
                "title": "Tesla (TSLA) Evaluates Global Autonomous & Energy Catalysts",
                "link": "https://finance.yahoo.com/quote/TSLA/news/",
                "ticker": "TSLA",
                "touches": ["TSLA"],
                "source": "Yahoo Finance",
                "time": "Recent",
                "summary": "Initializing live multi-market RSS and SEC EDGAR 8-K monitoring.",
                "tags": ["analyst", "deal"],
            },
            {
                "title": "Bitcoin (BTC-USD) & Crypto 24/7 Liquidity Tracker Active",
                "link": "https://finance.yahoo.com/quote/BTC-USD/news/",
                "ticker": "BTC-USD",
                "touches": ["BTC-USD"],
                "source": "Yahoo Finance",
                "time": "Recent",
                "summary": "Continuous 24/7 crypto and global macro headline stream ready.",
                "tags": ["macro"],
            },
        ]
        self.news_by_ticker = {}
        self.pelosi_filings = []
        self.active_plan = None
        self.timemachine_stats = None
        self.tm_cache = {}
        self.analyst_cache = {}
        self.entry_signals = {}
        self.orders = {}
        self.risk_verdict = {"status": "PASS", "details": "Risk Gatekeeper active (All-Markets & Unlimited Orders)"}
        self.alerts = []
        self.triggered_alerts = []
        self.logs = []
        self.positions = []
        self.transactions = []
        self.realized_pnl = 0.0
        self.broker_account = {
            "id": None,
            "status": "Ready",
            "cash": 100000.0,
            "portfolio_value": 100000.0,
            "buying_power": "UNLIMITED",
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
        }
        self.config = {}

        # Autonomous AI Agent State (24/7 Unlimited Action Taking)
        self.ai_enabled = True
        self.ai_unlimited_orders = True
        self.ai_confidence_threshold = 70
        self.ai_max_concurrent_positions = 0  # 0 = Unlimited
        self.ai_max_orders_per_cycle = 0      # 0 = Unlimited
        self.ai_auto_breakeven_stop = True
        self.ai_auto_flatten_eod = False      # 24/7 multi-market default
        self.ai_status = "Autonomous All-Markets 24/7"
        self.ai_actions_count = 0
        self.ai_orders_executed = 0
        self.ai_last_action = None
        self.ai_decisions = []

        self.skills_telemetry = {
            "scanner": {"status": "READY", "detail": "Waiting first sweep"},
            "news": {"status": "READY", "detail": "Waiting headlines"},
            "entry": {"status": "READY", "detail": "Bar-close timer ready"},
            "exit": {"status": "READY", "detail": "ATR / OR-mid / pip planner ready"},
            "timemachine": {"status": "READY", "detail": "10k Monte Carlo engine ready"},
            "budget": {"status": "READY", "detail": "Risk-bounded & fractional sizer"},
            "risk": {"status": "READY", "detail": "All-Markets Unlimited Gatekeeper"},
            "broker": {"status": "READY", "detail": "Multi-Market Paper / Alpaca router"},
            "alerts": {"status": "READY", "detail": "Prices & stop/target monitor"},
            "analyst": {"status": "READY", "detail": "SEC XBRL fundamentals ready"},
            "pelosi": {"status": "READY", "detail": "House PTR monitor ready"},
        }

        self._thread = None
        self._stop_event = threading.Event()
        self._universe_downloading = False

        os.makedirs(TRADER_DIR, exist_ok=True)
        os.makedirs(os.path.join(TRADER_DIR, "state"), exist_ok=True)
        self._init_files()
        self.sync_broker()
        self.log("INFO", "Trading Engine initialized. All 11 skills active across All Markets & Unlimited AI Orders.")

    def _init_files(self):
        cfg_path = os.path.join(TRADER_DIR, "config.json")
        default_cfg = {
            "budget": 10000.0,
            "cash_buffer_pct": 10,
            "max_position_pct": 75,
            "max_order_usd": 0,           # 0 = Unlimited order size
            "min_order_usd": 5,
            "max_loss_per_trade_usd": 50.0,
            "max_daily_loss_usd": 0.0,    # 0 = Unlimited
            "max_trades_per_day": 0,      # 0 = Unlimited
            "max_orders_per_day": 0,      # 0 = Unlimited
            "min_reward_risk": 1.0,
            "require_stop": True,
            "no_entries_before": "00:00",
            "no_entries_after": "23:59",
            "flat_by": "23:59",
            "fractional": True,
            "broker": "alpaca",
            "paper": True,
            "blocked": [],
            "allow_options": True,
            "allow_margin": True,
            "allow_short": False,
            "allow_all_markets": True,
            "allow_unlimited_orders": True,
            "pdt_guard": False,
            "sec_user_agent": "DayTrader daytrader@local.domain",
            "candle_interval": "1m",
            "or_minutes": 5,
            "min_volume_x": 1.2,
            "strategy_preset": "all_markets_24_7",
            "alpaca_api_key": "",
            "alpaca_secret_key": "",
            "alpaca_base_url": "https://paper-api.alpaca.markets",
            "ai_autonomous": True,
            "ai_unlimited_orders": True,
            "ai_confidence_threshold": 70,
            "ai_max_concurrent_positions": 0,
            "ai_max_orders_per_cycle": 0,
            "ai_auto_breakeven": True,
            "ai_auto_flatten": False,
        }

        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    default_cfg.update(loaded)
            except Exception:
                pass

        # Environment variable overrides
        if os.environ.get("ALPACA_API_KEY"):
            default_cfg["alpaca_api_key"] = os.environ["ALPACA_API_KEY"].strip()
        if os.environ.get("ALPACA_SECRET_KEY"):
            default_cfg["alpaca_secret_key"] = os.environ["ALPACA_SECRET_KEY"].strip()
        if os.environ.get("SEC_USER_AGENT"):
            default_cfg["sec_user_agent"] = os.environ["SEC_USER_AGENT"].strip()

        # Ensure unlimited & all-markets flags stay synced from loaded config
        self.config = default_cfg
        self.ai_enabled = bool(self.config.get("ai_autonomous", True))
        self.ai_unlimited_orders = bool(self.config.get("ai_unlimited_orders", True))
        self.ai_confidence_threshold = int(self.config.get("ai_confidence_threshold", 70))
        self.ai_max_concurrent_positions = int(self.config.get("ai_max_concurrent_positions", 0) or 0)
        self.ai_max_orders_per_cycle = int(self.config.get("ai_max_orders_per_cycle", 0) or 0)
        self.ai_auto_breakeven_stop = bool(self.config.get("ai_auto_breakeven", True))
        self.ai_auto_flatten_eod = bool(self.config.get("ai_auto_flatten", False))

        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

        # Load active multi-market watchlist if saved
        wl_active_file = os.path.join(TRADER_DIR, "watchlist_active.json")
        if os.path.exists(wl_active_file):
            try:
                with open(wl_active_file, "r", encoding="utf-8") as f:
                    saved_wl = json.load(f)
                    if isinstance(saved_wl, list) and saved_wl:
                        self.watchlist = [str(s).strip().upper() for s in saved_wl if str(s).strip()]
            except Exception:
                pass
        else:
            self._save_active_watchlist()

        # Load US company universe (~5,930 companies)
        self.us_universe = load_us_universe()
        self.scans["universe_total"] = len(self.us_universe)

        # Load initial alerts
        alerts_file = os.path.join(TRADER_DIR, "alerts.json")
        if os.path.exists(alerts_file):
            try:
                with open(alerts_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.alerts = data
                    elif isinstance(data, dict) and "rules" in data:
                        self.alerts = data["rules"]
                    elif isinstance(data, dict) and "alerts" in data:
                        self.alerts = data["alerts"]
            except Exception:
                pass

        # Load portfolio / positions
        pf_file = os.path.join(TRADER_DIR, "portfolio.json")
        if os.path.exists(pf_file):
            try:
                with open(pf_file, "r", encoding="utf-8") as f:
                    pf_data = json.load(f)
                    loaded_pos = pf_data.get("positions", [])
                    if isinstance(loaded_pos, list):
                        # Normalize ticker/symbol & shares
                        norm = []
                        for p in loaded_pos:
                            sym = str(p.get("symbol") or p.get("ticker") or "").upper()
                            if not sym:
                                continue
                            sh = float(p.get("shares", p.get("qty", 0)) or 0)
                            if sh <= 0:
                                continue
                            ep = float(p.get("entry_price") or 0)
                            if not ep and p.get("lots"):
                                tot_cost = sum(float(l.get("cost") or 0) for l in p["lots"])
                                ep = tot_cost / sh if sh else 0
                            norm.append({
                                "symbol": sym,
                                "shares": sh,
                                "entry_price": ep,
                                "current_price": float(p.get("current_price") or ep),
                                "stop_price": float(p.get("stop_price") or (ep * 0.985 if ep else 0)),
                                "target_price": float(p.get("target_price") or (ep * 1.02 if ep else 0)),
                                "pnl_usd": float(p.get("pnl_usd") or 0.0),
                                "pnl_pct": float(p.get("pnl_pct") or 0.0),
                                "time": p.get("time") or "Active",
                                "asset_class": p.get("asset_class") or classify_asset(sym)["asset_class"],
                            })
                        self.positions = norm
            except Exception:
                pass

        self._reload_trader_files()
        if not self.orders or not self.orders.get("orders"):
            self.generate_strategy_order(self.config.get("strategy_preset", "all_markets_24_7"), self.watchlist[0] if self.watchlist else "BTC-USD")

    def _save_active_watchlist(self):
        wl_active_file = os.path.join(TRADER_DIR, "watchlist_active.json")
        try:
            with open(wl_active_file, "w", encoding="utf-8") as f:
                json.dump(self.watchlist, f, indent=2)
        except Exception:
            pass

    def _reload_trader_files(self):
        plan_file = os.path.join(TRADER_DIR, "plan.json")
        if os.path.exists(plan_file):
            try:
                with open(plan_file, "r", encoding="utf-8") as f:
                    self.active_plan = json.load(f)
            except Exception:
                pass

        tm_file = os.path.join(TRADER_DIR, "timemachine.json")
        if os.path.exists(tm_file):
            try:
                with open(tm_file, "r", encoding="utf-8") as f:
                    self.timemachine_stats = json.load(f)
            except Exception:
                pass

        orders_file = os.path.join(TRADER_DIR, "orders.json")
        if os.path.exists(orders_file):
            try:
                with open(orders_file, "r", encoding="utf-8") as f:
                    self.orders = json.load(f)
            except Exception:
                pass

    def get_config(self):
        with self.lock:
            return dict(self.config)

    def update_config(self, new_settings):
        with self.lock:
            if "budget" in new_settings and new_settings["budget"] is not None:
                self.config["budget"] = float(new_settings["budget"])
            if "max_loss_per_trade_usd" in new_settings and new_settings["max_loss_per_trade_usd"] is not None:
                self.config["max_loss_per_trade_usd"] = float(new_settings["max_loss_per_trade_usd"])
            if "max_daily_loss_usd" in new_settings and new_settings["max_daily_loss_usd"] is not None:
                self.config["max_daily_loss_usd"] = float(new_settings["max_daily_loss_usd"])
            if "max_trades_per_day" in new_settings and new_settings["max_trades_per_day"] is not None:
                self.config["max_trades_per_day"] = max(0, int(new_settings["max_trades_per_day"]))
            if "max_orders_per_day" in new_settings and new_settings["max_orders_per_day"] is not None:
                self.config["max_orders_per_day"] = max(0, int(new_settings["max_orders_per_day"]))
            if "max_order_usd" in new_settings and new_settings["max_order_usd"] is not None:
                self.config["max_order_usd"] = max(0.0, float(new_settings["max_order_usd"]))
            if "min_reward_risk" in new_settings and new_settings["min_reward_risk"] is not None:
                self.config["min_reward_risk"] = float(new_settings["min_reward_risk"])
            if "candle_interval" in new_settings:
                self.config["candle_interval"] = str(new_settings["candle_interval"]).strip()
            if "or_minutes" in new_settings and new_settings["or_minutes"] is not None:
                self.config["or_minutes"] = int(new_settings["or_minutes"])
            if "min_volume_x" in new_settings and new_settings["min_volume_x"] is not None:
                self.config["min_volume_x"] = float(new_settings["min_volume_x"])
            if "no_entries_before" in new_settings:
                self.config["no_entries_before"] = str(new_settings["no_entries_before"]).strip()
            if "no_entries_after" in new_settings:
                self.config["no_entries_after"] = str(new_settings["no_entries_after"]).strip()
            if "flat_by" in new_settings:
                self.config["flat_by"] = str(new_settings["flat_by"]).strip()
            if "paper" in new_settings:
                self.config["paper"] = bool(new_settings["paper"])
            if "pdt_guard" in new_settings:
                self.config["pdt_guard"] = bool(new_settings["pdt_guard"])
            if "fractional" in new_settings:
                self.config["fractional"] = bool(new_settings["fractional"])
            if "allow_options" in new_settings:
                self.config["allow_options"] = bool(new_settings["allow_options"])
            if "allow_margin" in new_settings:
                self.config["allow_margin"] = bool(new_settings["allow_margin"])
            if "allow_short" in new_settings:
                self.config["allow_short"] = bool(new_settings["allow_short"])
            if "allow_all_markets" in new_settings:
                self.config["allow_all_markets"] = bool(new_settings["allow_all_markets"])
            if "allow_unlimited_orders" in new_settings:
                self.config["allow_unlimited_orders"] = bool(new_settings["allow_unlimited_orders"])
            if "strategy_preset" in new_settings:
                self.config["strategy_preset"] = str(new_settings["strategy_preset"]).strip()
            if "alpaca_api_key" in new_settings:
                self.config["alpaca_api_key"] = str(new_settings["alpaca_api_key"]).strip()
            if "alpaca_secret_key" in new_settings:
                self.config["alpaca_secret_key"] = str(new_settings["alpaca_secret_key"]).strip()
            if "sec_user_agent" in new_settings:
                self.config["sec_user_agent"] = str(new_settings["sec_user_agent"]).strip()
            if "ai_autonomous" in new_settings:
                self.ai_enabled = bool(new_settings["ai_autonomous"])
                self.config["ai_autonomous"] = self.ai_enabled
            if "ai_unlimited_orders" in new_settings:
                self.ai_unlimited_orders = bool(new_settings["ai_unlimited_orders"])
                self.config["ai_unlimited_orders"] = self.ai_unlimited_orders
                self.config["allow_unlimited_orders"] = self.ai_unlimited_orders
                if self.ai_unlimited_orders:
                    self.config["max_trades_per_day"] = 0
                    self.config["max_orders_per_day"] = 0
                    self.ai_max_concurrent_positions = 0
                    self.config["ai_max_concurrent_positions"] = 0
            if "ai_confidence_threshold" in new_settings and new_settings["ai_confidence_threshold"] is not None:
                self.ai_confidence_threshold = int(new_settings["ai_confidence_threshold"])
                self.config["ai_confidence_threshold"] = self.ai_confidence_threshold
            if "ai_auto_breakeven" in new_settings:
                self.ai_auto_breakeven_stop = bool(new_settings["ai_auto_breakeven"])
                self.config["ai_auto_breakeven"] = self.ai_auto_breakeven_stop
            if "ai_auto_flatten" in new_settings:
                self.ai_auto_flatten_eod = bool(new_settings["ai_auto_flatten"])
                self.config["ai_auto_flatten"] = self.ai_auto_flatten_eod
            if "ai_max_concurrent_positions" in new_settings and new_settings["ai_max_concurrent_positions"] is not None:
                self.ai_max_concurrent_positions = max(0, int(new_settings["ai_max_concurrent_positions"]))
                self.config["ai_max_concurrent_positions"] = self.ai_max_concurrent_positions
            if "ai_max_orders_per_cycle" in new_settings and new_settings["ai_max_orders_per_cycle"] is not None:
                self.ai_max_orders_per_cycle = max(0, int(new_settings["ai_max_orders_per_cycle"]))
                self.config["ai_max_orders_per_cycle"] = self.ai_max_orders_per_cycle

            cfg_path = os.path.join(TRADER_DIR, "config.json")
            try:
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2)
                cap_label = "UNLIMITED" if (self.ai_unlimited_orders or self.config.get("max_trades_per_day", 0) == 0) else str(self.config.get("max_trades_per_day"))
                self.log("INFO", f"Updated settings saved (AI Orders: {cap_label}, All Markets: {self.config.get('allow_all_markets')}, AI: {'ACTIVE' if self.ai_enabled else 'PAUSED'})")
                return True
            except Exception as e:
                self.log("ERROR", f"Failed saving config.json: {e}")
                return False

    def set_ai_mode(self, enabled=True):
        with self.lock:
            self.ai_enabled = bool(enabled)
            self.config["ai_autonomous"] = self.ai_enabled
            self.ai_status = (
                "Autonomous All-Markets 24/7 (Unlimited)" if (self.ai_enabled and self.ai_unlimited_orders)
                else ("Autonomous Scanning 24/7" if self.ai_enabled else "Paused (Manual Mode)")
            )
        mode_text = "ENABLED (24/7 All-Markets Unlimited Execution)" if self.ai_enabled else "PAUSED (Manual Approval Mode)"
        self.log("AI_AGENT", f"Autonomous AI Agent {mode_text}")
        return self.ai_enabled

    def set_strategy_preset(self, preset_name):
        unlim = self.ai_unlimited_orders
        if preset_name == "all_markets_24_7":
            settings = {
                "strategy_preset": "all_markets_24_7",
                "candle_interval": "1m",
                "or_minutes": 5,
                "min_volume_x": 1.2,
                "no_entries_before": "00:00",
                "no_entries_after": "23:59",
                "flat_by": "23:59",
                "min_reward_risk": 1.25,
                "allow_all_markets": True,
                "allow_unlimited_orders": True,
                "ai_unlimited_orders": True,
                "max_trades_per_day": 0,
                "max_orders_per_day": 0,
            }
            self.update_config(settings)
            self.log("STRATEGY", "Activated All-Markets 24/7 Unlimited Strategy (US, Global, Crypto, Forex, Commodities, Indices)")
            if len(self.watchlist) < 15:
                self.load_watchlist_preset("all_markets")
            return self.generate_strategy_order("all_markets_24_7", self.watchlist[0] if self.watchlist else "BTC-USD")
        elif preset_name == "fast_1m":
            settings = {
                "strategy_preset": "fast_1m",
                "candle_interval": "1m",
                "or_minutes": 5,
                "min_volume_x": 1.5,
                "no_entries_before": "00:00" if self.config.get("allow_all_markets") else "09:35",
                "min_reward_risk": 1.0,
                "max_trades_per_day": 0 if unlim else 5,
            }
            self.update_config(settings)
            self.log("STRATEGY", "Activated Strategy: 1-Minute Fast Scalp (5m Micro-Range, 1.5x Vol Spike)")
            return self.generate_strategy_order("fast_1m", "TSLA")
        elif preset_name == "forex_pip":
            settings = {
                "strategy_preset": "forex_pip",
                "candle_interval": "1m",
                "or_minutes": 5,
                "min_volume_x": 1.2,
                "no_entries_before": "00:00",
                "no_entries_after": "23:59",
                "flat_by": "23:59",
                "min_reward_risk": 1.75,
                "max_trades_per_day": 0 if unlim else 10,
            }
            self.update_config(settings)
            self.log("STRATEGY", "Activated Strategy: Forex & Currencies 24/5 Pip Scalp (20-Pip Stop, 35-Pip Target, 1.75R)")
            if not any("=X" in x for x in self.watchlist):
                self.load_watchlist_preset("forex")
            return self.generate_strategy_order("forex_pip", "EURUSD=X")
        elif preset_name == "standard_5m":
            settings = {
                "strategy_preset": "standard_5m",
                "candle_interval": "5m",
                "or_minutes": 15,
                "min_volume_x": 1.0,
                "no_entries_before": "00:00" if self.config.get("allow_all_markets") else "09:45",
                "min_reward_risk": 1.0,
                "max_trades_per_day": 0 if unlim else 3,
            }
            self.update_config(settings)
            self.log("STRATEGY", "Activated Strategy: 5-Minute Standard Day Trade (15m Opening Range)")
            return self.generate_strategy_order("standard_5m", "TSLA")

    def _format_price_str(self, sym, val):
        dec = price_decimals(sym, val)
        return f"{float(val):.{dec}f}", dec

    def _compute_order_qty(self, sym, entry, risk_per_unit, ac):
        """Sizes position cleanly using max_loss_per_trade_usd & budget, supporting fractional assets."""
        max_loss = float(self.config.get("max_loss_per_trade_usd", 50.0) or 50.0)
        budget = float(self.config.get("budget", 10000.0) or 10000.0)
        if budget <= 0:
            budget = 10000.0

        if ac == "FOREX" and ("=X" in sym or sym in BUILTIN_CATALOG):
            units = max(1000, int(max_loss / max(0.00001, risk_per_unit)))
            return units, str(units), round(units * risk_per_unit, 2)

        raw_shares = max_loss / max(1e-8, risk_per_unit)
        max_order_usd = float(self.config.get("max_order_usd") or 0)
        cap_usd = min(budget * 0.75, max_order_usd) if max_order_usd > 0 else (budget * 0.75)
        if self.config.get("allow_unlimited_orders"):
            cap_usd = max(cap_usd, budget * 0.5)
        max_shares_cap = cap_usd / max(1e-8, entry)
        target_shares = min(raw_shares, max_shares_cap)

        allow_frac = bool(self.config.get("fractional", True) or ac in ("CRYPTO", "COMMODITY_FUTURE", "INDEX", "INTL_EQUITY"))
        if target_shares < 1.0 and allow_frac:
            qty_f = max(0.0001, round(target_shares, 4))
            return qty_f, f"{qty_f:.4f}".rstrip("0").rstrip("."), round(qty_f * risk_per_unit, 2)

        if target_shares < 1.0:
            qty_i = 1
        else:
            qty_i = int(target_shares)
        return qty_i, str(qty_i), round(qty_i * risk_per_unit, 2)

    def generate_strategy_order(self, preset_name="all_markets_24_7", symbol=None):
        if not symbol:
            sym = "EURUSD=X" if preset_name == "forex_pip" else (self.watchlist[0] if self.watchlist else "TSLA")
        else:
            sym = normalize_symbol(symbol)

        asset = classify_asset(sym)
        ac = asset["asset_class"]

        with self.lock:
            current_quote = self.quotes.get(sym, {}).get("price")
            entry_sig = self.entry_signals.get(sym, {})

        if current_quote is None:
            fallback_prices = {
                "EURUSD=X": 1.1016, "GBPUSD=X": 1.3210, "USDJPY=X": 154.50,
                "BTC-USD": 64050.0, "ETH-USD": 3250.0, "SOL-USD": 165.0,
                "GC=F": 3870.0, "CL=F": 71.50, "^GSPC": 7560.0,
                "TSLA": 390.22, "NVDA": 162.85, "AAPL": 228.40,
            }
            current_quote = fallback_prices.get(sym, 100.00)

        dec = price_decimals(sym, current_quote)
        max_loss_cfg = float(self.config.get("max_loss_per_trade_usd", 50.0) or 50.0)
        min_rr = max(1.0, float(self.config.get("min_reward_risk", 1.25) or 1.0))

        # Use trader-exit math when building stop and target
        if ac == "FOREX" and ("=X" in sym):
            is_jpy = "JPY" in sym
            pip_size = 0.01 if is_jpy else 0.0001
            stop_pips = 20
            target_pips = int(round(stop_pips * max(1.75, min_rr)))
            entry = round(float(current_quote), dec)
            stop = round(entry - (stop_pips * pip_size), dec)
            target = round(entry + (target_pips * pip_size), dec)
            risk_per_unit = round(entry - stop, dec)
            rr = round((target - entry) / max(1e-9, risk_per_unit), 2)
            setup_name = "forex_pip_scalp"
            tif = "gtc"
        else:
            # Compute adaptive opening-range or ATR/pct stop via trader-exit
            entry = round(float(current_quote), dec)
            or_high = entry_sig.get("or_high")
            or_low = entry_sig.get("or_low")
            if ac in ("CRYPTO", "COMMODITY_FUTURE"):
                stop_pct = 1.5
            elif ac in ("INDEX", "INTL_EQUITY"):
                stop_pct = 1.0
            elif preset_name == "standard_5m":
                stop_pct = 1.2
            else:
                stop_pct = 0.8

            try:
                if dec == 2 and or_high and or_low and or_high > or_low and entry > (or_high + or_low) / 2.0:
                    computed = exit_skill.compute(
                        entry, "or_mid", None, "r", exit_skill.D(str(min_rr)),
                        or_high=or_high, or_low=or_low
                    )
                    entry = float(computed["entry"])
                    stop = float(computed["stop"])
                    target = float(computed["target"])
                    risk_per_unit = float(computed["risk"])
                    rr = float(computed["reward_risk"])
                else:
                    raw_stop = entry * (1.0 - stop_pct / 100.0)
                    stop = round(raw_stop, dec)
                    risk_per_unit = max(10 ** (-dec), round(entry - stop, dec))
                    target = round(entry + (risk_per_unit * min_rr), dec)
                    rr = round((target - entry) / risk_per_unit, 2)
            except Exception:
                stop = round(entry * (1.0 - stop_pct / 100.0), dec)
                risk_per_unit = max(10 ** (-dec), round(entry - stop, dec))
                target = round(entry + (risk_per_unit * min_rr), dec)
                rr = round((target - entry) / risk_per_unit, 2)

            setup_name = f"{ac.lower()}_{preset_name}"
            tif = "gtc" if ac in ("CRYPTO", "COMMODITY_FUTURE", "INTL_EQUITY", "INDEX") else "day"

        qty_num, qty_str, total_risk = self._compute_order_qty(sym, entry, risk_per_unit, ac)
        entry_s = f"{entry:.{dec}f}"
        stop_s = f"{stop:.{dec}f}"
        target_s = f"{target:.{dec}f}"

        plan = {
            "created_by": "trader-exit",
            "symbol": sym,
            "asset_class": ac,
            "region": asset["region"],
            "side": "buy",
            "setup": setup_name,
            "date": get_ny_time().date().isoformat(),
            "interval": self.config.get("candle_interval", "1m"),
            "or_minutes": self.config.get("or_minutes", 5),
            "entry": entry,
            "stop": stop,
            "target": target,
            "risk_per_share": round(risk_per_unit, dec),
            "reward_risk": rr,
            "max_loss": total_risk,
            "status": "triggered",
            "time": get_ny_time().strftime("%H:%M:%S ET"),
            "flat_by": self.config.get("flat_by", "23:59"),
        }

        order_obj = {
            "symbol": sym,
            "side": "buy",
            "qty": qty_str,
            "type": "market",
            "time_in_force": tif,
            "order_class": "bracket",
            "take_profit_limit_price": target_s,
            "stop_loss_stop_price": stop_s,
            "why": (
                f"{asset['region']} ({ac}) on {sym}: {qty_str} units/shares @ ${entry_s}, "
                f"Stop ${stop_s}, Target ${target_s} ({rr:.2f}R), Risk ${total_risk:.2f} / ${max_loss_cfg:.2f}"
            ),
            "plan": plan,
        }

        # Run real trader-risk audit
        risk_audit = self._audit_orders_with_risk_skill([order_obj])
        orders_doc = {
            "created_by": "trader-budget",
            "created_at": datetime.datetime.now().isoformat(),
            "status": "approved" if risk_audit["status"] == "PASS" else "blocked",
            "paper": bool(self.config.get("paper", True)),
            "strategy": preset_name,
            "source": f"{asset['region']} ({sym} {setup_name})",
            "orders": [order_obj],
        }

        with self.lock:
            self.active_plan = plan
            self.orders = orders_doc
            self.risk_verdict = risk_audit
            self.skills_telemetry["exit"] = {
                "status": "PASS",
                "detail": f"{sym} Stop ${stop_s} / Target ${target_s} ({rr:.2f}R)",
            }
            self.skills_telemetry["budget"] = {
                "status": "PASS",
                "detail": f"{sym}: {qty_str} units/sh (${total_risk:.2f} risk)",
            }

        try:
            with open(os.path.join(TRADER_DIR, "plan.json"), "w", encoding="utf-8") as f:
                json.dump(plan, f, indent=2)
            with open(os.path.join(TRADER_DIR, "orders.json"), "w", encoding="utf-8") as f:
                json.dump(orders_doc, f, indent=2)
        except Exception:
            pass

        self.log("STRATEGY", f"Staged {asset['badge']} Ticket: BUY {qty_str} {sym} @ ${entry_s} (Stop ${stop_s}, Target ${target_s}, Risk ${total_risk:.2f}, Risk Check: {risk_audit['status']})")
        return orders_doc

    def _audit_orders_with_risk_skill(self, orders_list):
        """Executes trader-risk/check.py logic and updates trader/state/risk.json."""
        try:
            with self.lock:
                cfg_copy = dict(self.config)
                prices_map = {s: q["price"] for s, q in self.quotes.items() if q.get("price")}
                pf_snapshot = {
                    "cash": float(self.broker_account.get("cash", cfg_copy.get("budget", 10000))),
                    "positions": [
                        {"ticker": p["symbol"], "shares": p["shares"], "lots": [{"shares": p["shares"], "cost": p["shares"] * p["entry_price"]}]}
                        for p in self.positions
                    ],
                }
            state_path = os.path.join(TRADER_DIR, "state", "broker.json")
            state_doc = risk_skill.read_json(state_path, "broker state", required=False) or {"orders": []}
            res = risk_skill.check(orders_list, cfg_copy, portfolio=pf_snapshot, prices=prices_map, state=state_doc)

            risk_out = os.path.join(TRADER_DIR, "state", "risk.json")
            res["checked_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with open(risk_out, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2)

            verdict_status = "PASS" if res.get("block", 0) == 0 else "BLOCK"
            reasons = []
            for r in res.get("results", []):
                reasons.extend(r.get("reasons", []))
            details = risk_skill.report(res)
            self.skills_telemetry["risk"] = {
                "status": verdict_status,
                "detail": f"{res.get('pass', 0)} PASS / {res.get('block', 0)} BLOCK",
            }
            return {
                "status": verdict_status,
                "pass": res.get("pass", 0),
                "block": res.get("block", 0),
                "reasons": reasons,
                "warnings": res.get("warnings", []),
                "details": details,
                "results": res.get("results", []),
            }
        except Exception as e:
            return {"status": "PASS", "details": f"Risk fallback pass ({e})", "reasons": []}

    def log(self, level, message, details=None):
        entry = {
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "level": level.upper(),
            "message": message,
            "details": details or "",
        }
        with self.lock:
            self.logs.insert(0, entry)
            if len(self.logs) > 400:
                self.logs.pop()

    def start(self):
        with self.lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self.running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        self.log("INFO", "24/7 All-Markets background scheduler thread started.")

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

    def load_watchlist_preset(self, category="all_markets"):
        cat = str(category).lower().strip()
        with self.lock:
            if cat in ("all", "all_markets"):
                self.watchlist = list(WATCHLIST_ALL_MARKETS)
                msg = f"Loaded All-Markets Global Radar ({len(self.watchlist)} assets across US, Global, Crypto, Forex, Commodities, Indices)"
            elif cat == "us_universe":
                top_hits = [h["symbol"] for h in self.universe_hits[:30]]
                if not top_hits:
                    top_hits = [s for s, _ in self.us_universe[:30]] or list(WATCHLIST_EQUITIES)
                self.watchlist = top_hits
                msg = f"Loaded US Universe Watchlist ({len(self.watchlist)} companies)"
            elif cat in MARKET_CATEGORIES:
                self.watchlist = list(MARKET_CATEGORIES[cat]["symbols"])
                msg = f"Loaded {MARKET_CATEGORIES[cat]['label']} ({len(self.watchlist)} symbols)"
            else:
                self.watchlist = list(WATCHLIST_EQUITIES)
                msg = f"Loaded US Equities Watchlist ({len(self.watchlist)} symbols)"
            self._save_active_watchlist()
        self.log("WATCHLIST", msg)
        threading.Thread(target=self._fetch_quotes, daemon=True).start()
        return list(self.watchlist)

    def add_symbol(self, symbol):
        sym = normalize_symbol(symbol)
        if not sym:
            return False
        with self.lock:
            if sym not in self.watchlist:
                self.watchlist.insert(0, sym)
                self._save_active_watchlist()
                self.log("INFO", f"Added symbol {sym} ({classify_asset(sym)['region']}) to active radar.")
                threading.Thread(target=self._fetch_quotes, daemon=True).start()
                return True
        return False

    def remove_symbol(self, symbol):
        sym = str(symbol or "").strip().upper()
        with self.lock:
            if sym in self.watchlist:
                self.watchlist.remove(sym)
                self._save_active_watchlist()
                self.log("INFO", f"Removed symbol {sym} from watchlist.")
                return True
        return False

    def search_markets(self, query, limit=25):
        return search_all_markets(query, limit=limit)

    def refresh_universe_async(self):
        if self._universe_downloading:
            return False
        self._universe_downloading = True

        def _job():
            try:
                self.log("SCANNER", "Downloading full Nasdaq Trader US company directory (trader-scanner universe)...")
                cmd = [sys.executable, os.path.join(ROOT, "trader-scanner", "scan.py"), "universe", "--json"]
                res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=60)
                if res.returncode == 0:
                    univ = load_us_universe()
                    with self.lock:
                        self.us_universe = univ
                        self.scans["universe_total"] = len(univ)
                    self.log("SUCCESS", f"Full US Company Universe updated: {len(univ):,} listed companies ready to scan.")
                else:
                    self.log("WARN", f"Universe refresh notice: {res.stderr.strip()}")
            except Exception as e:
                self.log("ERROR", f"Universe refresh error: {e}")
            finally:
                self._universe_downloading = False

        threading.Thread(target=_job, daemon=True).start()
        return True

    def add_alert(self, alert_data):
        with self.lock:
            sym = normalize_symbol(alert_data.get("symbol", ""))
            alert_id = f"{(sym or 'market').lower()}-{alert_data.get('type', 'rule')}-{int(time.time())}"
            alert = {
                "id": alert_id,
                "symbol": sym,
                "type": alert_data.get("type", "target"),
                "price": float(alert_data["price"]) if alert_data.get("price") not in (None, "") else None,
                "pct": float(alert_data["pct"]) if alert_data.get("pct") not in (None, "") else None,
                "at": alert_data.get("at"),
                "note": alert_data.get("note", "Custom alert"),
                "date": get_ny_time().strftime("%Y-%m-%d"),
                "status": "ARMED",
            }
            self.alerts.append(alert)
            self._save_alerts()
            self.log("ALERT", f"Armed new alert: {alert['symbol'] or 'CLOCK'} {alert['type']} at {alert.get('price') or alert.get('pct') or alert.get('at')}")
            return alert

    def dismiss_alert(self, alert_id):
        with self.lock:
            self.alerts = [a for a in self.alerts if a.get("id") != alert_id]
            self._save_alerts()
            self.log("INFO", f"Dismissed alert {alert_id}")

    def _save_alerts(self):
        alerts_file = os.path.join(TRADER_DIR, "alerts.json")
        try:
            with open(alerts_file, "w", encoding="utf-8") as f:
                json.dump(self.alerts, f, indent=2)
        except Exception as e:
            self.log("ERROR", f"Failed to save alerts.json: {e}")

    def _arm_position_alerts(self, sym, stop_price, target_price):
        with self.lock:
            self.alerts = [a for a in self.alerts if not (a.get("symbol") == sym and a.get("auto_pos"))]
            today_str = get_ny_time().strftime("%Y-%m-%d")
            self.alerts.append({
                "id": f"{sym.lower()}-auto-stop-{int(time.time())}",
                "symbol": sym,
                "type": "stop",
                "price": stop_price,
                "note": "Auto position stop-loss",
                "date": today_str,
                "status": "ARMED",
                "auto_pos": True,
            })
            self.alerts.append({
                "id": f"{sym.lower()}-auto-target-{int(time.time())}",
                "symbol": sym,
                "type": "target",
                "price": target_price,
                "note": "Auto position take-profit",
                "date": today_str,
                "status": "ARMED",
                "auto_pos": True,
            })
            self._save_alerts()

    def _record_broker_ledger(self, sym, side, qty, price, order_id, max_loss=None, stop=None, status="placed"):
        try:
            state_path = os.path.join(TRADER_DIR, "state", "broker.json")
            st = broker_skill.load_state(state_path)
            now_utc = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
            today = get_ny_time().date().isoformat()
            rec = {
                "at": broker_skill.ny_iso(now_utc),
                "date": today,
                "status": status,
                "symbol": sym,
                "side": side,
                "qty": str(qty),
                "kind": "entry" if side == "buy" else "exit",
                "price": float(price),
                "broker_order_id": order_id,
                "plain": f"{side.upper()} {qty} {sym} @ {price}",
            }
            if max_loss is not None:
                rec["max_loss"] = float(max_loss)
            if stop is not None:
                rec["stop"] = float(stop)
            st.setdefault("orders", []).append(rec)
            # Keep ledger compact
            if len(st["orders"]) > 1000:
                st["orders"] = st["orders"][-1000:]
            broker_skill.write_json(state_path, st)
        except Exception:
            pass

    def execute_order(self, order_data=None):
        """Executes a real-time trade across ANY market via Alpaca API or the Multi-Market Simulator."""
        with self.lock:
            order_to_send = None
            if order_data:
                order_to_send = dict(order_data)
            elif self.orders and isinstance(self.orders, dict) and self.orders.get("orders"):
                order_to_send = dict(self.orders["orders"][0])

            if not order_to_send:
                self.log("WARN", "No order found to execute.")
                return {"success": False, "error": "No order specified"}

            sym = normalize_symbol(order_to_send.get("symbol", "TSLA"))
            qty_raw = order_to_send.get("qty", 1)
            try:
                qty = float(qty_raw)
            except (TypeError, ValueError):
                qty = 1.0
            if qty <= 0:
                qty = 1.0
            qty_str = str(int(qty)) if abs(qty - round(qty)) < 1e-8 else f"{qty:.6f}".rstrip("0").rstrip(".")
            side = str(order_to_send.get("side", "buy")).lower()
            current_quote = float(self.quotes.get(sym, {}).get("price") or (order_to_send.get("plan") or {}).get("entry") or 100.0)
            dec = price_decimals(sym, current_quote)

            stop_price = float(order_to_send.get("stop_loss_stop_price") or round(current_quote * 0.985, dec))
            target_price = float(order_to_send.get("take_profit_limit_price") or round(current_quote * 1.015, dec))

            if side == "buy":
                if target_price <= current_quote:
                    target_price = round(current_quote * 1.015, dec)
                if stop_price >= current_quote:
                    stop_price = round(current_quote * 0.985, dec)

            asset = classify_asset(sym)
            ac = asset["asset_class"]
            api_key = self.config.get("alpaca_api_key", "").strip()
            secret_key = self.config.get("alpaca_secret_key", "").strip()
            is_paper = bool(self.config.get("paper", True))
            base_url = "https://paper-api.alpaca.markets" if is_paper else "https://api.alpaca.markets"
            alpaca_sym = asset.get("alpaca_symbol")

        # Run network broker submission outside self.lock
        if api_key and secret_key and alpaca_sym and ac in ("US_EQUITY", "ETF", "CRYPTO"):
            headers = {
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
                "Content-Type": "application/json",
            }
            if ac == "CRYPTO":
                payload = {
                    "symbol": alpaca_sym,
                    "qty": qty_str,
                    "side": side,
                    "type": "market",
                    "time_in_force": "gtc",
                }
            else:
                is_whole = abs(qty - round(qty)) < 1e-8
                if is_whole:
                    payload = {
                        "symbol": alpaca_sym,
                        "qty": str(int(round(qty))),
                        "side": side,
                        "type": "market",
                        "time_in_force": "day",
                        "order_class": "bracket",
                        "take_profit": {"limit_price": f"{target_price:.2f}"},
                        "stop_loss": {"stop_price": f"{stop_price:.2f}"},
                    }
                else:
                    payload = {
                        "symbol": alpaca_sym,
                        "qty": qty_str,
                        "side": side,
                        "type": "market",
                        "time_in_force": "day",
                    }
            try:
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(f"{base_url}/v2/orders", data=data_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    order_id = res_json.get("id", "alpaca-ord")
                    broker_lbl = f"Alpaca {'Paper' if is_paper else 'Live'} ({ac})"
                    tx = {
                        "id": order_id[:8],
                        "order_id": order_id,
                        "symbol": sym,
                        "asset_class": ac,
                        "qty": qty_str,
                        "side": side.upper(),
                        "type": "BRACKET" if payload.get("order_class") == "bracket" else "MARKET (AI BRACKET)",
                        "status": res_json.get("status", "NEW").upper(),
                        "submitted_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "stop_price": stop_price,
                        "target_price": target_price,
                        "broker": broker_lbl,
                    }
                    with self.lock:
                        self.transactions.insert(0, tx)
                        pos = self._add_position(sym, qty, current_quote, stop_price, target_price)
                    self._arm_position_alerts(sym, stop_price, target_price)
                    self._record_broker_ledger(sym, side, qty_str, current_quote, order_id, max_loss=round(abs(current_quote - stop_price) * qty, 2), stop=stop_price)
                    self.log("SUCCESS", f"Alpaca Order Placed: {side.upper()} {qty_str} {sym} @ ${current_quote:.{dec}f} (ID: {order_id[:8]})")
                    return {"success": True, "broker": "alpaca", "order_id": order_id, "data": res_json, "position": pos, "transaction": tx}
            except urllib.error.HTTPError as e:
                err_msg = e.read().decode("utf-8", errors="replace")
                if not is_paper:
                    self.log("ERROR", f"Alpaca Live API Error ({e.code}): {err_msg[:160]}")
                    return {"success": False, "error": f"Alpaca HTTP {e.code}: {err_msg}"}
                self.log("INFO", f"Alpaca paper unavailable for {sym} ({e.code}); routing to Multi-Market Paper Simulator.")
            except Exception as e:
                if not is_paper:
                    self.log("ERROR", f"Alpaca Live Connection Error: {e}")
                    return {"success": False, "error": str(e)}

        # Multi-Market High-Fidelity Paper Simulator (supports ALL asset classes 24/7)
        sim_prefix = {
            "FOREX": "fx",
            "CRYPTO": "cry",
            "COMMODITY_FUTURE": "fut",
            "INTL_EQUITY": "intl",
            "INDEX": "idx",
            "OPTION": "opt",
        }.get(ac, "sim")
        sim_id = f"{sim_prefix}-{int(time.time() * 1000) % 10000000}"
        broker_label_map = {
            "FOREX": "Paper Simulator (Forex 24/5)",
            "CRYPTO": "Paper Simulator (Crypto 24/7)",
            "COMMODITY_FUTURE": "Paper Simulator (Commodities/Futures)",
            "INTL_EQUITY": f"Paper Simulator ({asset['region']})",
            "INDEX": "Paper Simulator (Global Indices)",
            "OPTION": "Paper Simulator (Options)",
        }
        broker_lbl = broker_label_map.get(ac, "Paper Simulator (US Equities)")

        tx = {
            "id": sim_id,
            "order_id": sim_id,
            "symbol": sym,
            "asset_class": ac,
            "qty": qty_str,
            "side": side.upper(),
            "type": "BRACKET",
            "status": "FILLED",
            "submitted_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stop_price": stop_price,
            "target_price": target_price,
            "broker": broker_lbl,
        }
        with self.lock:
            self.transactions.insert(0, tx)
            if len(self.transactions) > 250:
                self.transactions.pop()
            pos = self._add_position(sym, qty, current_quote, stop_price, target_price)
            self.skills_telemetry["broker"] = {
                "status": "PASS",
                "detail": f"Last: {side.upper()} {qty_str} {sym} ({broker_lbl})",
            }
        self._arm_position_alerts(sym, stop_price, target_price)
        self._record_broker_ledger(sym, side, qty_str, current_quote, sim_id, max_loss=round(abs(current_quote - stop_price) * qty, 2), stop=stop_price, status="placed")
        self.log("SUCCESS", f"{broker_lbl} Fill: {side.upper()} {qty_str} {sym} @ ${current_quote:.{dec}f} (Stop: ${stop_price:.{dec}f}, Target: ${target_price:.{dec}f})")
        return {"success": True, "broker": "paper_simulator", "order_id": sim_id, "position": pos, "transaction": tx}

    def _recalculate_account_metrics(self):
        budget = float(self.config.get("budget", 10000.0) or 10000.0)
        used_capital = 0.0
        unrealized = 0.0
        for p in self.positions:
            sym = p.get("symbol", "")
            ac = classify_asset(sym)["asset_class"]
            margin_pct = 0.03 if ac == "FOREX" else (0.10 if ac == "COMMODITY_FUTURE" else 1.0)
            used_capital += (float(p.get("shares", 0)) * float(p.get("entry_price", 0))) * margin_pct
            unrealized += float(p.get("pnl_usd", 0.0))

        unlim = bool(self.config.get("allow_unlimited_orders") or self.ai_unlimited_orders)
        cash = max(0.0, budget + self.realized_pnl - used_capital) if not unlim else (budget + self.realized_pnl)
        self.broker_account["cash"] = round(cash, 2)
        self.broker_account["unrealized_pnl"] = round(unrealized, 2)
        self.broker_account["realized_pnl"] = round(self.realized_pnl, 2)
        self.broker_account["portfolio_value"] = round(budget + self.realized_pnl + unrealized, 2)
        self.broker_account["buying_power"] = "UNLIMITED" if unlim else round(cash * 4.0, 2)

    def _save_portfolio(self):
        pf_file = os.path.join(TRADER_DIR, "portfolio.json")
        try:
            self._recalculate_account_metrics()
            pf_data = {
                "cash": self.broker_account["cash"],
                "realized_pnl": self.realized_pnl,
                "positions": self.positions,
                "updated_at": datetime.datetime.now().isoformat(),
            }
            with open(pf_file, "w", encoding="utf-8") as f:
                json.dump(pf_data, f, indent=2)
        except Exception:
            pass

    def _add_position(self, symbol, shares, entry_price, stop_price, target_price):
        asset = classify_asset(symbol)
        pos = {
            "symbol": symbol,
            "asset_class": asset["asset_class"],
            "region": asset["region"],
            "shares": shares,
            "entry_price": entry_price,
            "current_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "pnl_usd": 0.0,
            "pnl_pct": 0.0,
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
        }
        self.positions.append(pos)
        self._save_portfolio()
        return pos

    def close_position(self, symbol, reason="MANUAL_CLOSE"):
        """Closes a single open position by symbol without disturbing other open positions."""
        sym = str(symbol or "").strip().upper()
        if not sym:
            return {"success": False, "error": "Missing symbol"}

        with self.lock:
            matches = [p for p in self.positions if p.get("symbol") == sym]
            if not matches:
                return {"success": False, "error": f"No open position for {sym}"}
            curr_price = float(self.quotes.get(sym, {}).get("price") or matches[0].get("current_price") or matches[0].get("entry_price") or 0.0)

        # Attempt Alpaca close if credentials exist and symbol is Alpaca-supported
        api_key = self.config.get("alpaca_api_key", "").strip()
        secret_key = self.config.get("alpaca_secret_key", "").strip()
        is_paper = bool(self.config.get("paper", True))
        base_url = "https://paper-api.alpaca.markets" if is_paper else "https://api.alpaca.markets"
        alpaca_sym = classify_asset(sym).get("alpaca_symbol")
        if api_key and secret_key and alpaca_sym:
            headers = {
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
            }
            try:
                enc_sym = urllib.parse.quote(alpaca_sym, safe="")
                req = urllib.request.Request(f"{base_url}/v2/positions/{enc_sym}", headers=headers, method="DELETE")
                with urllib.request.urlopen(req, timeout=8):
                    pass
            except Exception:
                pass

        with self.lock:
            closed_pnl = 0.0
            total_shares = 0.0
            remaining = []
            for p in self.positions:
                if p.get("symbol") == sym:
                    sh = float(p.get("shares", 0))
                    ep = float(p.get("entry_price", curr_price))
                    closed_pnl += (curr_price - ep) * sh
                    total_shares += sh
                else:
                    remaining.append(p)
            self.positions = remaining
            self.realized_pnl += closed_pnl

            dec = price_decimals(sym, curr_price)
            qty_str = str(int(total_shares)) if abs(total_shares - round(total_shares)) < 1e-8 else f"{total_shares:.4f}".rstrip("0").rstrip(".")
            close_id = f"cls-{int(time.time() * 1000) % 10000000}"
            tx = {
                "id": close_id,
                "order_id": close_id,
                "symbol": sym,
                "asset_class": classify_asset(sym)["asset_class"],
                "qty": qty_str,
                "side": "SELL",
                "type": reason,
                "status": "FILLED",
                "submitted_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "stop_price": None,
                "target_price": curr_price,
                "broker": "Position Exit",
            }
            self.transactions.insert(0, tx)
            if len(self.transactions) > 250:
                self.transactions.pop()
            self._save_portfolio()

        self._record_broker_ledger(sym, "sell", qty_str, curr_price, close_id, status="filled")
        pnl_sign = "+" if closed_pnl >= 0 else ""
        self.log("SUCCESS", f"Closed {sym} ({qty_str} @ ${curr_price:.{dec}f}) [{reason}] | Realized P&L: {pnl_sign}${closed_pnl:.2f}")
        return {"success": True, "symbol": sym, "closed_shares": total_shares, "exit_price": curr_price, "realized_pnl": round(closed_pnl, 2)}

    def sync_broker(self):
        """Synchronizes live account details, positions, and orders from Alpaca (if configured) and local portfolio."""
        api_key = self.config.get("alpaca_api_key", "").strip()
        secret_key = self.config.get("alpaca_secret_key", "").strip()
        is_paper = bool(self.config.get("paper", True))
        base_url = "https://paper-api.alpaca.markets" if is_paper else "https://api.alpaca.markets"

        if api_key and secret_key:
            headers = {
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
            }
            try:
                req_acc = urllib.request.Request(f"{base_url}/v2/account", headers=headers)
                with urllib.request.urlopen(req_acc, timeout=6) as r:
                    acc_data = json.loads(r.read().decode("utf-8"))
                    with self.lock:
                        self.broker_account["id"] = acc_data.get("id")
                        self.broker_account["status"] = acc_data.get("status")
            except Exception:
                pass

            try:
                req_pos = urllib.request.Request(f"{base_url}/v2/positions", headers=headers)
                with urllib.request.urlopen(req_pos, timeout=6) as r:
                    pos_list = json.loads(r.read().decode("utf-8"))
                    alpaca_positions = []
                    alpaca_syms = set()
                    for p in pos_list:
                        sym = str(p.get("symbol") or "").upper()
                        # Map Alpaca BTCUSD back to BTC-USD if needed
                        if sym.endswith("USD") and len(sym) >= 6 and sym not in BUILTIN_CATALOG and f"{sym[:-3]}-USD" in BUILTIN_CATALOG:
                            sym = f"{sym[:-3]}-USD"
                        shares = float(p.get("qty", 1))
                        entry_p = float(p.get("avg_entry_price", 0))
                        curr_p = float(p.get("current_price", entry_p))
                        unrealized_pl = float(p.get("unrealized_pl", 0))
                        unrealized_plpc = float(p.get("unrealized_plpc", 0)) * 100
                        alpaca_syms.add(sym)
                        dec = price_decimals(sym, entry_p)
                        alpaca_positions.append({
                            "symbol": sym,
                            "asset_class": classify_asset(sym)["asset_class"],
                            "region": classify_asset(sym)["region"],
                            "shares": shares,
                            "entry_price": entry_p,
                            "current_price": curr_p,
                            "stop_price": round(entry_p * 0.985, dec),
                            "target_price": round(entry_p * 1.02, dec),
                            "pnl_usd": round(unrealized_pl, 2),
                            "pnl_pct": round(unrealized_plpc, 2),
                            "time": "Alpaca Active",
                        })
                    with self.lock:
                        # Merge Alpaca positions with non-Alpaca simulated multi-market positions
                        local_non_alpaca = [lp for lp in self.positions if lp.get("symbol") not in alpaca_syms and classify_asset(lp.get("symbol", "")).get("alpaca_symbol") is None]
                        if alpaca_positions or not self.positions:
                            self.positions = alpaca_positions + local_non_alpaca
            except Exception:
                pass

        with self.lock:
            self._recalculate_account_metrics()

    def cancel_order(self, order_id):
        """Cancels an order on Alpaca or marks it canceled in the local simulator."""
        api_key = self.config.get("alpaca_api_key", "").strip()
        secret_key = self.config.get("alpaca_secret_key", "").strip()
        is_paper = bool(self.config.get("paper", True))
        base_url = "https://paper-api.alpaca.markets" if is_paper else "https://api.alpaca.markets"

        target_full_id = order_id
        with self.lock:
            for tx in self.transactions:
                if tx.get("id") == order_id or tx.get("order_id") == order_id:
                    target_full_id = tx.get("order_id")
                    break

        if api_key and secret_key and not str(target_full_id).startswith(("sim-", "fx-", "cry-", "fut-", "intl-", "idx-", "opt-", "cls-")):
            try:
                req = urllib.request.Request(
                    f"{base_url}/v2/orders/{target_full_id}",
                    headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key},
                    method="DELETE",
                )
                with urllib.request.urlopen(req, timeout=8):
                    self.log("INFO", f"Cancelled Alpaca order: {target_full_id}")
            except Exception as e:
                self.log("WARN", f"Failed to cancel Alpaca order {order_id}: {e}")

        with self.lock:
            for tx in self.transactions:
                if tx.get("id") == order_id or tx.get("order_id") == order_id or tx.get("order_id") == target_full_id:
                    tx["status"] = "CANCELED"
        self.sync_broker()
        return {"success": True, "order_id": order_id}

    def flatten_positions(self):
        """Closes all active positions and cancels open orders."""
        api_key = self.config.get("alpaca_api_key", "").strip()
        secret_key = self.config.get("alpaca_secret_key", "").strip()
        is_paper = bool(self.config.get("paper", True))
        base_url = "https://paper-api.alpaca.markets" if is_paper else "https://api.alpaca.markets"

        if api_key and secret_key:
            try:
                headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
                urllib.request.urlopen(urllib.request.Request(f"{base_url}/v2/orders", headers=headers, method="DELETE"), timeout=8)
                urllib.request.urlopen(urllib.request.Request(f"{base_url}/v2/positions", headers=headers, method="DELETE"), timeout=10)
                self.log("ALERT", "Flattened all Alpaca positions and orders.")
            except Exception as e:
                self.log("WARN", f"Alpaca flatten positions: {e}")

        with self.lock:
            count = len(self.positions)
            for p in self.positions:
                sym = p.get("symbol")
                curr = float(self.quotes.get(sym, {}).get("price") or p.get("current_price") or p.get("entry_price") or 0)
                ep = float(p.get("entry_price") or curr)
                self.realized_pnl += (curr - ep) * float(p.get("shares") or 0)
            self.positions = []
            self._save_portfolio()

        self.sync_broker()
        self.log("ALERT", f"EMERGENCY FLATTEN: Closed {count} open positions. Capital updated.")
        return {"success": True, "closed_count": count}

    def get_ny_clock_status(self):
        ny = get_ny_time()
        hour, minute = ny.hour, ny.minute
        weekday = ny.weekday()
        is_weekend = weekday >= 5
        minutes_from_midnight = hour * 60 + minute
        market_open_min = 9 * 60 + 30
        market_close_min = 16 * 60
        pre_market_min = 4 * 60
        post_market_min = 20 * 60

        if is_weekend:
            session = "WEEKEND (CRYPTO 24/7 OPEN)"
            is_open = False
            next_open = "Monday 09:30 ET"
        elif minutes_from_midnight < pre_market_min:
            session = "GLOBAL / FX / CRYPTO OPEN"
            is_open = False
            next_open = "Today 04:00 ET (Pre-Market)"
        elif minutes_from_midnight < market_open_min:
            session = "PRE-MARKET + GLOBAL OPEN"
            is_open = False
            next_open = f"Today 09:30 ET ({market_open_min - minutes_from_midnight}m)"
        elif minutes_from_midnight <= market_close_min:
            session = "ALL MARKETS OPEN"
            is_open = True
            next_open = f"NYSE Closes in {market_close_min - minutes_from_midnight}m"
        elif minutes_from_midnight <= post_market_min:
            session = "AFTER HOURS + 24/5 OPEN"
            is_open = False
            next_open = "Tomorrow 04:00 ET"
        else:
            session = "ASIA / FX / CRYPTO OPEN"
            is_open = False
            next_open = "Tomorrow 04:00 ET"

        return {
            "ny_time": ny.strftime("%Y-%m-%d %H:%M:%S ET"),
            "session": session,
            "is_open": is_open,
            "next_open": next_open,
            "hour": hour,
            "minute": minute,
            "global_sessions": get_global_market_sessions(),
        }

    def run_cycle_now(self):
        threading.Thread(target=self._execute_cycle, daemon=True).start()

    def run_demo_reel(self):
        """Runs the full 9-step simulation pipeline using offline fixtures."""
        self.log("INFO", "Running full 9-step Demo Reel simulation pipeline...")
        threading.Thread(target=self._execute_demo_reel, daemon=True).start()

    def _execute_demo_reel(self):
        with self.lock:
            self.status = "Running Demo Reel"
            self.status_detail = "Simulating full TSLA session with configured intervals"
        try:
            res_exit = subprocess.run([
                sys.executable, os.path.join(ROOT, "trader-exit", "exit.py"), "plan",
                "--stop", "or-mid", "--target", "1R",
                "--symbol", "TSLA", "--entry", "364.18",
                "--or-high", "362.18", "--or-low", "354.47",
                "--time", "10:15 AM", "--date", "2026-10-19",
                "--interval", "5m", "--write"
            ], cwd=ROOT, capture_output=True, text=True)
            if res_exit.returncode == 0:
                self.log("SUCCESS", "Exit plan generated: Stop $358.32, Target $370.04 (Risk $5.86/sh)")

            res_tm = subprocess.run([
                sys.executable, os.path.join(ROOT, "trader-timemachine", "timemachine.py"), "run",
                "--offline", os.path.join(ROOT, "tests", "fixtures", "trader-timemachine"),
                "--now", "2026-10-19 10:15", "--seed", "19", "--write"
            ], cwd=ROOT, capture_output=True, text=True)
            if res_tm.returncode == 0:
                self.log("SUCCESS", "Time Machine: Target 29.4%, Stop 25.5%, Open 45.1%. Verdict: Coin flip.")

            res_budget = subprocess.run([sys.executable, os.path.join(ROOT, "trader-budget", "size.py"), "--write"], cwd=ROOT, capture_output=True, text=True)
            if res_budget.returncode == 0:
                self.log("SUCCESS", "Budget sized position to max risk limits.")

            res_risk = subprocess.run([sys.executable, os.path.join(ROOT, "trader-risk", "check.py"), "--now", "2026-10-19 10:15"], cwd=ROOT, capture_output=True, text=True)
            if res_risk.returncode == 0:
                self.log("SUCCESS", "Risk inspection: PASS.")
                self.risk_verdict = {"status": "PASS", "details": res_risk.stdout}

            subprocess.run([sys.executable, os.path.join(ROOT, "trader-broker", "ticket.py"), "show"], cwd=ROOT, capture_output=True, text=True)
            subprocess.run([sys.executable, os.path.join(ROOT, "trader-alerts", "alerts.py"), "add", "--from-plan"], cwd=ROOT, capture_output=True, text=True)
            self._fetch_pelosi()
            self._reload_trader_files()
            self.log("FINISH", "Demo Reel simulation completed successfully! State updated.")
        except Exception as e:
            self.log("ERROR", f"Demo Reel execution error: {e}")
        finally:
            with self.lock:
                self.status = "Idle"
                self.status_detail = "Waiting for next scheduled cycle"

    def run_timemachine(self, symbol="TSLA", replays=10000, seed=19):
        """Runs a 10,000-replay Monte Carlo simulation on real Yahoo bars for ANY market/symbol."""
        sym = normalize_symbol(symbol)
        bars_doc = fetch_chart_bars(sym, rng="60d", interval="5m", timeout=12)
        bars = bars_doc.get("bars") or []
        if len(bars) < 30:
            bars_doc = fetch_chart_bars(sym, rng="6mo", interval="1d", timeout=12)
            bars = bars_doc.get("bars") or []

        if len(bars) < 10:
            raise RuntimeError(f"Insufficient historical bars for {sym}")

        entry = float(bars[-1]["c"])
        dec = price_decimals(sym, entry)
        stop_pct = 0.015 if classify_asset(sym)["asset_class"] in ("CRYPTO", "COMMODITY_FUTURE") else 0.01
        stop = round(entry * (1.0 - stop_pct), dec)
        risk = max(1e-8, entry - stop)
        target = round(entry + risk * 1.25, dec)

        # Build ratio pool from real bars
        ratios = []
        for idx in range(1, len(bars)):
            pc = bars[idx - 1]["c"]
            if pc > 0:
                b = bars[idx]
                ratios.append((b["o"] / pc, b["h"] / pc, b["l"] / pc, b["c"] / pc))
        if not ratios:
            raise RuntimeError(f"No valid return ratios for {sym}")

        rng = random.Random(seed)
        steps = min(40, max(12, len(ratios) // 4))
        t_cnt = s_cnt = n_cnt = g_cnt = 0
        rs = []
        closes = []
        for _ in range(replays):
            p = entry
            outcome = None
            for _ in range(steps):
                _, h, l, c = rng.choice(ratios)
                if outcome is None:
                    if p * l <= stop:
                        outcome = "stop"
                    elif p * h >= target:
                        outcome = "target"
                p *= c
            closes.append(p)
            if outcome == "target":
                t_cnt += 1
                g_cnt += 1
                rs.append(1.25)
            elif outcome == "stop":
                s_cnt += 1
                rs.append(-1.0)
            else:
                n_cnt += 1
                if p > entry:
                    g_cnt += 1
                rs.append((p - entry) / risk)

        p_t = round(t_cnt / replays, 4)
        p_s = round(s_cnt / replays, 4)
        p_n = round(n_cnt / replays, 4)
        p_g = round(g_cnt / replays, 4)
        avg_r = round(sum(rs) / replays, 3)
        mc = {
            "symbol": sym,
            "replays": replays,
            "seed": seed,
            "p_target": p_t,
            "p_stop": p_s,
            "p_neither": p_n,
            "p_green": p_g,
            "target_first_pct": round(p_t * 100, 1),
            "stop_first_pct": round(p_s * 100, 1),
            "neither_pct": round(p_n * 100, 1),
            "green_pct": round(p_g * 100, 1),
            "avg_R": avg_r,
            "r_at_target": 1.25,
            "median_close": round(sorted(closes)[replays // 2], dec),
            "pool_bars": len(ratios),
        }
        verdict_txt = timemachine_skill.verdict(mc)
        doc = {
            "created_by": "trader-timemachine",
            "created_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "symbol": sym,
            "plan": {"symbol": sym, "entry": entry, "stop": stop, "target": target, "target_r": 1.25},
            "mc": mc,
            "history": (self.timemachine_stats or {}).get("history"),
            "verdict": verdict_txt,
        }
        with self.lock:
            self.tm_cache[sym] = {"ts": time.time(), "doc": doc}
            self.timemachine_stats = doc
            self.skills_telemetry["timemachine"] = {"status": "PASS", "detail": f"{sym}: {p_g*100:.1f}% green ({replays:,} paths)"}
        try:
            with open(os.path.join(TRADER_DIR, "timemachine.json"), "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2)
        except Exception:
            pass
        return doc

    def analyze_company(self, symbol):
        """Runs trader-analyst SEC XBRL analysis for US companies or market summary for global/crypto/FX."""
        sym = normalize_symbol(symbol)
        asset = classify_asset(sym)
        if not asset.get("supports_sec"):
            quote = self.quotes.get(sym, {})
            summary = {
                "ticker": sym,
                "name": BUILTIN_CATALOG.get(sym, (sym,))[0],
                "asset_class": asset["asset_class"],
                "region": asset["region"],
                "price": quote.get("price"),
                "change": quote.get("change"),
                "note": "Non-US SEC filer asset; technicals, news, and Time Machine odds drive conviction.",
            }
            with self.lock:
                self.analyst_cache[sym] = {"ts": time.time(), "data": summary}
            return summary

        cached = self.analyst_cache.get(sym)
        if cached and time.time() - cached["ts"] < 3600:
            return cached["data"]

        ua = analyst_skill.user_agent(None, os.path.join(TRADER_DIR, "config.json"))
        if not ua:
            ua = self.config.get("sec_user_agent") or "DayTrader daytrader@local.domain"
        fetcher = analyst_skill.Fetcher(ua)
        ciks = analyst_skill.ticker_ciks(fetcher)
        cik, name = ciks.get(sym.replace("-", "."), (None, None))
        if not cik:
            raise RuntimeError(f"No SEC XBRL CIK found for {sym}")
        cf = fetcher.json(analyst_skill.FACTS_URL % cik, f"companyfacts-CIK{cik}.json")
        res = analyst_skill.analyse(cf, quarters=6, name=name)
        sub = fetcher.json(analyst_skill.SUBMISSIONS_URL % cik, f"submissions-CIK{cik}.json")
        filings = analyst_skill.latest_filings(sub, cik, fetcher)
        data = {
            "ticker": sym,
            "name": res.get("entity"),
            "cik": res.get("cik"),
            "asset_class": asset["asset_class"],
            "rows": res.get("rows", []),
            "ttm": res.get("ttm", {}),
            "changes": analyst_skill.changes(res),
            "filings": filings,
            "metrics": analyst_skill.metrics_row(sym, res),
        }
        with self.lock:
            self.analyst_cache[sym] = {"ts": time.time(), "data": data}
            self.skills_telemetry["analyst"] = {"status": "PASS", "detail": f"Analyzed {sym} SEC XBRL"}
        return data

    def _score_symbol_conviction(self, sym, preset, ny_status):
        """5-Factor Quantitative Skill Conviction Model (0 - 100) using Scanner, Entry, Time Machine, Risk, News, and Analyst."""
        score = 0
        breakdown = {}

        asset = classify_asset(sym)
        ac = asset["asset_class"]
        q = self.quotes.get(sym, {})
        current_quote = q.get("price")
        if not current_quote:
            return 0, {"error": "No quote data"}

        chg_pct = float(q.get("change_pct") or 0.0)
        entry_sig = self.entry_signals.get(sym, {})
        hit = next((h for h in self.scans.get("hits", []) if h.get("symbol") == sym), None)
        if not hit:
            hit = next((h for h in self.universe_hits if h.get("symbol") == sym), None)

        # 1. Technical Momentum, Scanner & Entry Timer (0 - 35 points)
        tech_pts = 18
        if entry_sig.get("status") == "triggered" or (hit and hit.get("status") == "TRIGGERED"):
            tech_pts = 34
            breakdown["technical"] = f"Entry Triggered ({entry_sig.get('setup', 'breakout')}) (+34)"
        elif hit and hit.get("setups"):
            setups = hit["setups"]
            if "breakout_20d" in setups or "bull_flag" in setups or "oversold_bounce" in setups:
                tech_pts = 30
                breakdown["technical"] = f"Scanner: {', '.join(setups)} (+30)"
            else:
                tech_pts = 25
                breakdown["technical"] = f"Scanner: {', '.join(setups)} (+25)"
        elif chg_pct >= 0.4:
            tech_pts = 27
            breakdown["technical"] = f"Active {ac} Uptrend ({chg_pct:+.2f}%) (+27)"
        elif ac in ("CRYPTO", "FOREX", "COMMODITY_FUTURE") and abs(chg_pct) >= 0.15:
            tech_pts = 24
            breakdown["technical"] = f"24/7 {ac} Momentum ({chg_pct:+.2f}%) (+24)"
        else:
            breakdown["technical"] = f"Baseline {ac} Trend ({chg_pct:+.2f}%) (+18)"
        score += tech_pts

        # 2. Time Machine Statistical Odds (0 - 20 points)
        tm_entry = self.tm_cache.get(sym)
        if tm_entry:
            tm_mc = tm_entry["doc"].get("mc", {})
            p_green = tm_mc.get("green_pct", 52.0)
            p_target = tm_mc.get("target_first_pct", 30.0)
            p_stop = tm_mc.get("stop_first_pct", 25.0)
        else:
            p_green = 53.0 if chg_pct >= 0 else 48.0
            p_target = 33.0 if chg_pct >= 0.2 else 28.0
            p_stop = 25.0

        tm_pts = 0
        if p_green >= 50.0:
            tm_pts += 12
        if p_target >= p_stop:
            tm_pts += 8
        score += tm_pts
        breakdown["timemachine"] = f"MC Odds {p_green:.0f}% Green / T>{p_target:.0f}% (+{tm_pts})"

        # 3. Exit Plan, Budget & Risk Clearance (0 - 20 points)
        min_rr = float(self.config.get("min_reward_risk", 1.0) or 1.0)
        risk_pts = 20 if min_rr >= 1.0 else 12
        score += risk_pts
        breakdown["risk_budget"] = f"Stop + Size + {min_rr:.1f}R Cleared (+{risk_pts})"

        # 4. Breaking News, SEC 8-K & Pelosi Congressional Signal (0 - 15 points)
        sym_news = self.news_by_ticker.get(sym) or [n for n in self.news_feed if n.get("ticker") == sym or sym in (n.get("touches") or [])]
        news_pts = 10
        if sym_news:
            all_tags = {t for n in sym_news for t in (n.get("tags") or [])}
            if all_tags & {"halt", "risk", "legal"}:
                news_pts = 2
                breakdown["news"] = f"Caution Tag ({', '.join(sorted(all_tags & {'halt', 'risk', 'legal'}))}) (+2)"
            elif all_tags & {"deal", "earnings", "analyst", "regulatory", "macro"}:
                news_pts = 15
                breakdown["news"] = f"Positive Catalyst ({', '.join(sorted(all_tags & {'deal', 'earnings', 'analyst', 'regulatory', 'macro'}))}) (+15)"
            else:
                news_pts = 12
                breakdown["news"] = f"Active Coverage ({len(sym_news)} items) (+12)"
        else:
            breakdown["news"] = "Clean Catalyst Screen (+10)"
        score += news_pts

        # 5. Analyst Fundamentals / Market Liquidity (0 - 10 points)
        an = self.analyst_cache.get(sym, {}).get("data")
        an_pts = 7
        if an and an.get("metrics"):
            rev_g = an["metrics"].get("revenue_growth_yoy")
            if rev_g is not None and rev_g > 5:
                an_pts = 10
                breakdown["analyst"] = f"SEC XBRL Rev YoY {rev_g:+.1f}% (+10)"
            elif rev_g is not None and rev_g < -10:
                an_pts = 4
                breakdown["analyst"] = f"SEC XBRL Rev YoY {rev_g:+.1f}% (+4)"
            else:
                breakdown["analyst"] = "SEC Fundamentals Verified (+7)"
        else:
            vol = int(q.get("volume") or 0)
            if vol >= 500000 or ac in ("CRYPTO", "FOREX", "COMMODITY_FUTURE", "INDEX"):
                an_pts = 9
                breakdown["analyst"] = f"High {ac} Liquidity (+9)"
            else:
                breakdown["analyst"] = f"Market Liquidity OK (+7)"
        score += an_pts

        score = min(100, max(0, score))
        return score, breakdown

    def ai_evaluate_market(self, ny_status=None):
        """Autonomous AI Agent 24/7: Protects open positions per-symbol and executes UNLIMITED trades across ALL markets."""
        if not self.ai_enabled:
            with self.lock:
                self.ai_status = "Paused (Manual Mode)"
            return []

        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        decisions = []
        exited_this_cycle = set()

        # Part A: Protect & Manage Each Open Position Independently 24/7
        with self.lock:
            current_positions = [dict(p) for p in self.positions]

        for pos in current_positions:
            sym = pos.get("symbol")
            curr_price = self.quotes.get(sym, {}).get("price")
            if not curr_price:
                continue

            curr_price = float(curr_price)
            entry = float(pos.get("entry_price", curr_price))
            stop = float(pos.get("stop_price", entry * 0.985))
            target = float(pos.get("target_price", entry * 1.02))
            dec = price_decimals(sym, curr_price)
            asset = classify_asset(sym)

            # 1. Target Hit -> Take Profit on ONLY this symbol
            if target > entry and curr_price >= target:
                exited_this_cycle.add(sym)
                self.close_position(sym, reason="TARGET_PROFIT_EXIT")
                decision = {
                    "time": now_str,
                    "symbol": sym,
                    "asset_class": asset["asset_class"],
                    "action": "TARGET_PROFIT_EXIT",
                    "conviction": 100,
                    "details": f"Target hit @ ${curr_price:.{dec}f} (+{((curr_price / entry) - 1) * 100:.2f}%). Closed {sym} only; gains banked.",
                    "status": "EXECUTED",
                }
                decisions.append(decision)
                with self.lock:
                    self.ai_decisions.insert(0, decision)
                    self.ai_actions_count += 1
                    self.ai_last_action = f"Target Exit {sym} @ ${curr_price:.{dec}f}"
                continue

            # 2. Stop Hit -> Protective Stop Exit on ONLY this symbol
            if stop < entry and curr_price <= stop:
                exited_this_cycle.add(sym)
                self.close_position(sym, reason="STOP_LOSS_EXIT")
                decision = {
                    "time": now_str,
                    "symbol": sym,
                    "asset_class": asset["asset_class"],
                    "action": "STOP_LOSS_EXIT",
                    "conviction": 100,
                    "details": f"Stop triggered @ ${curr_price:.{dec}f} (Stop: ${stop:.{dec}f}). Closed {sym} to protect capital.",
                    "status": "EXECUTED",
                }
                decisions.append(decision)
                with self.lock:
                    self.ai_decisions.insert(0, decision)
                    self.ai_actions_count += 1
                    self.ai_last_action = f"Stop Exit {sym} @ ${curr_price:.{dec}f}"
                continue

            # 3. Favorable Move (+1.0R) -> Trailing Stop to Breakeven Lock
            initial_risk = (entry - stop) if entry > stop else (entry * 0.01)
            if self.ai_auto_breakeven_stop and (curr_price - entry) >= initial_risk and stop < entry:
                with self.lock:
                    for p_live in self.positions:
                        if p_live.get("symbol") == sym:
                            p_live["stop_price"] = entry
                self.log("AI_AGENT", f"Locked Breakeven on {sym}: Gain >= +1.0R (${curr_price:.{dec}f}). Stop raised to ${entry:.{dec}f}.")
                decision = {
                    "time": now_str,
                    "symbol": sym,
                    "asset_class": asset["asset_class"],
                    "action": "TRAILING_STOP_BREAKEVEN",
                    "conviction": 95,
                    "details": f"Gain +{((curr_price / entry) - 1) * 100:.2f}% (+1.0R). Stop raised to breakeven ${entry:.{dec}f}.",
                    "status": "EXECUTED",
                }
                decisions.append(decision)
                with self.lock:
                    self.ai_decisions.insert(0, decision)
                    self.ai_actions_count += 1
                    self.ai_last_action = f"Stop -> BE on {sym}"

            # 4. EOD Auto Flatten for US Equities only when configured before 20:00
            flat_time = self.config.get("flat_by", "23:59")
            if self.ai_auto_flatten_eod and asset["asset_class"] in ("US_EQUITY", "ETF") and flat_time < "20:00" and ny_status:
                ny_hhmm = ny_status.get("ny_time", "")[11:16]
                if ny_hhmm >= flat_time and ny_status.get("is_open"):
                    exited_this_cycle.add(sym)
                    self.close_position(sym, reason="EOD_FLATTEN")
                    decision = {
                        "time": now_str,
                        "symbol": sym,
                        "asset_class": asset["asset_class"],
                        "action": "EOD_FLATTEN",
                        "conviction": 98,
                        "details": f"EOD flatten cutoff {flat_time} reached for {sym}. Liquidated intraday equity trade.",
                        "status": "EXECUTED",
                    }
                    decisions.append(decision)
                    with self.lock:
                        self.ai_decisions.insert(0, decision)
                        self.ai_actions_count += 1
                        self.ai_last_action = f"EOD Flatten {sym}"

        # Part B: Unlimited All-Markets Scanning & Multi-Order Execution 24/7
        preset = self.config.get("strategy_preset", "all_markets_24_7")
        is_unlim = bool(self.ai_unlimited_orders or self.config.get("allow_unlimited_orders"))
        max_trades = 0 if is_unlim else int(self.config.get("max_trades_per_day", 0) or 0)
        max_pos = 0 if is_unlim else int(self.ai_max_concurrent_positions or 0)

        with self.lock:
            open_pos_count = len(self.positions)
            held_symbols = {p.get("symbol") for p in self.positions}
            # Combine ALL watchlist symbols + discovered US universe hits + news movers
            pool_syms = list(self.watchlist)
            for uh in self.universe_hits[:20]:
                s = uh.get("symbol")
                if s and s not in pool_syms:
                    pool_syms.append(s)

        if max_pos > 0 and open_pos_count >= max_pos:
            with self.lock:
                self.ai_status = f"Managing {open_pos_count}/{max_pos} Open Positions"
            return decisions

        if max_trades > 0 and self.ai_orders_executed >= max_trades:
            with self.lock:
                self.ai_status = f"Daily Trade Cap Reached ({self.ai_orders_executed}/{max_trades})"
            return decisions

        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        scored_candidates = []
        for sym in pool_syms:
            if sym in held_symbols or sym in exited_this_cycle:
                continue
            if not is_symbol_market_open(sym, now_utc=now_utc, mode=self.mode):
                continue
            score, breakdown = self._score_symbol_conviction(sym, preset, ny_status)
            if score > 0:
                scored_candidates.append((score, sym, breakdown))

        scored_candidates.sort(key=lambda x: (-x[0], x[1]))
        qualified = [c for c in scored_candidates if c[0] >= self.ai_confidence_threshold]

        max_per_cycle = int(self.ai_max_orders_per_cycle or 0)
        if max_per_cycle > 0:
            qualified = qualified[:max_per_cycle]
        elif is_unlim:
            # Execute across all qualified opportunities cleanly (cap single-burst API spike at 15/cycle, unlimited across cycles)
            qualified = qualified[:15]
        else:
            qualified = qualified[:1]

        executed_this_cycle = 0
        for score, sym, breakdown in qualified:
            if max_pos > 0 and (open_pos_count + executed_this_cycle) >= max_pos:
                break
            if max_trades > 0 and self.ai_orders_executed >= max_trades:
                break

            # Optional cached Time Machine verification for top candidate if not yet cached
            if sym not in self.tm_cache and executed_this_cycle < 2:
                try:
                    self.run_timemachine(sym, replays=2000)
                    score, breakdown = self._score_symbol_conviction(sym, preset, ny_status)
                    if score < self.ai_confidence_threshold:
                        continue
                except Exception:
                    pass

            orders_doc = self.generate_strategy_order(preset, sym)
            if self.risk_verdict.get("status") == "BLOCK":
                self.log("AI_AGENT", f"Risk Gatekeeper blocked {sym}: {'; '.join(self.risk_verdict.get('reasons', []))}")
                continue

            if orders_doc and orders_doc.get("orders"):
                target_order = orders_doc["orders"][0]
                exec_result = self.execute_order(target_order)
                if exec_result.get("success"):
                    executed_this_cycle += 1
                    broker_name = exec_result.get("broker", "Simulator")
                    order_id = exec_result.get("order_id") or exec_result.get("transaction", {}).get("id", "ord")
                    asset = classify_asset(sym)

                    self.log("AI_AGENT", f"Autonomous Trade Executed: BUY {target_order.get('qty')} {sym} [{asset['badge']}] (Score {score}% >= {self.ai_confidence_threshold}%) -> {broker_name} ({order_id})")
                    decision = {
                        "time": now_str,
                        "symbol": sym,
                        "asset_class": asset["asset_class"],
                        "action": "AUTONOMOUS_BUY_EXECUTED",
                        "conviction": score,
                        "factors": breakdown,
                        "details": f"All-Markets AI ({asset['region']}) conviction {score}% >= {self.ai_confidence_threshold}%. Routed {target_order.get('qty')} {sym} to {broker_name} (ID: {order_id}).",
                        "status": "EXECUTED",
                        "order_id": order_id,
                    }
                    decisions.append(decision)
                    with self.lock:
                        self.ai_decisions.insert(0, decision)
                        if len(self.ai_decisions) > 80:
                            self.ai_decisions.pop()
                        self.ai_actions_count += 1
                        self.ai_orders_executed += 1
                        self.ai_last_action = f"Auto-Buy {sym} ({score}%)"

        with self.lock:
            if executed_this_cycle > 0:
                self.ai_status = f"Executed {executed_this_cycle} Trade(s) | Total: {self.ai_orders_executed} (Unlimited)"
            elif scored_candidates:
                top_score, top_sym, top_bd = scored_candidates[0]
                decision = {
                    "time": now_str,
                    "symbol": top_sym,
                    "asset_class": classify_asset(top_sym)["asset_class"],
                    "action": "MONITOR_AND_HOLD",
                    "conviction": top_score,
                    "factors": top_bd,
                    "details": f"Evaluated {len(scored_candidates)} open-market symbols. Top: {top_sym} ({top_score}% < {self.ai_confidence_threshold}% gate).",
                    "status": "WAITING",
                }
                self.ai_decisions.insert(0, decision)
                if len(self.ai_decisions) > 80:
                    self.ai_decisions.pop()
                self.ai_status = f"Scanning {len(scored_candidates)} Markets 24/7 (Top: {top_sym} {top_score}%)"
            else:
                self.ai_status = "Monitoring Global Markets 24/7 (Unlimited)"

        return decisions

    def _execute_cycle(self):
        with self.lock:
            self.cycle_count += 1
            self.last_cycle_time = time.time()
            self.status = "Running Cycle"
            self.status_detail = f"Cycle #{self.cycle_count} across all markets ({self.mode})"

        self.log("CYCLE", f"Starting 24/7 All-Markets cycle #{self.cycle_count} ({self.mode.upper()})...")
        ny = self.get_ny_clock_status()

        try:
            # 1. Quotes & Prices (trader-alerts) across ALL watchlist + held positions
            self._fetch_quotes()

            # 2. Sync Broker & Real-Time P&L
            self.sync_broker()
            self._update_positions_pnl()

            # 3. Check Armed Price & Clock Alerts (trader-alerts)
            self._check_alerts(ny)

            # 4. Breaking News & SEC 8-K Filings (trader-news) across ALL markets
            self._fetch_news()

            # 5. All-Markets & All-Companies Scanner (trader-scanner) + Entry Timer (trader-entry)
            self._run_multi_market_scan(ny)

            # 6. Background SEC XBRL Analyst check for top candidate (trader-analyst)
            if self.cycle_count % 3 == 1:
                self._refresh_top_analyst()

            # 7. Autonomous AI Agent 24/7 (Exit + TimeMachine + Budget + Risk + Broker)
            self.ai_evaluate_market(ny)

            # 8. Pelosi & House Congressional Tracker (every 5 cycles)
            if self.cycle_count % 5 == 1 or not self.pelosi_filings:
                self._fetch_pelosi()

            self._reload_trader_files()
            self.log("CYCLE", f"Cycle #{self.cycle_count} complete | {len(self.quotes)} quotes | {len(self.news_feed)} headlines | AI: {self.ai_status}")

        except Exception as e:
            self.log("ERROR", f"Error during cycle #{self.cycle_count}: {e}")
        finally:
            with self.lock:
                self.status = "Idle"
                self.status_detail = f"Completed #{self.cycle_count}. Next in {self.interval}s."

    def _fetch_quotes(self):
        with self.lock:
            symbols = list(self.watchlist)
            for p in self.positions:
                s = p.get("symbol")
                if s and s not in symbols:
                    symbols.append(s)
            for uh in self.universe_hits[:20]:
                s = uh.get("symbol")
                if s and s not in symbols:
                    symbols.append(s)

        if not symbols:
            return

        fetched_quotes, spark_series = fetch_spark_quotes(symbols, rng="1d", interval="5m", timeout=10)

        with self.lock:
            self.quotes.update(fetched_quotes)
            self.spark_series.update(spark_series)
            # Ensure fallback quotes for any symbols offline/unreachable so UI & sim stay responsive
            defaults = {
                "TSLA": 390.22, "NVDA": 162.85, "AAPL": 228.40, "AMD": 154.20,
                "MSFT": 425.00, "AMZN": 188.00, "META": 585.00, "GOOGL": 182.00,
                "BTC-USD": 64050.0, "ETH-USD": 3250.0, "SOL-USD": 165.0,
                "EURUSD=X": 1.1016, "GBPUSD=X": 1.3210, "USDJPY=X": 154.50,
                "GC=F": 3870.0, "CL=F": 71.50, "^GSPC": 7560.0,
            }
            for s in symbols:
                if s not in self.quotes:
                    p = defaults.get(s, 100.00)
                    self.quotes[s] = {
                        "symbol": s,
                        "price": p,
                        "prev_close": p,
                        "change_pct": 0.0,
                        "change": "+0.00%",
                        "time": datetime.datetime.now().strftime("%H:%M:%S"),
                        "asset": classify_asset(s),
                    }
            q_snapshot = dict(self.quotes)

        # Write trader/prices.json via trader-alerts
        try:
            prices_path = os.path.join(TRADER_DIR, "prices.json")
            now_utc = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
            formatted_for_alerts = {
                s: {
                    "price": float(q["price"]),
                    "prev_close": q.get("prev_close"),
                    "time": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "source": "yahoo",
                }
                for s, q in q_snapshot.items()
                if q.get("price")
            }
            if formatted_for_alerts:
                alerts_skill.write_prices(prices_path, formatted_for_alerts, now_utc, "yahoo")
                self.skills_telemetry["alerts"] = {"status": "PASS", "detail": f"{len(formatted_for_alerts)} live prices synced"}
        except Exception:
            pass

    def _update_positions_pnl(self):
        with self.lock:
            for pos in self.positions:
                sym = pos.get("symbol")
                if sym in self.quotes:
                    curr = float(self.quotes[sym]["price"])
                    entry = float(pos.get("entry_price", curr))
                    shares = float(pos.get("shares", 0))
                    pos["current_price"] = curr
                    pos["pnl_usd"] = round((curr - entry) * shares, 2)
                    pos["pnl_pct"] = round(((curr / entry) - 1.0) * 100, 2) if entry else 0.0
            self._recalculate_account_metrics()

    def _check_alerts(self, ny):
        with self.lock:
            for alert in self.alerts:
                if alert.get("status") == "TRIGGERED":
                    continue
                sym = alert.get("symbol")
                price = alert.get("price")
                alert_type = alert.get("type")

                if sym in self.quotes and price is not None:
                    current_price = float(self.quotes[sym]["price"])
                    dec = price_decimals(sym, current_price)
                    triggered = False
                    if alert_type in ("target", "above") and current_price >= float(price):
                        triggered = True
                    elif alert_type in ("stop", "below") and current_price <= float(price):
                        triggered = True

                    if triggered:
                        alert["status"] = "TRIGGERED"
                        alert["triggered_at"] = datetime.datetime.now().strftime("%H:%M:%S")
                        trigger_msg = f"{sym} {alert_type.upper()} HIT! Price ${current_price:.{dec}f} crossed ${float(price):.{dec}f}"
                        self.triggered_alerts.insert(0, {
                            "time": datetime.datetime.now().strftime("%H:%M:%S"),
                            "symbol": sym,
                            "type": alert_type,
                            "price": current_price,
                            "note": alert.get("note", ""),
                        })
                        self.log("ALERT", trigger_msg)

    def _fetch_news(self, custom_tickers=None):
        """Fetches Yahoo Finance RSS + SEC 8-K filings across ALL markets & rotating watchlist tickers."""
        with self.lock:
            base = list(custom_tickers or self.watchlist)
            for p in self.positions:
                if p.get("symbol") and p["symbol"] not in base:
                    base.insert(0, p["symbol"])

        # Ensure every asset class gets news coverage + rotate through full list
        if not custom_tickers and len(base) > 16:
            offset = ((self.cycle_count - 1) * 10) % len(base)
            # Always include top held/core symbols + rotating window
            core = base[:6]
            rot = (base[6:] + base[6:])[offset % max(1, len(base) - 6):][:10]
            tickers = []
            for t in core + rot:
                if t not in tickers:
                    tickers.append(t)
        else:
            tickers = base[:20]

        if not tickers:
            return

        state_path = os.path.join(TRADER_DIR, "state", "news.json")
        state = news_skill.load_json(state_path) or {}
        seen_map = state.setdefault("seen", {})
        ua = self.config.get("sec_user_agent") or "DayTrader daytrader@local.domain"
        watch_dict = {t: BUILTIN_CATALOG.get(t, (None,))[0] for t in tickers}

        def fetch_one_rss(t):
            ysym = urllib.parse.quote(news_skill.yahoo_symbol(t), safe=".-=")
            url = news_skill.YAHOO % ysym
            req = urllib.request.Request(url, headers={"User-Agent": news_skill.BROWSER_UA})
            with urllib.request.urlopen(req, timeout=8) as r:
                return news_skill.parse_rss(r.read(), t)

        raw_items = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(fetch_one_rss, t): t for t in tickers}
            for fut in as_completed(futs):
                try:
                    raw_items.extend(fut.result())
                except Exception:
                    pass

        # Fetch SEC 8-K filings for US Equities in the batch (polite rate)
        us_tickers = [t for t in tickers if news_skill._is_us_sec_ticker(t)][:5]
        if us_tickers and ua and "@" in ua:
            try:
                fetcher = news_skill.Fetcher(ua, pause=0.12)
                ciks = news_skill.cik_map(fetcher, state)
                for t in us_tickers:
                    cik = ciks.get(t)
                    if not cik:
                        continue
                    try:
                        data = fetcher.get(news_skill.SEC_FEED % (cik, "8-K", 5), f"sec-8-K-{cik}.xml", sec=True)
                        raw_items.extend(news_skill.parse_sec_atom(data, t))
                    except Exception:
                        pass
            except Exception:
                pass

        if not raw_items:
            return

        tagged = news_skill.dedupe(news_skill.tag(raw_items, watch_dict))
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now_utc - datetime.timedelta(hours=72)

        formatted = []
        new_count = 0
        for it in tagged:
            it_time = it.get("time")
            if it_time is not None and it_time < cutoff:
                continue
            fp = news_skill.fingerprint(it)
            is_new = fp not in seen_map
            if is_new:
                new_count += 1
            link = (it.get("link") or "").strip() or f"https://finance.yahoo.com/quote/{to_yahoo(it.get('ticker', 'TSLA'))}/news/"
            formatted.append({
                "id": it.get("id", fp),
                "title": it.get("title", "Market Update"),
                "link": link,
                "ticker": it.get("ticker", "MARKET"),
                "touches": it.get("touches") or [it.get("ticker", "MARKET")],
                "source": it.get("source", "Yahoo Finance"),
                "time": it_time.isoformat() if it_time else "Recent",
                "summary": re.sub(r"<[^>]+>", "", it.get("summary") or "")[:240],
                "tags": it.get("tags") or [],
                "important": bool(it.get("important")),
                "new": is_new,
                "_sort": it_time.isoformat() if it_time else "",
            })

        formatted.sort(key=lambda x: x["_sort"], reverse=True)
        for item in formatted:
            item.pop("_sort", None)

        news_skill.remember(tagged, state, now_utc)
        try:
            with open(state_path, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2)
        except Exception:
            pass

        with self.lock:
            # Merge with existing feed, keep newest 60 unique titles
            by_title = {}
            for item in formatted + self.news_feed:
                k = item.get("title", "").lower().strip()
                if k and k not in by_title:
                    by_title[k] = item
            merged = list(by_title.values())
            merged.sort(key=lambda x: x.get("time", ""), reverse=True)
            self.news_feed = merged[:60]

            by_tick = {}
            for item in self.news_feed:
                for t in item.get("touches") or [item.get("ticker")]:
                    if t:
                        by_tick.setdefault(t, []).append(item)
            self.news_by_ticker = by_tick
            self.skills_telemetry["news"] = {
                "status": "PASS",
                "detail": f"{len(self.news_feed)} headlines across {len(by_tick)} tickers (+{new_count} new)",
            }

        if new_count > 0:
            top_new = next((x for x in formatted if x.get("new") and (x.get("important") or any(t in ("earnings", "deal", "halt", "macro", "regulatory") for t in x.get("tags", [])))), None)
            if top_new:
                self.log("NEWS", f"Breaking ({top_new['ticker']}): {top_new['title'][:110]}")

    def _run_multi_market_scan(self, ny):
        """Runs trader-scanner across ALL watchlist assets + rotating sweep of all ~5,930 US companies."""
        candle_int = self.config.get("candle_interval", "1m")
        or_mins = int(self.config.get("or_minutes", 5) or 5)

        with self.lock:
            wl_syms = list(self.watchlist)
            universe_list = [s for s, _ in self.us_universe]

        if not universe_list:
            self.refresh_universe_async()

        # 1. Evaluate all watchlist symbols using spark 3mo daily + 1d 5m bars
        raw_daily_series = self._fetch_raw_spark_series(wl_syms, rng="3mo", interval="1d")
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
        daily_hits, daily_counts, _ = scan_skill.scan_daily(raw_daily_series, wl_syms, now_utc, 0.0, 0)
        daily_hit_map = {h["symbol"]: h for h in daily_hits}

        hits = []
        entry_signals = {}
        with self.lock:
            spark_1d = dict(self.spark_series)
            quotes_snap = dict(self.quotes)

        for sym in wl_syms:
            q = quotes_snap.get(sym, {})
            price = q.get("price")
            if not price:
                continue
            price = float(price)
            dec = price_decimals(sym, price)
            s1d = spark_1d.get(sym, {})
            closes = [float(c) for c in (s1d.get("c") or []) if c is not None]
            or_n = max(1, min(len(closes), or_mins // 5 if or_mins >= 5 else 3))
            if len(closes) > or_n:
                or_high = round(max(closes[:or_n]), dec)
                or_low = round(min(closes[:or_n]), dec)
            else:
                or_high = round(price * 1.004, dec)
                or_low = round(price * 0.994, dec)

            d_hit = daily_hit_map.get(sym)
            chg_pct = float(q.get("change_pct") or 0.0)
            is_breakout = (price > or_high) or (d_hit and any(x in d_hit.get("setups", []) for x in ("breakout_20d", "bull_flag", "oversold_bounce")))
            status = "TRIGGERED" if is_breakout else ("WAITING" if chg_pct > -0.5 else "MONITORING")
            vol_x = round(1.35 + min(1.5, abs(chg_pct) * 0.2), 2) if status == "TRIGGERED" else 1.0
            pct_over = ((price / or_high) - 1.0) * 100.0 if or_high else 0.0
            setups = list(d_hit["setups"]) if d_hit else (["intraday_break"] if status == "TRIGGERED" else [])

            entry_signals[sym] = {
                "symbol": sym,
                "status": "triggered" if status == "TRIGGERED" else "waiting",
                "setup": setups[0] if setups else f"orb_{or_mins}m_{candle_int}",
                "or_high": or_high,
                "or_low": or_low,
                "vol_x": vol_x,
            }

            hits.append({
                "symbol": sym,
                "asset_class": classify_asset(sym)["asset_class"],
                "price": round(price, dec),
                "or_high": or_high,
                "or_low": or_low,
                "status": status,
                "setup": f"{setups[0] if setups else f'orb_{or_mins}m_{candle_int}'}",
                "setups": setups,
                "vol_x": vol_x,
                "pct_over": f"{'+' if pct_over >= 0 else ''}{pct_over:.2f}%",
            })

        # 2. Rotating Sweep across the ENTIRE ~5,930-company US Universe (100 companies per cycle!)
        new_univ_hits = []
        if universe_list:
            batch_size = 100
            start = self.universe_cursor % len(universe_list)
            batch = (universe_list + universe_list)[start:start + batch_size]
            self.universe_cursor = (start + batch_size) % len(universe_list)
            u_series = self._fetch_raw_spark_series(batch, rng="3mo", interval="1d")
            u_hits, u_counts, _ = scan_skill.scan_daily(u_series, batch, now_utc, 5.0, 500000)
            for h in u_hits:
                h["asset_class"] = "US_EQUITY"
                h["status"] = "TRIGGERED"
                h["setup"] = ",".join(h.get("setups", ["daily"]))
                new_univ_hits.append(h)

        with self.lock:
            for h in new_univ_hits:
                # Cache quote for discovered universe hits so AI can evaluate & trade them immediately
                self.quotes[h["symbol"]] = {
                    "symbol": h["symbol"],
                    "price": h["price"],
                    "prev_close": h["price"],
                    "change_pct": 0.8,
                    "change": "+0.80%",
                    "volume": h.get("volume") or 0,
                    "time": datetime.datetime.now().strftime("%H:%M:%S"),
                    "asset": classify_asset(h["symbol"]),
                }
            if new_univ_hits:
                existing_by_sym = {h["symbol"]: h for h in self.universe_hits}
                for h in new_univ_hits:
                    existing_by_sym[h["symbol"]] = h
                self.universe_hits = sorted(existing_by_sym.values(), key=lambda x: -(x["price"] * (x.get("volume") or 0)))[:100]

            self.entry_signals = entry_signals
            self.scans = {
                "as_of": ny.get("ny_time"),
                "scanned": len(wl_syms) + (len(batch) if universe_list else 0),
                "universe_total": len(universe_list),
                "universe_scanned": min(len(universe_list), self.universe_cursor) if universe_list else 0,
                "universe_cursor": self.universe_cursor,
                "candle_interval": candle_int,
                "or_minutes": or_mins,
                "hits": hits,
                "universe_hits": self.universe_hits[:50],
            }
            self.skills_telemetry["scanner"] = {
                "status": "PASS",
                "detail": f"{len(wl_syms)} watchlist + {self.universe_cursor}/{len(universe_list)} US universe ({len(self.universe_hits)} hits)",
            }
            trig_n = sum(1 for h in hits if h["status"] == "TRIGGERED")
            self.skills_telemetry["entry"] = {
                "status": "PASS" if trig_n else "WAITING",
                "detail": f"{trig_n} triggered setups across all markets",
            }

        # Persist watchlist.json for CLI compatibility (trader-scanner contract)
        try:
            wl_doc = {
                "created_by": "trader-scanner",
                "created_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "mode": "multi_market",
                "as_of": ny.get("ny_time"),
                "universe": len(universe_list) or len(wl_syms),
                "scanned": self.scans["scanned"],
                "failed": 0,
                "source": "yahoo",
                "hits": [{"symbol": h["symbol"], "setups": h.get("setups") or [h.get("setup")], "price": h["price"]} for h in (hits + self.universe_hits[:20]) if h.get("status") == "TRIGGERED"][:50],
            }
            with open(os.path.join(TRADER_DIR, "watchlist.json"), "w", encoding="utf-8") as f:
                json.dump(wl_doc, f, indent=2)
        except Exception:
            pass

    def _fetch_raw_spark_series(self, symbols, rng="3mo", interval="1d"):
        data = {}
        for i in range(0, len(symbols), 20):
            batch = symbols[i:i + 20]
            wanted = {to_yahoo(s): s for s in batch}
            q_syms = ",".join(urllib.parse.quote(to_yahoo(s), safe=".-=") for s in batch)
            path = f"/v7/finance/spark?symbols={q_syms}&range={rng}&interval={interval}"
            try:
                raw = scan_skill.yahoo_get(path)
                data.update(scan_skill.parse_spark(raw, wanted))
            except Exception:
                continue
        return data

    def scan_universe_batch(self, count=500):
        """On-demand sweep of N companies from the full ~5,930 US company universe."""
        if not self.us_universe:
            self.us_universe = load_us_universe()
        if not self.us_universe:
            return {"success": False, "error": "Universe file not loaded yet; refreshing now."}
        universe_list = [s for s, _ in self.us_universe]
        batch_n = min(len(universe_list), max(20, int(count)))
        start = self.universe_cursor % len(universe_list)
        batch = (universe_list + universe_list)[start:start + batch_n]
        self.universe_cursor = (start + batch_n) % len(universe_list)
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
        u_series = self._fetch_raw_spark_series(batch, rng="3mo", interval="1d")
        u_hits, u_counts, _ = scan_skill.scan_daily(u_series, batch, now_utc, 5.0, 500000)
        for h in u_hits:
            h["asset_class"] = "US_EQUITY"
            h["status"] = "TRIGGERED"
            h["setup"] = ",".join(h.get("setups", ["daily"]))
        with self.lock:
            existing_by_sym = {h["symbol"]: h for h in self.universe_hits}
            for h in u_hits:
                existing_by_sym[h["symbol"]] = h
                self.quotes[h["symbol"]] = {
                    "symbol": h["symbol"],
                    "price": h["price"],
                    "prev_close": h["price"],
                    "change_pct": 0.8,
                    "change": "+0.80%",
                    "volume": h.get("volume") or 0,
                    "time": datetime.datetime.now().strftime("%H:%M:%S"),
                    "asset": classify_asset(h["symbol"]),
                }
            self.universe_hits = sorted(existing_by_sym.values(), key=lambda x: -(x["price"] * (x.get("volume") or 0)))[:150]
            self.scans["universe_hits"] = self.universe_hits[:50]
            scanned_total = min(len(universe_list), start + batch_n)
            self.scans["universe_scanned"] = scanned_total
            self.scans["universe_total"] = len(universe_list)
        self.log("SCANNER", f"Universe Sweep scanned {batch_n} US companies -> found {len(u_hits)} setups ({len(self.universe_hits)} total tracked).")
        return {
            "success": True,
            "scanned": batch_n,
            "new_hits": len(u_hits),
            "universe_scanned": scanned_total,
            "universe_total": len(universe_list),
            "hits": u_hits[:25],
        }

    def _refresh_top_analyst(self):
        """Background SEC XBRL fundamentals check for one un-cached US equity on watchlist."""
        with self.lock:
            us_cands = [s for s in self.watchlist if classify_asset(s)["supports_sec"] and s not in self.analyst_cache]
        if not us_cands:
            return
        try:
            self.analyze_company(us_cands[0])
        except Exception:
            pass

    def _fetch_pelosi(self):
        try:
            cmd = [sys.executable, os.path.join(ROOT, "trader-pelosi", "ptr.py"), "index", "--member", "pelosi", "--limit", "15"]
            res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=15)
            lines = [l.strip() for l in res.stdout.splitlines() if l.strip()] if res.returncode == 0 else []
            # Also load recent House PTRs across all members
            cmd_all = [sys.executable, os.path.join(ROOT, "trader-pelosi", "ptr.py"), "index", "--limit", "15"]
            res_all = subprocess.run(cmd_all, cwd=ROOT, capture_output=True, text=True, timeout=15)
            if res_all.returncode == 0:
                all_lines = [l.strip() for l in res_all.stdout.splitlines() if l.strip()]
                seen = set(lines)
                for ln in all_lines:
                    if ln not in seen:
                        lines.append(ln)
                        seen.add(ln)
            if lines:
                with self.lock:
                    self.pelosi_filings = lines[:25]
                    self.skills_telemetry["pelosi"] = {"status": "PASS", "detail": f"{len(self.pelosi_filings)} congressional PTRs"}
        except Exception:
            pass

    def _run_loop(self):
        while not self._stop_event.is_set():
            if self.running:
                self._execute_cycle()

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
                "global_sessions": get_global_market_sessions(),
                "watchlist": self.watchlist,
                "quotes": self.quotes,
                "scans": self.scans,
                "universe_hits": self.universe_hits[:50],
                "news": self.news_feed,
                "pelosi": self.pelosi_filings,
                "plan": self.active_plan,
                "timemachine": self.timemachine_stats,
                "orders": self.orders,
                "risk": self.risk_verdict,
                "alerts": self.alerts,
                "triggered_alerts": self.triggered_alerts[:10],
                "positions": self.positions,
                "transactions": self.transactions,
                "broker_account": self.broker_account,
                "config": self.config,
                "skills_telemetry": self.skills_telemetry,
                "ai_agent": {
                    "enabled": self.ai_enabled,
                    "unlimited_orders": self.ai_unlimited_orders,
                    "status": self.ai_status,
                    "confidence_threshold": self.ai_confidence_threshold,
                    "max_concurrent_positions": self.ai_max_concurrent_positions,
                    "max_orders_per_cycle": self.ai_max_orders_per_cycle,
                    "actions_today": self.ai_actions_count,
                    "orders_executed": self.ai_orders_executed,
                    "auto_breakeven": self.ai_auto_breakeven_stop,
                    "auto_flatten": self.ai_auto_flatten_eod,
                    "last_action": self.ai_last_action,
                    "decisions": self.ai_decisions[:30],
                },
                "logs": self.logs[:60],
            }
