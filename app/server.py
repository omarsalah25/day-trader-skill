#!/usr/bin/env python3
"""HTTP API Server & Static Asset Server for the 24/7 Day Trader Web App.
Runs on standard Python library only.
"""

import argparse
from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import os
from socketserver import ThreadingMixIn
import sys
import urllib.parse

from engine import TradingEngine
from markets import MARKET_CATEGORIES, classify_asset, get_global_market_sessions, normalize_symbol

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, "web")

engine = TradingEngine()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class TraderHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def address_string(self):
        # Avoid reverse DNS resolution lag on macOS
        return self.client_address[0]


    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        elif path.startswith("/api/"):
            query = urllib.parse.parse_qs(url.query)
            self.handle_api_get(path, query)
        else:
            if path in ("", "/"):
                self.path = "/index.html"
            super().do_GET()

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            data = {}

        if path.startswith("/api/"):
            self.handle_api_post(path, data)
        else:
            self.send_error(404, "Not Found")

    def handle_api_get(self, path, query=None):
        query = query or {}
        if path == "/api/status" or path == "/api/state":
            state = engine.get_state()
            self._send_json(200, state)
        elif path == "/api/logs":
            self._send_json(200, {"logs": engine.logs})
        elif path == "/api/watchlist":
            self._send_json(200, {"watchlist": engine.watchlist, "quotes": engine.quotes})
        elif path == "/api/markets/search":
            q = (query.get("q") or [""])[0]
            limit = int((query.get("limit") or ["25"])[0])
            results = engine.search_markets(q, limit=limit)
            self._send_json(200, {"query": q, "results": results})
        elif path == "/api/markets/categories":
            self._send_json(200, {
                "success": True,
                "categories": MARKET_CATEGORIES,
                "universe_total": len(engine.us_universe),
                "sessions": get_global_market_sessions(),
            })
        elif path == "/api/analyst" or path.startswith("/api/analyst/"):
            raw_sym = path.split("/api/analyst/", 1)[1] if path.startswith("/api/analyst/") else (query.get("symbol") or ["TSLA"])[0]
            sym = normalize_symbol(urllib.parse.unquote(raw_sym))
            try:
                data = engine.analyze_company(sym)
                self._send_json(200, {
                    "success": True,
                    "symbol": data.get("ticker", sym),
                    "asset": classify_asset(sym),
                    "quote": engine.quotes.get(sym, {}),
                    "analysis": data,
                })
            except Exception as e:
                self._send_json(200, {"success": False, "error": str(e), "symbol": sym})
        elif path == "/api/alerts":
            self._send_json(200, {"alerts": engine.alerts, "triggered": engine.triggered_alerts})
        elif path == "/api/news":
            self._send_json(200, {"news": engine.news_feed})
        elif path == "/api/pelosi":
            self._send_json(200, {"pelosi": engine.pelosi_filings})
        elif path == "/api/plan":
            self._send_json(200, {"plan": engine.active_plan, "timemachine": engine.timemachine_stats})
        elif path == "/api/orders":
            self._send_json(200, {"orders": engine.orders, "risk": engine.risk_verdict})
        elif path == "/api/config":
            self._send_json(200, {"config": engine.get_config()})
        elif path == "/api/broker/positions":
            self._send_json(200, {"positions": engine.positions})
        elif path == "/api/broker/transactions":
            self._send_json(200, {"transactions": engine.transactions})
        elif path == "/api/broker/account":
            self._send_json(200, {"account": engine.broker_account})
        elif path == "/api/ai/status":
            self._send_json(200, {
                "enabled": engine.ai_enabled,
                "unlimited_orders": engine.ai_unlimited_orders,
                "status": engine.ai_status,
                "confidence_threshold": engine.ai_confidence_threshold,
                "max_concurrent_positions": engine.ai_max_concurrent_positions,
                "max_orders_per_cycle": engine.ai_max_orders_per_cycle,
                "actions_today": engine.ai_actions_count,
                "orders_executed": engine.ai_orders_executed,
                "auto_breakeven": engine.ai_auto_breakeven_stop,
                "auto_flatten": engine.ai_auto_flatten_eod,
                "last_action": engine.ai_last_action,
                "decisions": engine.ai_decisions[:30],
            })
        else:
            self.send_error(404, "API endpoint not found")

    def handle_api_post(self, path, data):
        if path == "/api/engine/toggle":
            if engine.running:
                engine.pause()
            else:
                engine.resume()
            self._send_json(200, {"running": engine.running})

        elif path == "/api/engine/mode":
            mode = data.get("mode", "simulation")
            engine.set_mode(mode)
            self._send_json(200, {"mode": engine.mode})

        elif path == "/api/engine/interval":
            interval = data.get("interval", 30)
            engine.set_interval(interval)
            self._send_json(200, {"interval": engine.interval})

        elif path == "/api/engine/run-now":
            engine.run_cycle_now()
            self._send_json(200, {"message": "Cycle triggered immediately"})

        elif path == "/api/engine/replay-demo":
            engine.run_demo_reel()
            self._send_json(200, {"message": "Full 9-step demo reel started"})

        elif path == "/api/watchlist/add":
            sym = data.get("symbol", "")
            success = engine.add_symbol(sym)
            self._send_json(200, {"success": success, "watchlist": engine.watchlist})

        elif path == "/api/watchlist/remove":
            sym = data.get("symbol", "")
            success = engine.remove_symbol(sym)
            self._send_json(200, {"success": success, "watchlist": engine.watchlist})

        elif path == "/api/watchlist/preset":
            cat = data.get("category", "forex")
            syms = engine.load_watchlist_preset(cat)
            self._send_json(200, {"success": True, "category": cat, "watchlist": syms})

        elif path == "/api/alerts/add":
            alert = engine.add_alert(data)
            self._send_json(200, {"success": True, "alert": alert})

        elif path == "/api/alerts/dismiss":
            alert_id = data.get("id", "")
            engine.dismiss_alert(alert_id)
            self._send_json(200, {"success": True})

        elif path == "/api/config":
            ok = engine.update_config(data)
            self._send_json(200, {"success": ok, "config": engine.get_config()})

        elif path == "/api/strategy":
            preset = data.get("preset", "fast_1m")
            engine.set_strategy_preset(preset)
            self._send_json(200, {"success": True, "config": engine.get_config()})

        elif path == "/api/broker/execute":
            if data.get("symbol") and not data.get("order"):
                preset = data.get("preset") or engine.config.get("strategy_preset", "all_markets_24_7")
                engine.generate_strategy_order(preset, data["symbol"])
            res = engine.execute_order(data.get("order"))
            self._send_json(200, res)

        elif path == "/api/broker/close":
            sym = data.get("symbol", "")
            res = engine.close_position(sym, reason=data.get("reason", "MANUAL_CLOSE"))
            self._send_json(200, res)

        elif path == "/api/scanner/scan-universe":
            count = int(data.get("count") or data.get("batch_size") or 500)
            res = engine.scan_universe_batch(count=count)
            self._send_json(200, res)

        elif path == "/api/scanner/refresh-universe":
            started = engine.refresh_universe_async()
            self._send_json(200, {
                "success": True,
                "started": started,
                "universe_total": len(engine.us_universe),
            })

        elif path == "/api/news/fetch":
            tickers = data.get("tickers") or data.get("symbols")
            if isinstance(tickers, str):
                tickers = [t.strip().upper() for t in tickers.split(",") if t.strip()]
            engine._fetch_news(custom_tickers=tickers)
            self._send_json(200, {"success": True, "news": engine.news_feed})

        elif path == "/api/timemachine/run":
            sym = data.get("symbol", "TSLA")
            replays = int(data.get("replays") or 10000)
            try:
                doc = engine.run_timemachine(sym, replays=replays)
                self._send_json(200, {"success": True, "timemachine": doc})
            except Exception as e:
                self._send_json(200, {"success": False, "error": str(e)})

        elif path == "/api/broker/sync":
            engine.sync_broker()
            self._send_json(200, {
                "success": True,
                "positions": engine.positions,
                "transactions": engine.transactions,
                "account": engine.broker_account
            })

        elif path == "/api/broker/order/cancel":
            order_id = data.get("order_id", "")
            res = engine.cancel_order(order_id)
            self._send_json(200, res)

        elif path == "/api/strategy/generate":
            preset = data.get("preset", "fast_1m")
            sym = data.get("symbol", "TSLA")
            orders_doc = engine.generate_strategy_order(preset, sym)
            self._send_json(200, {"success": True, "orders": orders_doc})

        elif path == "/api/broker/flatten":
            res = engine.flatten_positions()
            self._send_json(200, res)

        elif path == "/api/logs/clear":
            with engine.lock:
                engine.logs.clear()
            self._send_json(200, {"success": True})

        elif path == "/api/ai/toggle":
            enabled = data.get("enabled")
            if enabled is None:
                enabled = not engine.ai_enabled
            engine.set_ai_mode(enabled)
            self._send_json(200, {"success": True, "enabled": engine.ai_enabled, "status": engine.ai_status})

        elif path == "/api/ai/config":
            updates = {}
            thresh_val = data.get("confidence_threshold") if "confidence_threshold" in data else data.get("threshold")
            if thresh_val is not None:
                updates["ai_confidence_threshold"] = int(thresh_val)
            if "auto_breakeven" in data:
                updates["ai_auto_breakeven"] = bool(data["auto_breakeven"])
            if "auto_flatten" in data:
                updates["ai_auto_flatten"] = bool(data["auto_flatten"])
            if "unlimited_orders" in data:
                updates["ai_unlimited_orders"] = bool(data["unlimited_orders"])
            if "max_concurrent_positions" in data:
                updates["ai_max_concurrent_positions"] = int(data["max_concurrent_positions"])
            if "max_orders_per_cycle" in data:
                updates["ai_max_orders_per_cycle"] = int(data["max_orders_per_cycle"])
            engine.update_config(updates)
            self._send_json(200, {
                "success": True,
                "unlimited_orders": engine.ai_unlimited_orders,
                "confidence_threshold": engine.ai_confidence_threshold,
                "auto_breakeven": engine.ai_auto_breakeven_stop,
                "auto_flatten": engine.ai_auto_flatten_eod,
                "max_concurrent_positions": engine.ai_max_concurrent_positions,
                "max_orders_per_cycle": engine.ai_max_orders_per_cycle,
            })

        elif path == "/api/ai/evaluate-now":
            decisions = engine.ai_evaluate_market(engine.get_ny_clock_status())
            self._send_json(200, {
                "success": True,
                "status": engine.ai_status,
                "actions_today": engine.ai_actions_count,
                "decisions": decisions or engine.ai_decisions[:10]
            })

        else:
            self.send_error(404, "API endpoint not found")

    def _send_json(self, status_code, data):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        # Mute standard noisy HTTP access logs so terminal logs stay clean
        pass


def run_server(port=8080):
    server_address = ("0.0.0.0", port)
    httpd = ThreadedHTTPServer(server_address, TraderHandler)
    print(f"==================================================")
    print(f"  Day Trader 24/7 Engine & Dashboard Active")
    print(f"  Local URL:   http://localhost:{port}")
    print(f"  Network URL: http://0.0.0.0:{port}")
    print(f"==================================================")

    # Start the continuous 24/7 engine in background thread
    engine.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down 24/7 server...")
        engine.pause()
        httpd.server_close()


if __name__ == "__main__":
    default_port = int(os.environ.get("PORT", "8080"))
    parser = argparse.ArgumentParser(description="24/7 Day Trader Web Application")
    parser.add_argument("--port", type=int, default=default_port, help="Port to serve on (default: 8080 or $PORT)")
    args = parser.parse_args()
    run_server(args.port)
