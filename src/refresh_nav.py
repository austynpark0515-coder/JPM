"""Refreshes NAV / NAV Change for the main table, sourced from JPM's own
historical-NAV export (src/jpm_data_client.py) — Finnhub's free tier has
no NAV field at all (see finnhub_client.py). NAV is an end-of-day figure,
not intraday, so a short trailing window is enough to get the latest
published value and compute day-over-day change.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from src import db
from src.fund_reference import load_fund_reference
from src.jpm_data_client import fetch_historical_nav

LOOKBACK_DAYS = 10  # comfortably covers weekends/holidays to get 2 trading days


def refresh_nav_snapshot() -> int:
    """Returns the count of funds successfully updated."""
    ref = load_fund_reference()
    today = date.today()
    start = today - timedelta(days=LOOKBACK_DAYS)
    updated = 0

    for _, row in ref.iterrows():
        cusip = row.get("cusip")
        if not isinstance(cusip, str) or not cusip:
            continue
        try:
            nav_df = fetch_historical_nav(cusip, start, today)
        except Exception:
            continue
        if nav_df.empty:
            continue

        nav_df = nav_df.sort_values("Date")
        latest_nav = nav_df.iloc[-1].get("NAV")
        if latest_nav is None or latest_nav != latest_nav:  # NaN check
            continue

        nav_change: Optional[float] = None
        nav_change_pct: Optional[float] = None
        if len(nav_df) >= 2:
            prior_nav = nav_df.iloc[-2].get("NAV")
            if prior_nav is not None and prior_nav == prior_nav and prior_nav != 0:
                nav_change = latest_nav - prior_nav
                nav_change_pct = nav_change / prior_nav * 100

        db.upsert_quote(
            row["ticker"],
            nav=latest_nav,
            nav_change=nav_change,
            nav_change_pct=nav_change_pct,
            nav_last_updated=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        updated += 1

    return updated


if __name__ == "__main__":
    db.init_db()
    count = refresh_nav_snapshot()
    print(f"Refreshed NAV for {count} funds.")
