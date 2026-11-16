import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
RISK_DIR = os.path.join(ROOT, "trader-risk")
for p in (APP_DIR, RISK_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import check as risk_check
import markets


def _setup_temp_trader_dir(tmp_dir, extra_cfg=None):
    trader_dir = os.path.join(tmp_dir, "trader")
    os.makedirs(os.path.join(trader_dir, "state"), exist_ok=True)
    cfg = {
        "budget": 5000.0,
        "max_loss_per_trade_usd": 50.0,
        "max_order_usd": 0.0,
        "max_daily_loss_usd": 0.0,
        "max_trades_per_day": 0,
        "max_orders_per_day": 0,
        "min_reward_risk": 1.0,
        "fractional": True,
        "paper": True,
        "pdt_guard": False,
        "allow_all_markets": True,
        "allow_unlimited_orders": True,
        "ai_unlimited_orders": True,
        "ai_autonomous": True,
        "ai_confidence_threshold": 60,
        "ai_max_concurrent_positions": 0,
        "ai_max_orders_per_cycle": 0,
        "ai_auto_breakeven": True,
        "ai_auto_flatten": False,
        "allow_margin": True,
        "allow_options": True,
        "allow_short": True,
        "no_entries_before": "00:00",
        "no_entries_after": "23:59",
        "flat_by": "23:59",
        "candle_interval": "1m",
        "or_minutes": 5,
        "min_volume_x": 1.0,
        "strategy_preset": "all_markets_24_7",
    }
    if extra_cfg:
        cfg.update(extra_cfg)
    with open(os.path.join(trader_dir, "config.json"), "w") as f:
        json.dump(cfg, f)
    with open(os.path.join(trader_dir, "universe.txt"), "w") as f:
        f.write("AAPL\nMSFT\nNVDA\nTSLA\nPLTR\nBRK.B\nSMCI\nSHOP\nAMD\nSPY\n")
    return trader_dir


class MarketsTests(unittest.TestCase):
    def test_classify_all_asset_classes(self):
        self.assertEqual(markets.classify_asset("TSLA")["asset_class"], "US_EQUITY")
        self.assertEqual(markets.classify_asset("BRK.B")["asset_class"], "US_EQUITY")
        self.assertEqual(markets.classify_asset("7203.T")["asset_class"], "INTL_EQUITY")
        self.assertEqual(markets.classify_asset("ASML.AS")["asset_class"], "INTL_EQUITY")
        self.assertEqual(markets.classify_asset("0700.HK")["asset_class"], "INTL_EQUITY")
        self.assertEqual(markets.classify_asset("BTC-USD")["asset_class"], "CRYPTO")
        self.assertEqual(markets.classify_asset("BTC/USD")["asset_class"], "CRYPTO")
        self.assertEqual(markets.classify_asset("EURUSD=X")["asset_class"], "FOREX")
        self.assertEqual(markets.classify_asset("GC=F")["asset_class"], "COMMODITY_FUTURE")
        self.assertEqual(markets.classify_asset("^GSPC")["asset_class"], "INDEX")
        self.assertEqual(markets.classify_asset("AAPL260116C00250000")["asset_class"], "OPTION")

    def test_to_yahoo_preserves_intl_suffixes_and_converts_us_class_shares(self):
        self.assertEqual(markets.to_yahoo("BRK.B"), "BRK-B")
        self.assertEqual(markets.to_yahoo("7203.T"), "7203.T")
        self.assertEqual(markets.to_yahoo("ASML.AS"), "ASML.AS")
        self.assertEqual(markets.to_yahoo("MC.PA"), "MC.PA")
        self.assertEqual(markets.to_yahoo("BTC/USD"), "BTC-USD")
        self.assertEqual(markets.to_yahoo("EURUSD"), "EURUSD=X")

    def test_search_all_markets_offline_catalog_and_universe(self):
        with tempfile.TemporaryDirectory() as td:
            uni = os.path.join(td, "universe.txt")
            with open(uni, "w") as f:
                f.write("PLTR\nSOUN\nTSLA\n")
            with mock.patch.object(markets, "UNIVERSE_FILE", uni):
                res_toyota = markets.search_all_markets("Toyota", limit=10, use_network=False)
                self.assertTrue(any(r["symbol"] == "7203.T" for r in res_toyota))

                res_btc = markets.search_all_markets("Bitcoin", limit=10, use_network=False)
                self.assertTrue(any(r["symbol"] == "BTC-USD" for r in res_btc))

                res_pltr = markets.search_all_markets("PLTR", limit=10, use_network=False)
                self.assertTrue(any(r["symbol"] == "PLTR" for r in res_pltr))

    def test_global_sessions_crypto_always_open(self):
        sessions = markets.get_global_market_sessions()
        self.assertIn("crypto", sessions)
        self.assertTrue(sessions["crypto"]["open"])
        for key in ("crypto", "forex", "futures", "us", "europe", "asia"):
            self.assertIn(key, sessions)


class UnlimitedAllMarketsRiskTests(unittest.TestCase):
    def test_risk_allows_25_multi_asset_orders_when_unlimited_enabled(self):
        cfg = {
            "budget": 5000.0,
            "max_loss_per_trade_usd": 50.0,
            "max_order_usd": 0.0,
            "max_daily_loss_usd": 0.0,
            "max_trades_per_day": 0,
            "max_orders_per_day": 0,
            "min_reward_risk": 1.0,
            "fractional": True,
            "paper": True,
            "allow_all_markets": True,
            "allow_unlimited_orders": True,
            "no_entries_before": "00:00",
            "no_entries_after": "23:59",
            "flat_by": "23:59",
        }
        symbols = [
            "TSLA", "NVDA", "AAPL", "MSFT", "PLTR",
            "BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD", "XRP-USD",
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",
            "GC=F", "CL=F", "SI=F", "ES=F", "NQ=F",
            "7203.T", "ASML.AS", "0700.HK", "AZN.L", "^GSPC",
        ]
        orders = []
        prices = {}
        for i, sym in enumerate(symbols):
            px = 1.0850 if sym.endswith("=X") else (0.15 if sym == "DOGE-USD" else (100.0 + i))
            stop = round(px * 0.99, 4)
            target = round(px * 1.02, 4)
            qty = round(50.0 / max(px - stop, 0.0001), 4)
            prices[sym] = px
            orders.append({
                "symbol": sym,
                "side": "buy",
                "type": "market",
                "qty": str(qty),
                "order_class": "bracket",
                "stop_loss_stop_price": str(stop),
                "take_profit_limit_price": str(target),
            })
        portfolio = {"cash": "5000.00", "equity": "5000.00", "positions": [], "daytrade_count": 0}
        res = risk_check.check(orders, cfg, portfolio=portfolio, prices=prices)
        self.assertEqual(res["block"], 0, res)
        self.assertEqual(res["pass"], 25, res)
        self.assertTrue(all(r["verdict"] == "PASS" for r in res["results"]))


class EngineUnlimitedAndAllMarketsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.trader_dir = _setup_temp_trader_dir(self._tmp.name)
        import engine as eng_mod
        self.eng_mod = eng_mod
        self._orig_tr_dir = eng_mod.TRADER_DIR
        self._orig_mkt_dir = markets.TRADER_DIR
        self._orig_uni_file = markets.UNIVERSE_FILE
        eng_mod.TRADER_DIR = self.trader_dir
        markets.TRADER_DIR = self.trader_dir
        markets.UNIVERSE_FILE = os.path.join(self.trader_dir, "universe.txt")
        self.engine = eng_mod.TradingEngine()

    def tearDown(self):
        try:
            self.engine.pause()
        except Exception:
            pass
        self.eng_mod.TRADER_DIR = self._orig_tr_dir
        markets.TRADER_DIR = self._orig_mkt_dir
        markets.UNIVERSE_FILE = self._orig_uni_file
        self._tmp.cleanup()

    def test_ai_unlimited_executes_all_high_conviction_markets_and_closes_per_symbol(self):
        test_syms = ["TSLA", "BTC-USD", "EURUSD=X", "7203.T", "GC=F"]
        self.engine.watchlist = list(test_syms)
        quotes = {
            "TSLA": {"symbol": "TSLA", "price": 250.0, "prev_close": 240.0, "change_pct": 4.17, "volume": 1000000, "asset": markets.classify_asset("TSLA")},
            "BTC-USD": {"symbol": "BTC-USD", "price": 90000.0, "prev_close": 86000.0, "change_pct": 4.65, "volume": 500000, "asset": markets.classify_asset("BTC-USD")},
            "EURUSD=X": {"symbol": "EURUSD=X", "price": 1.0950, "prev_close": 1.0800, "change_pct": 1.39, "volume": 200000, "asset": markets.classify_asset("EURUSD=X")},
            "7203.T": {"symbol": "7203.T", "price": 2800.0, "prev_close": 2680.0, "change_pct": 4.48, "volume": 800000, "asset": markets.classify_asset("7203.T")},
            "GC=F": {"symbol": "GC=F", "price": 2700.0, "prev_close": 2620.0, "change_pct": 3.05, "volume": 300000, "asset": markets.classify_asset("GC=F")},
        }
        self.engine.quotes = quotes
        self.engine.scans = {
            "hits": [
                {"symbol": sym, "price": quotes[sym]["price"], "or_low": quotes[sym]["price"] * 0.985, "or_high": quotes[sym]["price"] * 0.995, "vol_x": 2.2, "status": "TRIGGERED"}
                for sym in test_syms
            ]
        }
        self.engine.news_feed = [
            {"id": "n1", "ticker": sym, "title": "%s surges on earnings and breakout volume" % sym, "tags": ["Earnings"], "important": True}
            for sym in test_syms
        ]

        ny_mock = {"ny_time": "10:15:00 ET", "session": "REGULAR MARKET HOURS", "is_open": True}
        with mock.patch.object(self.engine, "_fetch_quotes", return_value=quotes), \
             mock.patch.object(self.engine, "get_ny_clock_status", return_value=ny_mock):
            decisions = self.engine.ai_evaluate_market(ny_status=ny_mock)

        executed_syms = [d["symbol"] for d in decisions if d.get("action") == "AUTONOMOUS_BUY_EXECUTED"]
        self.assertEqual(len(executed_syms), 5)
        self.assertEqual(set(executed_syms), set(test_syms))
        self.assertEqual(len(self.engine.positions), 5)

        # Now verify hitting target or closing a SINGLE symbol preserves the other 4 positions
        ok = self.engine.close_position("BTC-USD", reason="TARGET_EXIT")
        self.assertTrue(ok.get("success"))
        remaining_syms = [p["symbol"] for p in self.engine.positions]
        self.assertNotIn("BTC-USD", remaining_syms)
        self.assertEqual(len(remaining_syms), 4)
        self.assertIn("TSLA", remaining_syms)
        self.assertIn("7203.T", remaining_syms)

    def test_ai_breakeven_and_single_target_exit_in_evaluation_cycle(self):
        self.engine.positions = [
            {
                "symbol": "BTC-USD",
                "asset_class": "crypto",
                "shares": 0.1,
                "entry_price": 80000.0,
                "current_price": 80000.0,
                "stop_price": 78000.0,
                "target_price": 82000.0,
            },
            {
                "symbol": "NVDA",
                "asset_class": "us_equity",
                "shares": 10.0,
                "entry_price": 120.0,
                "current_price": 120.0,
                "stop_price": 118.0,
                "target_price": 124.0,
            },
        ]
        # BTC-USD hits target; NVDA loses below stop -> only BTC & NVDA exit individually cleanly; let's test BTC exits while NVDA trails stop to breakeven
        quotes = {
            "BTC-USD": {"symbol": "BTC-USD", "price": 82500.0, "change_pct": 3.1, "asset": markets.classify_asset("BTC-USD")},
            "NVDA": {"symbol": "NVDA", "price": 122.5, "change_pct": 2.0, "asset": markets.classify_asset("NVDA")},
        }
        self.engine.watchlist = ["BTC-USD", "NVDA"]
        self.engine.quotes = quotes
        ny_mock = {"ny_time": "11:00:00 ET", "session": "REGULAR MARKET HOURS", "is_open": True}
        with mock.patch.object(self.engine, "_fetch_quotes", return_value=quotes), \
             mock.patch.object(self.engine, "get_ny_clock_status", return_value=ny_mock):
            decisions = self.engine.ai_evaluate_market(ny_status=ny_mock)

        actions = {d["symbol"]: d["action"] for d in decisions}
        self.assertEqual(actions.get("BTC-USD"), "TARGET_PROFIT_EXIT")
        self.assertEqual(actions.get("NVDA"), "TRAILING_STOP_BREAKEVEN")
        self.assertEqual([p["symbol"] for p in self.engine.positions], ["NVDA"])
        self.assertEqual(self.engine.positions[0]["stop_price"], 120.0)

    def test_zero_limits_persist_on_config_update(self):
        ok = self.engine.update_config({
            "max_trades_per_day": 0,
            "max_orders_per_day": 0,
            "max_daily_loss_usd": 0.0,
            "ai_max_concurrent_positions": 0,
            "ai_max_orders_per_cycle": 0,
            "ai_unlimited_orders": True,
        })
        self.assertTrue(ok)
        cfg = self.engine.get_config()
        self.assertEqual(cfg["max_trades_per_day"], 0)
        self.assertEqual(cfg["max_orders_per_day"], 0)
        self.assertEqual(cfg["max_daily_loss_usd"], 0.0)
        self.assertTrue(cfg["ai_unlimited_orders"])

    def test_http_api_smoke_endpoints(self):
        import server as srv_mod
        orig_srv_engine = srv_mod.engine
        srv_mod.engine = self.engine
        httpd = srv_mod.ThreadedHTTPServer(("127.0.0.1", 0), srv_mod.TraderHandler)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/api/status")
            r1 = conn.getresponse()
            self.assertEqual(r1.status, 200)
            st = json.loads(r1.read().decode("utf-8"))
            self.assertIn("global_sessions", st)
            self.assertIn("skills_telemetry", st)
            self.assertTrue(st["ai_agent"]["unlimited_orders"])

            conn.request("GET", "/api/markets/categories")
            r2 = conn.getresponse()
            self.assertEqual(r2.status, 200)
            cats = json.loads(r2.read().decode("utf-8"))
            self.assertTrue(cats["success"])
            self.assertIn("categories", cats)
            self.assertIn("crypto", cats["categories"])

            with mock.patch.object(self.eng_mod, "search_all_markets", return_value=[{"symbol": "7203.T", "name": "Toyota Motor Corp", "asset_class": "INTL_EQUITY", "badge": "T"}]):
                conn.request("GET", "/api/markets/search?q=Toyota&limit=5")
                r3 = conn.getresponse()
                self.assertEqual(r3.status, 200)
                srch = json.loads(r3.read().decode("utf-8"))
                self.assertEqual(srch["results"][0]["symbol"], "7203.T")

            body = json.dumps({"unlimited_orders": True, "max_concurrent_positions": 0, "max_orders_per_cycle": 0, "threshold": 60})
            conn.request("POST", "/api/ai/config", body=body, headers={"Content-Type": "application/json"})
            r4 = conn.getresponse()
            self.assertEqual(r4.status, 200)
            ai_cfg = json.loads(r4.read().decode("utf-8"))
            self.assertTrue(ai_cfg["unlimited_orders"])
            self.assertEqual(ai_cfg["max_concurrent_positions"], 0)

            with mock.patch.object(self.engine, "_fetch_quotes", return_value={"BTC-USD": {"symbol": "BTC-USD", "price": 90000.0, "change_pct": 2.0, "asset": markets.classify_asset("BTC-USD")}}):
                self.engine.quotes["BTC-USD"] = {"symbol": "BTC-USD", "price": 90000.0, "change_pct": 2.0, "asset": markets.classify_asset("BTC-USD")}
                conn.request("POST", "/api/broker/execute", body=json.dumps({"symbol": "BTC-USD"}), headers={"Content-Type": "application/json"})
                r5 = conn.getresponse()
                self.assertEqual(r5.status, 200)
                exec_res = json.loads(r5.read().decode("utf-8"))
                self.assertTrue(exec_res["success"], exec_res)

                conn.request("POST", "/api/broker/close", body=json.dumps({"symbol": "BTC-USD"}), headers={"Content-Type": "application/json"})
                r6 = conn.getresponse()
                self.assertEqual(r6.status, 200)
                close_res = json.loads(r6.read().decode("utf-8"))
                self.assertTrue(close_res["success"])

            with mock.patch.object(self.engine, "analyze_company", return_value={"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193", "asset_class": "US_EQUITY", "metrics": {"PE": "30x"}}):
                conn.request("GET", "/api/analyst/AAPL")
                r7 = conn.getresponse()
                self.assertEqual(r7.status, 200)
                an_res = json.loads(r7.read().decode("utf-8"))
                self.assertTrue(an_res["success"])
                self.assertEqual(an_res["symbol"], "AAPL")
                self.assertEqual(an_res["analysis"]["name"], "Apple Inc.")

            with mock.patch.object(self.engine, "_fetch_news", return_value=[{"id": "x1", "ticker": "BTC-USD", "title": "BTC breaks record", "tags": []}]):
                conn.request("POST", "/api/news/fetch", body=json.dumps({"symbols": ["BTC-USD"]}), headers={"Content-Type": "application/json"})
                r8 = conn.getresponse()
                self.assertEqual(r8.status, 200)
                nw_res = json.loads(r8.read().decode("utf-8"))
                self.assertTrue(nw_res["success"])

            with mock.patch.object(self.engine, "scan_universe_batch", return_value={"success": True, "scanned": 10, "universe_scanned": 10, "universe_total": 10, "hits": [{"symbol": "NVDA"}]}) as m_scan:
                conn.request("POST", "/api/scanner/scan-universe", body=json.dumps({"batch_size": 10}), headers={"Content-Type": "application/json"})
                r9 = conn.getresponse()
                self.assertEqual(r9.status, 200)
                sc_res = json.loads(r9.read().decode("utf-8"))
                self.assertTrue(sc_res["success"])
                m_scan.assert_called_once_with(count=10)

            with mock.patch.object(self.engine, "run_timemachine", return_value={"symbol": "BTC-USD", "mc": {"p_target": 0.4, "p_stop": 0.3, "p_neither": 0.3, "p_green": 0.6}}):
                conn.request("POST", "/api/timemachine/run", body=json.dumps({"symbol": "BTC-USD"}), headers={"Content-Type": "application/json"})
                r10 = conn.getresponse()
                self.assertEqual(r10.status, 200)
                tm_res = json.loads(r10.read().decode("utf-8"))
                self.assertTrue(tm_res["success"])
                self.assertEqual(tm_res["timemachine"]["symbol"], "BTC-USD")
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            srv_mod.engine = orig_srv_engine


if __name__ == "__main__":
    unittest.main()
