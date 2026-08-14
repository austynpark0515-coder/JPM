"""Refreshes the main table: price snapshot for the full lineup, from
Finnhub's /quote endpoint — the only endpoint this project's free-tier key
actually has access to (verified live: /stock/candle and all /etf/* paths
403 on a free key; see finnhub_client.py).

Meant to run on a frequent interval during market hours (see
config.MAIN_TABLE_REFRESH_MINUTES) — ~40 funds x 1 call/fund is well
within the 60 calls/min free-tier limit.

NAV / NAV Change aren't pulled here — Finnhub only exposes market price
on /quote, not a fund's official NAV; see src/refresh_nav.py, which
sources those from JPM's own site instead. Day Change ($ and %) is
included here since /quote returns it for free (fields d/dp).
"""
from typing import Optional, Tuple

from src import db
from src.finnhub_client import FinnhubClient
from src.fund_reference import load_fund_reference


def refresh_main_table(client: Optional[FinnhubClient] = None) -> Tuple[int, Optional[str]]:
    """Returns (count of funds successfully updated, a sample error message
    if every call failed — so a mass failure is diagnosable from the UI
    instead of silently showing "0 funds refreshed")."""
    client = client or FinnhubClient()
    tickers = load_fund_reference()["ticker"].tolist()
    updated = 0
    last_error: Optional[str] = None
    for ticker in tickers:
        try:
            q = client.quote(ticker)
        except Exception as exc:
            last_error = f"{ticker}: {exc}"
            continue
        close = q.get("c")
        if not close:
            last_error = f"{ticker}: quote returned no price ({q})"
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
    return updated, (last_error if updated == 0 else None)


if __name__ == "__main__":
    db.init_db()
    count, error = refresh_main_table()
    print(f"Refreshed {count} funds.")
    if error:
        print(f"Sample error: {error}")
