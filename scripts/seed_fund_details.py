"""Pre-populates holdings + NAV history for the full lineup, sourced from
JPM's own site (src/refresh_fund_detail.py) — no API key, no paid plan.

Unlike the original Finnhub-holdings plan, this is fast enough (2 HTTP
requests per fund) to run on demand from the Fund Detail page itself; this
script exists to pre-seed data/cache.db so a freshly deployed app doesn't
show empty pages before anyone's clicked into a fund yet.

Run from the project root: python -m scripts.seed_fund_details
"""
from src import db
from src.fund_reference import load_fund_reference
from src.refresh_fund_detail import refresh_fund_detail


def main():
    db.init_db()
    tickers = load_fund_reference()["ticker"].tolist()
    for ticker in tickers:
        try:
            ok = refresh_fund_detail(ticker)
            print(f"{ticker}: {'refreshed' if ok else 'skipped (no CUSIP on file)'}")
        except Exception as exc:
            print(f"{ticker}: failed ({exc})")


if __name__ == "__main__":
    main()
