"""Fetch a real US large-cap universe (daily OHLCV) for the alpha-zoo OOS hunt.

Cross-sectional alphas (alpha101/gtja191/qlib158) need breadth — many symbols
per day. This pulls ~100 S&P-100 large-caps via yfinance (split/div-adjusted)
and writes a long/tidy CSV: date,symbol,open,high,low,close,volume,amount.

Run with SYSTEM python3 (has yfinance); alpha_bench runs in the venv (3.11).
"""
import sys
import pandas as pd
import yfinance as yf

# A liquid, survivorship-biased-but-fine-for-a-first-pass S&P 100 set.
SYMBOLS = [
    "AAPL","MSFT","AMZN","GOOGL","GOOG","META","NVDA","TSLA","BRK-B","JPM",
    "JNJ","V","PG","UNH","HD","MA","BAC","XOM","DIS","ADBE",
    "CRM","NFLX","CSCO","PFE","KO","PEP","INTC","CMCSA","ABT","TMO",
    "NKE","WMT","MRK","ORCL","ACN","COST","MCD","DHR","TXN","NEE",
    "WFC","LIN","BMY","UPS","PM","RTX","HON","QCOM","LOW","UNP",
    "IBM","AMGN","SBUX","CAT","GS","BA","GE","MMM","BLK","AXP",
    "GILD","CVX","LMT","SPGI","INTU","ISRG","NOW","AMD","BKNG","MDLZ",
    "ADP","TJX","CB","C","MO","DUK","SO","USB","CI","BDX",
    "T","VZ","COP","SLB","MS","SCHW","PNC","CL","EMR","FDX",
    "F","GM","DOW","KHC","MET","AIG","ALL","WBA","TGT","COF",
]


def main():
    start = sys.argv[1] if len(sys.argv) > 1 else "2016-01-01"
    end = sys.argv[2] if len(sys.argv) > 2 else "2024-12-31"
    out = sys.argv[3] if len(sys.argv) > 3 else "universe_sp100.csv"

    print(f"Fetching {len(SYMBOLS)} symbols {start}..{end} (auto-adjusted daily)...")
    raw = yf.download(
        SYMBOLS, start=start, end=end, auto_adjust=True,
        group_by="ticker", threads=True, progress=False,
    )

    frames = []
    missing = []
    for sym in SYMBOLS:
        try:
            sub = raw[sym].dropna(how="all")
        except KeyError:
            missing.append(sym)
            continue
        if sub.empty:
            missing.append(sym)
            continue
        df = sub.reset_index().rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        df["symbol"] = sym
        df = df[["date", "symbol", "open", "high", "low", "close", "volume"]]
        df = df.dropna(subset=["open", "high", "low", "close", "volume"])
        frames.append(df)

    if not frames:
        print("ERROR: no data fetched")
        sys.exit(1)

    full = pd.concat(frames, ignore_index=True)
    full["amount"] = full["close"] * full["volume"]
    full["date"] = pd.to_datetime(full["date"]).dt.strftime("%Y-%m-%d")
    full = full.sort_values(["date", "symbol"])
    full.to_csv(out, index=False)

    n_sym = full["symbol"].nunique()
    print(f"Wrote {out}: {len(full):,} rows, {n_sym} symbols, "
          f"{full['date'].min()}..{full['date'].max()}")
    if missing:
        print(f"Missing ({len(missing)}): {', '.join(missing)}")


if __name__ == "__main__":
    main()
