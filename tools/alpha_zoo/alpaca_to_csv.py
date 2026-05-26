#!/usr/bin/env python3
"""Fetch multi-symbol daily bars from Alpaca → tidy CSV for alpha_bench.py.

Pulls historical daily OHLCV for a basket of symbols over a date range and
writes the exact long/tidy shape alpha_bench expects:

    date,symbol,open,high,low,close,volume

Credentials (precedence):
  1. --key / --secret CLI flags
  2. a local, gitignored JSON file (default: ./alpaca_credentials.json):
         {"api_key": "...", "api_secret": "...", "paper": true}
     This file is in .gitignore — never commit it.
  3. APCA_API_KEY_ID / APCA_API_SECRET_KEY env (silent fallback only)

Then:
    python3 alpaca_to_csv.py --symbols AAPL,MSFT,NVDA,... --start 2021-01-01 --out universe.csv
    python3 alpha_bench.py universe.csv --top 20

Requires `alpaca-trade-api`:
    python3 -m pip install alpaca-trade-api
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("alpaca_to_csv")

_HERE = Path(__file__).resolve().parent
_DEFAULT_CRED_FILE = _HERE / "alpaca_credentials.json"
_OUT_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "volume"]


# --------------------------------------------------------------------------- #
# Credentials — local config / CLI, mirroring the Settings-store philosophy
# --------------------------------------------------------------------------- #
def resolve_credentials(
    key: Optional[str], secret: Optional[str], cred_file: Path
) -> tuple[str, str, bool]:
    """Return (api_key, api_secret, paper) from CLI > local file > env."""
    paper = True
    if key and secret:
        return key, secret, paper
    if cred_file.is_file():
        try:
            data = json.loads(cred_file.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise SystemExit(f"could not read {cred_file}: {exc}")
        k = key or data.get("api_key")
        s = secret or data.get("api_secret")
        paper = bool(data.get("paper", True))
        if k and s:
            return k, s, paper
    # Last-resort env fallback (alpaca-trade-api's own standard names).
    k = key or os.getenv("APCA_API_KEY_ID")
    s = secret or os.getenv("APCA_API_SECRET_KEY")
    if k and s:
        return k, s, paper
    raise SystemExit(
        f"no Alpaca credentials found. Provide --key/--secret, or create "
        f"{cred_file.name} with {{\"api_key\":..., \"api_secret\":...}}."
    )


def build_client(api_key: str, api_secret: str, paper: bool) -> Any:
    """Construct a tradeapi.REST client for historical bar fetching."""
    try:
        import alpaca_trade_api as tradeapi
    except ImportError as exc:
        raise SystemExit(
            "alpaca-trade-api not installed. Run: python3 -m pip install alpaca-trade-api"
        ) from exc
    base_url = (
        "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
    )
    os.environ.setdefault("APCA_API_DATA_URL", "https://data.alpaca.markets")
    return tradeapi.REST(api_key, api_secret, base_url, api_version="v2")


# --------------------------------------------------------------------------- #
# Fetch — pure-ish core with a client seam so it's testable without network
# --------------------------------------------------------------------------- #
def _day_timeframe(client: Any) -> Any:
    """Return the SDK's daily TimeFrame, or the string '1Day' as a fallback."""
    try:
        from alpaca_trade_api.rest import TimeFrame

        return TimeFrame.Day
    except Exception:  # noqa: BLE001 — tests inject a fake client
        return "1Day"


def _bars_df_to_rows(bars_df: pd.DataFrame, symbol: str) -> list[dict[str, Any]]:
    """Convert one symbol's Alpaca bars .df into tidy rows (date-keyed)."""
    if bars_df is None or len(bars_df) == 0:
        return []
    rows: list[dict[str, Any]] = []
    for ts, row in bars_df.iterrows():
        # Alpaca daily bar index is a tz-aware Timestamp at session open.
        date = pd.Timestamp(ts).tz_localize(None).date().isoformat()
        rows.append(
            {
                "date": date,
                "symbol": symbol,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
            }
        )
    return rows


def fetch_universe(
    client: Any,
    symbols: list[str],
    start: str,
    end: Optional[str],
    *,
    feed: str = "iex",
    timeframe: Any = None,
    pause: float = 0.0,
) -> pd.DataFrame:
    """Fetch daily bars for every symbol and return one tidy DataFrame."""
    tf = timeframe if timeframe is not None else _day_timeframe(client)
    all_rows: list[dict[str, Any]] = []
    n = len(symbols)
    for i, sym in enumerate(symbols, start=1):
        sym = sym.strip().upper()
        if not sym:
            continue
        try:
            kwargs: dict[str, Any] = {"start": start, "feed": feed}
            if end:
                kwargs["end"] = end
            try:
                bars = client.get_bars(sym, tf, **kwargs).df
            except TypeError:
                kwargs.pop("feed", None)  # older SDK without feed kwarg
                bars = client.get_bars(sym, tf, **kwargs).df
            rows = _bars_df_to_rows(bars, sym)
            if not rows:
                logger.warning("%s: no bars returned (skipped)", sym)
            all_rows.extend(rows)
            logger.info("[%d/%d] %s: %d bars", i, n, sym, len(rows))
        except Exception as exc:  # noqa: BLE001 — one bad symbol must not abort the run
            logger.warning("[%d/%d] %s: fetch failed (%s)", i, n, sym, exc)
        if pause:
            time.sleep(pause)

    if not all_rows:
        return pd.DataFrame(columns=_OUT_COLUMNS)
    df = pd.DataFrame(all_rows, columns=_OUT_COLUMNS)
    df = df.drop_duplicates(subset=["date", "symbol"]).sort_values(["date", "symbol"])
    return df.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Index constituents (current membership -> survivorship-biased; flagged in CLI)
# --------------------------------------------------------------------------- #
_WIKI_UNIVERSES = {
    "sp500": ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "Symbol"),
    "sp100": ("https://en.wikipedia.org/wiki/S%26P_100", "Symbol"),
}


def fetch_constituents(universe: str) -> list[str]:
    """Pull current index members from Wikipedia. Alpaca uses dotted class
    tickers (BRK.B), which is also Wikipedia's format, so no symbol rewriting."""
    import io

    import requests

    url, col = _WIKI_UNIVERSES[universe]
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (alpha-zoo research)"}, timeout=20)
    resp.raise_for_status()
    for tbl in pd.read_html(io.StringIO(resp.text)):
        if col in tbl.columns:
            out = [str(s).strip().upper() for s in tbl[col].tolist()]
            return [s for s in out if s and s != "NAN"]
    raise RuntimeError(f"could not find a '{col}' column on {url}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _read_symbols(args: argparse.Namespace) -> list[str]:
    syms: list[str] = []
    if getattr(args, "universe", None):
        fetched = fetch_constituents(args.universe)
        logger.info("%s: %d constituents from Wikipedia (current membership)",
                    args.universe, len(fetched))
        syms.extend(fetched)
    if args.symbols:
        syms.extend(s for s in args.symbols.replace(",", " ").split())
    if args.symbols_file:
        text = Path(args.symbols_file).expanduser().read_text(encoding="utf-8")
        syms.extend(s for line in text.splitlines() for s in line.replace(",", " ").split())
    # de-dup, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for s in syms:
        u = s.strip().upper()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fetch Alpaca daily bars for many symbols → tidy CSV for alpha_bench.py.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--universe", choices=["sp500", "sp100"],
                    help="Fetch current index constituents (survivorship-biased).")
    ap.add_argument("--symbols", help="Comma/space list, e.g. AAPL,MSFT,NVDA.")
    ap.add_argument("--symbols-file", help="File with symbols (one per line or comma-separated).")
    ap.add_argument("--start", default="2021-01-01", help="Start date YYYY-MM-DD.")
    ap.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: latest).")
    ap.add_argument("--feed", default="iex", choices=["iex", "sip"],
                    help="Data feed. Free Alpaca accounts get 'iex' only.")
    ap.add_argument("--out", default="universe.csv", help="Output CSV path.")
    ap.add_argument("--key", help="Alpaca API key (overrides config file).")
    ap.add_argument("--secret", help="Alpaca API secret (overrides config file).")
    ap.add_argument("--cred-file", default=str(_DEFAULT_CRED_FILE),
                    help="Local JSON credentials file.")
    ap.add_argument("--pause", type=float, default=0.0,
                    help="Seconds to sleep between symbols (rate-limit cushion).")
    args = ap.parse_args(argv)

    symbols = _read_symbols(args)
    if not symbols:
        ap.error("provide --universe, --symbols, and/or --symbols-file")
    if args.universe:
        logger.warning("%s uses CURRENT constituents -> survivorship-biased; "
                       "delisted/removed names are excluded, biasing IC upward.", args.universe)
    logger.info("Fetching %d symbols, daily bars from %s%s (feed=%s)",
                len(symbols), args.start, f" to {args.end}" if args.end else "", args.feed)

    api_key, api_secret, paper = resolve_credentials(
        args.key, args.secret, Path(args.cred_file).expanduser()
    )
    client = build_client(api_key, api_secret, paper)

    df = fetch_universe(client, symbols, args.start, args.end,
                        feed=args.feed, pause=args.pause)
    if df.empty:
        logger.error("No data fetched — check symbols, dates, feed, and credentials.")
        return 1

    out_path = Path(args.out).expanduser()
    df.to_csv(out_path, index=False)
    n_syms = df["symbol"].nunique()
    n_dates = df["date"].nunique()
    logger.info("Wrote %s rows (%d symbols x %d dates) -> %s",
                f"{len(df):,}", n_syms, n_dates, out_path)
    if n_syms < 5:
        logger.warning("Only %d symbols — cross-sectional IC needs >=5 per bar.", n_syms)
    print(f"\nNext:  python3 alpha_bench.py {out_path} --top 20 --out results.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
