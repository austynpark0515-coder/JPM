"""Refreshes the main table: price snapshot for the full lineup, from
Finnhub's /quote endpoint — the only endpoint this project's free-tier key
actually has access to (verified live: /stock/candle and all /etf/* paths
403 on a free key; see finnhub_client.py).

Meant to run on a frequent interval during market hours (see
config.MAIN_TABLE_REFRESH_MINUTES) — ~40 funds x 1 call/fund is well
within the 60 calls/min free-tier limit.

Columns NOT available on this plan, left blank rather than faked:
- Volume, YTD Return — both require /stock/candle (paid).
- NAV / NAV Change — Finnhub only exposes market price on /quote, not a
  fund's official NAV (that lives in the paid /etf/profile).
Day Change ($ and %) is included instead — /quote returns it for free
(fields d/dp) and it's a reasonable free substitute snapshot metric.
"""
from typing import Optional

from src import db
from src.finnhub_client import FinnhubClient
from src.fund_reference import load_fund_reference


def refresh_main_table(client: Optional[FinnhubClient] = None) -> int:
    """Returns the count of funds successfully updated."""
    client = client or FinnhubClient()
    tickers = load_fund_reference()["ticker"].tolist()
    updated = 0
    for ticker in tickers:
        try:
            q = client.quote(ticker)
        except Exception:
            continue
        close = q.get("c")
        if not close:
            continue
        db.upsert_quote(
            ticker,
            open=q.get("o"),
            high=q.get("h"),
            low=q.get("l"),
            close=close,
            prev_close=q.get("pc"),
            day_change=q.get("d"),
            day_change_pct=q.get("dp"),
            nav=None,
            nav_change=None,
            nav_change_pct=None,
        )
        updated += 1
    return updated


if __name__ == "__main__":
    db.init_db()
    count = refresh_main_table()
    print(f"Refreshed {count} funds.")
