#!/usr/bin/env python3
"""Global Multi-Market Registry, Asset Classifier, Market Sessions & Universal Search.
Supports US Equities (~5,900+ Nasdaq/NYSE/AMEX companies), Global International Equities,
24/7 Crypto, 24/5 Forex, Commodities & Futures, Global Indices, ETFs & Fixed Income.
Standard library only.
"""

import datetime
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADER_DIR = os.path.join(ROOT, "trader")
UNIVERSE_FILE = os.path.join(TRADER_DIR, "universe.txt")

UA = "Mozilla/5.0 (compatible; day-trader-skill/2.0; +https://github.com/Jakeschincariol/day-trader-skill)"
YAHOO_HOSTS = ("https://query2.finance.yahoo.com", "https://query1.finance.yahoo.com")

EXCHANGE_SUFFIXES = {
    "T": ("Tokyo (JPX)", "Asia-Pacific"),
    "L": ("London (LSE)", "Europe"),
    "HK": ("Hong Kong (HKEX)", "Asia-Pacific"),
    "NS": ("India (NSE)", "Asia-Pacific"),
    "BO": ("India (BSE)", "Asia-Pacific"),
    "AS": ("Amsterdam (Euronext)", "Europe"),
    "DE": ("Frankfurt (XETRA)", "Europe"),
    "PA": ("Paris (Euronext)", "Europe"),
    "SW": ("Zurich (SIX)", "Europe"),
    "CO": ("Copenhagen", "Europe"),
    "ST": ("Stockholm", "Europe"),
    "OL": ("Oslo", "Europe"),
    "HE": ("Helsinki", "Europe"),
    "MI": ("Milan", "Europe"),
    "MC": ("Madrid", "Europe"),
    "BR": ("Brussels", "Europe"),
    "TO": ("Toronto (TSX)", "Americas"),
    "V": ("TSX Venture", "Americas"),
    "AX": ("Australia (ASX)", "Asia-Pacific"),
    "NZ": ("New Zealand", "Asia-Pacific"),
    "KS": ("Korea (KRX)", "Asia-Pacific"),
    "KQ": ("Korea (KOSDAQ)", "Asia-Pacific"),
    "TW": ("Taiwan (TWSE)", "Asia-Pacific"),
    "TWO": ("Taiwan (TPEX)", "Asia-Pacific"),
    "SS": ("Shanghai (SSE)", "Asia-Pacific"),
    "SZ": ("Shenzhen (SZSE)", "Asia-Pacific"),
    "SI": ("Singapore (SGX)", "Asia-Pacific"),
    "SA": ("Sao Paulo (B3)", "Americas"),
    "MX": ("Mexico (BMV)", "Americas"),
    "SR": ("Saudi (Tadawul)", "Middle East"),
    "QA": ("Qatar", "Middle East"),
    "TA": ("Tel Aviv", "Middle East"),
    "JO": ("Johannesburg", "Africa"),
    "JK": ("Jakarta", "Asia-Pacific"),
    "BK": ("Bangkok", "Asia-Pacific"),
    "KL": ("Kuala Lumpur", "Asia-Pacific"),
    "CN": ("CSE Canada", "Americas"),
    "NE": ("NEO Canada", "Americas"),
    "F": ("Frankfurt", "Europe"),
    "BE": ("Berlin", "Europe"),
    "DU": ("Dusseldorf", "Europe"),
    "HM": ("Hamburg", "Europe"),
    "MU": ("Munich", "Europe"),
    "SG": ("Stuttgart", "Europe"),
    "VI": ("Vienna", "Europe"),
    "LS": ("Lisbon", "Europe"),
    "WA": ("Warsaw", "Europe"),
    "PR": ("Prague", "Europe"),
    "BD": ("Budapest", "Europe"),
    "AT": ("Athens", "Europe"),
    "IS": ("Istanbul", "Europe"),
    "IC": ("Iceland", "Europe"),
    "BA": ("Buenos Aires", "Americas"),
    "SN": ("Santiago", "Americas"),
    "CR": ("Caracas", "Americas"),
    "AE": ("UAE", "Middle East"),
    "KW": ("Kuwait", "Middle East"),
}

MARKET_CATEGORIES = {
    "us_equities": {
        "label": "US Equities & Tech Leaders",
        "symbols": [
            "TSLA", "NVDA", "AAPL", "AMD", "MSFT", "AMZN", "META", "GOOGL",
            "PLTR", "NFLX", "JPM", "BRK.B", "AVGO", "COIN", "SOFI", "MSTR",
        ],
    },
    "crypto": {
        "label": "Crypto (24/7)",
        "symbols": [
            "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
            "DOGE-USD", "ADA-USD", "AVAX-USD", "LINK-USD", "DOT-USD", "LTC-USD",
        ],
    },
    "forex": {
        "label": "Forex & Currencies (24/5)",
        "symbols": [
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",
            "USDCHF=X", "NZDUSD=X", "EURJPY=X", "GBPJPY=X", "UUP", "FXE", "FXY",
        ],
    },
    "commodities": {
        "label": "Commodities & Futures (24/5)",
        "symbols": [
            "GC=F", "SI=F", "HG=F", "CL=F", "BZ=F", "NG=F",
            "ZC=F", "ES=F", "NQ=F", "YM=F", "GLD", "SLV", "USO",
        ],
    },
    "global_equities": {
        "label": "Global Equities (EU, Asia, UK, India, Canada)",
        "symbols": [
            "7203.T", "6758.T", "0700.HK", "9988.HK", "ASML.AS", "SAP.DE",
            "MC.PA", "AZN.L", "SHEL.L", "NESN.SW", "RELIANCE.NS", "RY.TO",
            "BHP.AX", "TSM",
        ],
    },
    "indices_bonds": {
        "label": "Indices, ETFs & Bonds",
        "symbols": [
            "^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX", "^FTSE", "^GDAXI", "^N225", "^HSI",
            "SPY", "QQQ", "IWM", "DIA", "SMH", "TLT", "HYG", "LQD",
        ],
    },
}

BUILTIN_CATALOG = {
    # US Equities & ETFs
    "TSLA": ("Tesla, Inc.", "US_EQUITY", "US NYSE/NASDAQ"),
    "NVDA": ("NVIDIA Corporation", "US_EQUITY", "US NYSE/NASDAQ"),
    "AAPL": ("Apple Inc.", "US_EQUITY", "US NYSE/NASDAQ"),
    "AMD": ("Advanced Micro Devices, Inc.", "US_EQUITY", "US NYSE/NASDAQ"),
    "MSFT": ("Microsoft Corporation", "US_EQUITY", "US NYSE/NASDAQ"),
    "AMZN": ("Amazon.com, Inc.", "US_EQUITY", "US NYSE/NASDAQ"),
    "META": ("Meta Platforms, Inc.", "US_EQUITY", "US NYSE/NASDAQ"),
    "GOOGL": ("Alphabet Inc.", "US_EQUITY", "US NYSE/NASDAQ"),
    "PLTR": ("Palantir Technologies Inc.", "US_EQUITY", "US NYSE/NASDAQ"),
    "NFLX": ("Netflix, Inc.", "US_EQUITY", "US NYSE/NASDAQ"),
    "JPM": ("JPMorgan Chase & Co.", "US_EQUITY", "US NYSE/NASDAQ"),
    "BRK.B": ("Berkshire Hathaway Inc.", "US_EQUITY", "US NYSE/NASDAQ"),
    "AVGO": ("Broadcom Inc.", "US_EQUITY", "US NYSE/NASDAQ"),
    "COIN": ("Coinbase Global, Inc.", "US_EQUITY", "US NYSE/NASDAQ"),
    "SOFI": ("SoFi Technologies, Inc.", "US_EQUITY", "US NYSE/NASDAQ"),
    "MSTR": ("Strategy (MicroStrategy)", "US_EQUITY", "US NYSE/NASDAQ"),
    "TSM": ("Taiwan Semiconductor ADR", "US_EQUITY", "US NYSE/NASDAQ"),
    "SPY": ("SPDR S&P 500 ETF Trust", "ETF", "US ETF"),
    "QQQ": ("Invesco QQQ Trust (Nasdaq-100)", "ETF", "US ETF"),
    "IWM": ("iShares Russell 2000 ETF", "ETF", "US ETF"),
    "DIA": ("SPDR Dow Jones Industrial Avg ETF", "ETF", "US ETF"),
    "SMH": ("VanEck Semiconductor ETF", "ETF", "US ETF"),
    "TLT": ("iShares 20+ Year Treasury Bond ETF", "ETF", "US Fixed Income"),
    "HYG": ("iShares iBoxx High Yield Corp Bond ETF", "ETF", "US Fixed Income"),
    "LQD": ("iShares iBoxx Investment Grade Corp Bond ETF", "ETF", "US Fixed Income"),
    "GLD": ("SPDR Gold Shares", "ETF", "Commodity ETF"),
    "SLV": ("iShares Silver Trust", "ETF", "Commodity ETF"),
    "USO": ("United States Oil Fund", "ETF", "Commodity ETF"),
    "UUP": ("Invesco DB US Dollar Index Bullish", "ETF", "Currency ETF"),
    "FXE": ("Invesco CurrencyShares Euro Trust", "ETF", "Currency ETF"),
    "FXY": ("Invesco CurrencyShares Japanese Yen", "ETF", "Currency ETF"),
    # Crypto
    "BTC-USD": ("Bitcoin USD", "CRYPTO", "Crypto 24/7"),
    "ETH-USD": ("Ethereum USD", "CRYPTO", "Crypto 24/7"),
    "SOL-USD": ("Solana USD", "CRYPTO", "Crypto 24/7"),
    "BNB-USD": ("BNB USD", "CRYPTO", "Crypto 24/7"),
    "XRP-USD": ("XRP USD", "CRYPTO", "Crypto 24/7"),
    "DOGE-USD": ("Dogecoin USD", "CRYPTO", "Crypto 24/7"),
    "ADA-USD": ("Cardano USD", "CRYPTO", "Crypto 24/7"),
    "AVAX-USD": ("Avalanche USD", "CRYPTO", "Crypto 24/7"),
    "LINK-USD": ("Chainlink USD", "CRYPTO", "Crypto 24/7"),
    "DOT-USD": ("Polkadot USD", "CRYPTO", "Crypto 24/7"),
    "LTC-USD": ("Litecoin USD", "CRYPTO", "Crypto 24/7"),
    # Forex
    "EURUSD=X": ("EUR / USD", "FOREX", "Forex 24/5"),
    "GBPUSD=X": ("GBP / USD", "FOREX", "Forex 24/5"),
    "USDJPY=X": ("USD / JPY", "FOREX", "Forex 24/5"),
    "AUDUSD=X": ("AUD / USD", "FOREX", "Forex 24/5"),
    "USDCAD=X": ("USD / CAD", "FOREX", "Forex 24/5"),
    "USDCHF=X": ("USD / CHF", "FOREX", "Forex 24/5"),
    "NZDUSD=X": ("NZD / USD", "FOREX", "Forex 24/5"),
    "EURJPY=X": ("EUR / JPY", "FOREX", "Forex 24/5"),
    "GBPJPY=X": ("GBP / JPY", "FOREX", "Forex 24/5"),
    # Commodities & Futures
    "GC=F": ("Gold Futures (COMEX)", "COMMODITY_FUTURE", "Commodities 24/5"),
    "SI=F": ("Silver Futures (COMEX)", "COMMODITY_FUTURE", "Commodities 24/5"),
    "HG=F": ("Copper Futures (COMEX)", "COMMODITY_FUTURE", "Commodities 24/5"),
    "CL=F": ("Crude Oil WTI Futures (NYMEX)", "COMMODITY_FUTURE", "Commodities 24/5"),
    "BZ=F": ("Brent Crude Oil Futures", "COMMODITY_FUTURE", "Commodities 24/5"),
    "NG=F": ("Natural Gas Futures", "COMMODITY_FUTURE", "Commodities 24/5"),
    "ZC=F": ("Corn Futures (CBOT)", "COMMODITY_FUTURE", "Commodities 24/5"),
    "ES=F": ("E-Mini S&P 500 Futures", "COMMODITY_FUTURE", "Index Futures 24/5"),
    "NQ=F": ("E-Mini Nasdaq-100 Futures", "COMMODITY_FUTURE", "Index Futures 24/5"),
    "YM=F": ("E-Mini Dow Futures", "COMMODITY_FUTURE", "Index Futures 24/5"),
    # Global Equities
    "7203.T": ("Toyota Motor Corporation", "INTL_EQUITY", "Tokyo (JPX)"),
    "6758.T": ("Sony Group Corporation", "INTL_EQUITY", "Tokyo (JPX)"),
    "0700.HK": ("Tencent Holdings Limited", "INTL_EQUITY", "Hong Kong (HKEX)"),
    "9988.HK": ("Alibaba Group Holding", "INTL_EQUITY", "Hong Kong (HKEX)"),
    "ASML.AS": ("ASML Holding N.V.", "INTL_EQUITY", "Amsterdam (Euronext)"),
    "SAP.DE": ("SAP SE", "INTL_EQUITY", "Frankfurt (XETRA)"),
    "MC.PA": ("LVMH Moet Hennessy", "INTL_EQUITY", "Paris (Euronext)"),
    "AZN.L": ("AstraZeneca PLC", "INTL_EQUITY", "London (LSE)"),
    "SHEL.L": ("Shell plc", "INTL_EQUITY", "London (LSE)"),
    "NESN.SW": ("Nestle S.A.", "INTL_EQUITY", "Zurich (SIX)"),
    "RELIANCE.NS": ("Reliance Industries Limited", "INTL_EQUITY", "India (NSE)"),
    "RY.TO": ("Royal Bank of Canada", "INTL_EQUITY", "Toronto (TSX)"),
    "BHP.AX": ("BHP Group Limited", "INTL_EQUITY", "Australia (ASX)"),
    # Indices
    "^GSPC": ("S&P 500 Index", "INDEX", "US Index"),
    "^IXIC": ("NASDAQ Composite Index", "INDEX", "US Index"),
    "^DJI": ("Dow Jones Industrial Average", "INDEX", "US Index"),
    "^RUT": ("Russell 2000 Index", "INDEX", "US Index"),
    "^VIX": ("CBOE Volatility Index (VIX)", "INDEX", "Volatility Index"),
    "^FTSE": ("FTSE 100 Index", "INDEX", "UK Index"),
    "^GDAXI": ("DAX Performance Index", "INDEX", "Germany Index"),
    "^N225": ("Nikkei 225 Index", "INDEX", "Japan Index"),
    "^HSI": ("Hang Seng Index", "INDEX", "Hong Kong Index"),
}

# Curated multi-market default watchlist covering every major asset class
WATCHLIST_ALL_MARKETS = [
    # US Mega-Caps & Momentum
    "TSLA", "NVDA", "AAPL", "AMD", "MSFT", "AMZN", "META", "GOOGL", "PLTR", "BRK.B",
    # ETFs & Bonds
    "SPY", "QQQ", "IWM", "SMH", "TLT",
    # Crypto (24/7)
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD",
    # Forex (24/5)
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "UUP", "FXE",
    # Commodities & Futures (24/5)
    "GC=F", "SI=F", "CL=F", "NG=F", "ES=F", "NQ=F", "GLD",
    # Global Equities
    "7203.T", "0700.HK", "ASML.AS", "SAP.DE", "AZN.L", "RELIANCE.NS", "RY.TO", "TSM",
    # Indices
    "^GSPC", "^IXIC", "^VIX", "^N225", "^FTSE",
]

ETF_SYMBOLS = {
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "SMH", "XLK", "XLF", "XLE",
    "XLV", "XLI", "ARKK", "TQQQ", "SQQQ", "TLT", "IEF", "SHY", "HYG", "LQD",
    "AGG", "GLD", "SLV", "USO", "UNG", "UUP", "FXE", "FXY",
}

OCC_RE = re.compile(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")
SPOT_FX_PAIRS = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY"}


def normalize_symbol(raw):
    """Normalizes user-entered symbol across all markets."""
    s = str(raw or "").strip().upper()
    if not s:
        return ""
    if s in SPOT_FX_PAIRS:
        return s + "=X"
    if "/" in s:
        left, right = s.split("/", 1)
        if left + right in SPOT_FX_PAIRS or (len(left) == 3 and len(right) == 3 and right in ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD")):
            if left in ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX", "LINK", "DOT", "LTC"):
                return left + "-" + right
            return left + right + "=X"
        return left + "-" + right
    return s


def to_yahoo(sym):
    """Converts internal symbol to Yahoo Finance symbol format.
    Preserves exchange suffixes (7203.T, ASML.AS, AZN.L) and converts US share classes (BRK.B -> BRK-B).
    """
    s = normalize_symbol(sym)
    if "." in s and not s.startswith("^"):
        base, suf = s.rsplit(".", 1)
        if suf in EXCHANGE_SUFFIXES or any(ch.isdigit() for ch in base):
            return s
        return base + "-" + suf
    return s


def classify_asset(sym):
    """Returns market classification, region, Alpaca symbol compatibility, and formatting metadata."""
    s = str(sym or "").strip().upper()
    if OCC_RE.match(s.replace(" ", "")):
        return {
            "symbol": s,
            "asset_class": "OPTION",
            "badge": "OPT",
            "region": "US Options",
            "alpaca_symbol": None,
            "supports_24_7": False,
            "supports_24_5": False,
            "supports_sec": False,
        }
    if s.startswith("^"):
        return {
            "symbol": s,
            "asset_class": "INDEX",
            "badge": "IDX",
            "region": BUILTIN_CATALOG.get(s, ("", "", "Global Index"))[2],
            "alpaca_symbol": None,
            "supports_24_7": False,
            "supports_24_5": True,
            "supports_sec": False,
        }
    if s.endswith("=X") or s in SPOT_FX_PAIRS:
        return {
            "symbol": s,
            "asset_class": "FOREX",
            "badge": "FX",
            "region": "Forex 24/5",
            "alpaca_symbol": None,
            "supports_24_7": False,
            "supports_24_5": True,
            "supports_sec": False,
        }
    if s.endswith("=F"):
        return {
            "symbol": s,
            "asset_class": "COMMODITY_FUTURE",
            "badge": "FUT",
            "region": "Futures & Commodities 24/5",
            "alpaca_symbol": None,
            "supports_24_7": False,
            "supports_24_5": True,
            "supports_sec": False,
        }
    if s.endswith(("-USD", "-USDT", "-BTC", "-ETH", "/USD", "/USDT")):
        base, quote = re.split(r"[-/]", s, maxsplit=1)
        return {
            "symbol": s,
            "asset_class": "CRYPTO",
            "badge": "CRYPTO",
            "region": "Crypto 24/7",
            "alpaca_symbol": "%s/%s" % (base, quote) if quote == "USD" else None,
            "supports_24_7": True,
            "supports_24_5": True,
            "supports_sec": False,
        }
    if "." in s:
        base, suf = s.rsplit(".", 1)
        if suf in EXCHANGE_SUFFIXES or any(ch.isdigit() for ch in base):
            ex_name, area = EXCHANGE_SUFFIXES.get(suf, ("Global Exchange", "International"))
            return {
                "symbol": s,
                "asset_class": "INTL_EQUITY",
                "badge": suf,
                "region": ex_name,
                "area": area,
                "alpaca_symbol": None,
                "supports_24_7": False,
                "supports_24_5": False,
                "supports_sec": False,
            }
    if s in ETF_SYMBOLS:
        return {
            "symbol": s,
            "asset_class": "ETF",
            "badge": "ETF",
            "region": BUILTIN_CATALOG.get(s, ("", "", "US ETF"))[2],
            "alpaca_symbol": s,
            "supports_24_7": False,
            "supports_24_5": False,
            "supports_sec": False,
        }
    return {
        "symbol": s,
        "asset_class": "US_EQUITY",
        "badge": "US",
        "region": "US NYSE/NASDAQ",
        "alpaca_symbol": s,
        "supports_24_7": False,
        "supports_24_5": False,
        "supports_sec": True,
    }


def price_decimals(sym, price=None):
    s = str(sym or "").upper()
    if "=X" in s or s in SPOT_FX_PAIRS:
        return 2 if "JPY" in s else 4
    if price is not None:
        try:
            p = abs(float(price))
            if p > 0 and p < 0.01:
                return 6
            if p > 0 and p < 2.0:
                return 4
        except (TypeError, ValueError):
            pass
    return 2


def _eastern_offset(utc):
    y = utc.year
    d1 = datetime.date(y, 3, 1)
    d1 += datetime.timedelta(days=(6 - d1.weekday()) % 7 + 7)
    start = datetime.datetime.combine(d1, datetime.time(7, 0))
    d2 = datetime.date(y, 11, 1)
    d2 += datetime.timedelta(days=(6 - d2.weekday()) % 7)
    end = datetime.datetime.combine(d2, datetime.time(6, 0))
    naive = utc.replace(tzinfo=None)
    return -4 if start <= naive < end else -5


def to_eastern(utc=None):
    if utc is None:
        utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return utc.replace(tzinfo=None) + datetime.timedelta(hours=_eastern_offset(utc))


def get_global_market_sessions(now_utc=None):
    """Returns real-time open/closed status for global markets."""
    utc = (now_utc or datetime.datetime.now(datetime.timezone.utc)).replace(tzinfo=None)
    et = to_eastern(utc)
    wd = et.weekday()  # 0=Mon .. 6=Sun
    et_mins = et.hour * 60 + et.minute

    # Forex & Futures: Sun 17:00 ET -> Fri 17:00 ET
    if wd < 4:
        fx_open = True
    elif wd == 4:
        fx_open = et_mins < 17 * 60
    elif wd == 6:
        fx_open = et_mins >= 17 * 60
    else:
        fx_open = False

    # US Equities
    if wd < 5:
        if 9 * 60 + 30 <= et_mins < 16 * 60:
            us_session = "OPEN"
            us_open = True
        elif 4 * 60 <= et_mins < 9 * 60 + 30:
            us_session = "PRE-MARKET"
            us_open = False
        elif 16 * 60 <= et_mins < 20 * 60:
            us_session = "AFTER HOURS"
            us_open = False
        else:
            us_session = "CLOSED"
            us_open = False
    else:
        us_session = "WEEKEND"
        us_open = False

    # Europe / London (approx 08:00 - 16:30 UTC Mon-Fri)
    utc_mins = utc.hour * 60 + utc.minute
    utc_wd = utc.weekday()
    eu_open = utc_wd < 5 and (8 * 60 <= utc_mins < 16 * 60 + 30)

    # Asia (Tokyo / HK / India approx 00:00 - 10:00 UTC Mon-Fri)
    asia_open = utc_wd < 5 and (0 <= utc_mins < 10 * 60)

    return {
        "crypto": {"name": "Crypto", "open": True, "label": "24/7 OPEN"},
        "forex": {"name": "Forex", "open": fx_open, "label": "24/5 OPEN" if fx_open else "WEEKEND CLOSED"},
        "futures": {"name": "Futures & Commodities", "open": fx_open, "label": "24/5 OPEN" if fx_open else "WEEKEND CLOSED"},
        "us": {"name": "US Equities", "open": us_open, "label": us_session},
        "europe": {"name": "Europe / UK", "open": eu_open, "label": "OPEN" if eu_open else "CLOSED"},
        "asia": {"name": "Asia-Pacific", "open": asia_open, "label": "OPEN" if asia_open else "CLOSED"},
    }


def is_symbol_market_open(sym, now_utc=None, mode="live"):
    """True if the symbol's market is currently trading (or in simulation mode)."""
    if mode == "simulation":
        return True
    info = classify_asset(sym)
    ac = info["asset_class"]
    sessions = get_global_market_sessions(now_utc)
    if ac == "CRYPTO":
        return True
    if ac in ("FOREX", "COMMODITY_FUTURE"):
        return sessions["forex"]["open"]
    if ac == "INDEX":
        s = info["symbol"]
        if s in ("^N225", "^HSI", "^AXJO", "^NSEI"):
            return sessions["asia"]["open"]
        if s in ("^FTSE", "^GDAXI", "^FCHI"):
            return sessions["europe"]["open"]
        return sessions["us"]["open"] or sessions["forex"]["open"]
    if ac == "INTL_EQUITY":
        area = info.get("area", "")
        if area == "Europe":
            return sessions["europe"]["open"]
        if area == "Asia-Pacific":
            return sessions["asia"]["open"]
        return sessions["us"]["open"]
    # US_EQUITY / ETF: open during regular or extended hours Mon-Fri
    return sessions["us"]["label"] in ("OPEN", "PRE-MARKET", "AFTER HOURS")


def load_us_universe(path=UNIVERSE_FILE):
    """Loads [(symbol, name)] from trader/universe.txt (~5,900+ US companies)."""
    if not os.path.isfile(path):
        return []
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "|" in line:
                    sym, name = line.split("|", 1)
                    out.append((sym.strip().upper(), name.strip()))
                else:
                    out.append((line.upper(), ""))
    except Exception:
        pass
    return out


def yahoo_http_get(path, timeout=10):
    last_err = None
    for host in YAHOO_HOSTS:
        url = host + path
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError("Yahoo request failed for %s: %s" % (path.split("?")[0], last_err))


def fetch_spark_quotes(symbols, rng="1d", interval="5m", timeout=10):
    """Fetches quotes and mini bar series in batches of 20 via Yahoo v7/finance/spark."""
    quotes = {}
    series_map = {}
    clean = []
    seen = set()
    for s in symbols:
        u = str(s or "").strip().upper()
        if u and u not in seen:
            seen.add(u)
            clean.append(u)

    for i in range(0, len(clean), 20):
        batch = clean[i:i + 20]
        wanted = {to_yahoo(s): s for s in batch}
        q_syms = ",".join(urllib.parse.quote(to_yahoo(s), safe=".-=") for s in batch)
        path = "/v7/finance/spark?symbols=%s&range=%s&interval=%s" % (q_syms, rng, interval)
        try:
            raw = yahoo_http_get(path, timeout=timeout)
            doc = json.loads(raw)
            results = (doc.get("spark") or {}).get("result") or []
            for item in results:
                resp = item.get("response") or []
                if not resp:
                    continue
                r0 = resp[0]
                meta = r0.get("meta") or {}
                ysym = str(item.get("symbol") or meta.get("symbol") or "").upper()
                orig = wanted.get(ysym, ysym)
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                q_ind = ((r0.get("indicators") or {}).get("quote") or [{}])[0] or {}
                closes = [float(x) for x in (q_ind.get("close") or []) if x is not None]
                if price is None and closes:
                    price = closes[-1]
                if price is None:
                    continue
                p_f = float(price)
                prev_f = float(prev) if prev else (closes[0] if closes else p_f)
                chg_pct = ((p_f / prev_f) - 1.0) * 100.0 if prev_f else 0.0
                sign = "+" if chg_pct >= 0 else ""
                dec = price_decimals(orig, p_f)
                quotes[orig] = {
                    "symbol": orig,
                    "price": round(p_f, dec),
                    "prev_close": round(prev_f, dec),
                    "change_pct": round(chg_pct, 2),
                    "change": "%s%.2f%%" % (sign, chg_pct),
                    "volume": int(meta.get("regularMarketVolume") or 0),
                    "high": meta.get("regularMarketDayHigh"),
                    "low": meta.get("regularMarketDayLow"),
                    "currency": meta.get("currency") or "USD",
                    "exchange": meta.get("exchangeName") or "",
                    "name": meta.get("shortName") or meta.get("longName") or BUILTIN_CATALOG.get(orig, ("",))[0],
                    "time": datetime.datetime.now().strftime("%H:%M:%S"),
                    "asset": classify_asset(orig),
                }
                series_map[orig] = {
                    "t": r0.get("timestamp") or [],
                    "c": q_ind.get("close") or [],
                    "meta": meta,
                }
        except Exception:
            continue
    return quotes, series_map


def fetch_chart_bars(sym, rng="5d", interval="5m", timeout=10):
    """Fetches full OHLCV bars from Yahoo v8/finance/chart."""
    ysym = urllib.parse.quote(to_yahoo(sym), safe=".-=")
    path = "/v8/finance/chart/%s?range=%s&interval=%s" % (ysym, rng, interval)
    raw = yahoo_http_get(path, timeout=timeout)
    doc = json.loads(raw)
    res = (doc.get("chart") or {}).get("result") or []
    if not res:
        return {"bars": [], "meta": {}}
    r0 = res[0]
    meta = r0.get("meta") or {}
    stamps = r0.get("timestamp") or []
    q = ((r0.get("indicators") or {}).get("quote") or [{}])[0] or {}
    opens = q.get("open") or []
    highs = q.get("high") or []
    lows = q.get("low") or []
    closes = q.get("close") or []
    vols = q.get("volume") or []
    bars = []
    for i, ts in enumerate(stamps):
        c = closes[i] if i < len(closes) else None
        if ts is None or c is None:
            continue
        o = opens[i] if i < len(opens) and opens[i] is not None else c
        h = highs[i] if i < len(highs) and highs[i] is not None else c
        l = lows[i] if i < len(lows) and lows[i] is not None else c
        v = vols[i] if i < len(vols) and vols[i] is not None else 0
        bars.append({"t": int(ts), "o": float(o), "h": float(h), "l": float(l), "c": float(c), "v": float(v)})
    return {"bars": bars, "meta": meta}


def search_all_markets(query, limit=25, use_network=True):
    """Searches built-in global markets, the ~5,900+ US company universe, and live Yahoo Finance Search."""
    q = str(query or "").strip()
    if not q:
        results = []
        for sym in WATCHLIST_ALL_MARKETS[:limit]:
            info = classify_asset(sym)
            cat = BUILTIN_CATALOG.get(sym, (sym, info["asset_class"], info["region"]))
            results.append({
                "symbol": sym,
                "name": cat[0],
                "asset_class": info["asset_class"],
                "badge": info["badge"],
                "region": cat[2],
                "source": "catalog",
            })
        return results

    ql = q.lower()
    qu = q.upper()
    results = []
    seen = set()

    # 1. Exact/partial matches in built-in multi-market catalog
    for sym, (name, ac, region) in BUILTIN_CATALOG.items():
        if ql in sym.lower() or ql in name.lower() or ql in region.lower() or ql in ac.lower():
            info = classify_asset(sym)
            seen.add(sym)
            results.append({
                "symbol": sym,
                "name": name,
                "asset_class": info["asset_class"],
                "badge": info["badge"],
                "region": region,
                "source": "catalog",
                "_rank": 0 if sym == qu else (1 if sym.startswith(qu) else 2),
            })

    # 2. Search ~5,900+ US companies in trader/universe.txt
    for sym, name in load_us_universe():
        if sym in seen:
            continue
        if ql in sym.lower() or ql in name.lower():
            info = classify_asset(sym)
            seen.add(sym)
            results.append({
                "symbol": sym,
                "name": name,
                "asset_class": info["asset_class"],
                "badge": info["badge"],
                "region": info["region"],
                "source": "nasdaq_universe",
                "_rank": 0 if sym == qu else (1 if sym.startswith(qu) else 3),
            })
            if len(results) >= limit * 2:
                break

    # 3. Live Yahoo Finance global search (finds any company/market worldwide)
    if use_network:
        try:
            path = "/v1/finance/search?q=%s&quotesCount=%d&newsCount=0" % (urllib.parse.quote(q), limit)
            raw = yahoo_http_get(path, timeout=6)
            doc = json.loads(raw)
            for item in doc.get("quotes") or []:
                sym = str(item.get("symbol") or "").strip().upper()
                if not sym or sym in seen:
                    continue
                seen.add(sym)
                info = classify_asset(sym)
                results.append({
                    "symbol": sym,
                    "name": item.get("shortname") or item.get("longname") or sym,
                    "asset_class": info["asset_class"],
                    "badge": info["badge"],
                    "region": item.get("exchDisp") or item.get("exchange") or info["region"],
                    "quote_type": item.get("quoteType") or info["asset_class"],
                    "source": "yahoo_global",
                    "_rank": 0 if sym == qu else (1 if sym.startswith(qu) else 2),
                })
        except Exception:
            pass

    results.sort(key=lambda r: (r.get("_rank", 5), len(r["symbol"]), r["symbol"]))
    for r in results:
        r.pop("_rank", None)
    return results[:limit]
