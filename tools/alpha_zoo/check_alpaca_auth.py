#!/usr/bin/env python3
"""Verify Alpaca credentials before a big fetch — prints masked info only.

Never prints your key/secret values. Tells you:
  - whether the creds file is actually filled in (no placeholders),
  - whether the keys authenticate against the PAPER and/or LIVE endpoint,
  - whether the IEX data feed works.

Run from tools/alpha_zoo:  ./.venv/bin/python check_alpaca_auth.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def main() -> int:
    p = _HERE / "alpaca_credentials.json"
    if not p.is_file():
        print("creds file: MISSING — create alpaca_credentials.json first.")
        return 1
    d = json.loads(p.read_text(encoding="utf-8"))
    k = (d.get("api_key") or "").strip()
    s = (d.get("api_secret") or "").strip()
    paper = bool(d.get("paper", True))
    placeholder = "REPLACE_WITH" in k or "REPLACE_WITH" in s

    print(f"creds file: present | paper flag = {paper}")
    print(f"placeholders still in file? {placeholder}")
    print(f"key   -> prefix={k[:2]!r} len={len(k)}  (PK*=paper, AK*=live)")
    print(f"secret-> len={len(s)} (value hidden)")
    if placeholder or not k or not s:
        print(">> File not filled with real keys. Edit alpaca_credentials.json and re-run.")
        return 1

    try:
        import alpaca_trade_api as tradeapi
    except ImportError:
        print(">> alpaca-trade-api not installed in this interpreter; use ./.venv/bin/python")
        return 1

    os.environ.setdefault("APCA_API_DATA_URL", "https://data.alpaca.markets")
    results = {}
    for label, url in [("PAPER", "https://paper-api.alpaca.markets"),
                       ("LIVE", "https://api.alpaca.markets")]:
        try:
            acct = tradeapi.REST(k, s, url, api_version="v2").get_account()
            results[label] = True
            print(f"{label:<5} endpoint: AUTH OK (account status={acct.status})")
        except Exception as e:  # noqa: BLE001
            results[label] = False
            print(f"{label:<5} endpoint: FAIL -> {str(e)[:80]}")

    base = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
    try:
        cli = tradeapi.REST(k, s, base, api_version="v2")
        n = len(cli.get_bars("AAPL", "1Day", start="2024-01-02", end="2024-01-10", feed="iex").df)
        print(f"DATA  iex bars: OK ({n} AAPL bars) — you're good to fetch.")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"DATA  iex bars: FAIL -> {str(e)[:80]}")

    if results.get("LIVE") and not results.get("PAPER") and paper:
        print(">> Your keys are LIVE keys but paper=true. Set \"paper\": false in the file.")
    elif results.get("PAPER") and not results.get("LIVE") and not paper:
        print(">> Your keys are PAPER keys but paper=false. Set \"paper\": true in the file.")
    elif not results.get("PAPER") and not results.get("LIVE"):
        print(">> Keys rejected by both endpoints — regenerate them in the Alpaca dashboard.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
