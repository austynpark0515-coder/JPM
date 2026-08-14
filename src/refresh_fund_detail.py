"""Refreshes one fund's holdings + NAV history from JPM's own site
(src/jpm_data_client.py). Cheap enough (2 HTTP requests) to run on-demand
when a user opens a fund's detail page — no nightly batch needed, unlike
the original Finnhub-holdings plan that turned out to need a paid key.
"""
from datetime import date
from typing import Optional

import pandas as pd

from src import db
from src.fund_reference import load_fund_reference
from src.jpm_data_client import fetch_historical_nav, fetch_holdings

# Far enough back to cover any current fund's inception; JPM's endpoint
# just returns whatever history exists if fromDate predates it.
NAV_HISTORY_START = date(2015, 1, 1)


def get_cusip(ticker: str) -> Optional[str]:
    ref = load_fund_reference()
    row = ref[ref["ticker"] == ticker]
    if row.empty:
        return None
    cusip = row.iloc[0].get("cusip")
    return cusip if isinstance(cusip, str) and cusip else None


def _pct_to_float(val) -> Optional[float]:
    if isinstance(val, str):
        val = val.strip().rstrip("%")
        try:
            return float(val)
        except ValueError:
            return None
    if isinstance(val, (int, float)):
        return float(val)
    return None


def refresh_fund_detail(ticker: str) -> bool:
    """Returns True if data was refreshed, False if no CUSIP is on file
    (e.g. a too-newly-launched fund with no fact sheet yet)."""
    cusip = get_cusip(ticker)
    if not cusip:
        return False

    holdings_df = fetch_holdings(cusip)
    enriched = []
    sector_alloc: dict = {}
    total_assets = 0.0
    for _, h in holdings_df.iterrows():
        weight = _pct_to_float(h.get("% of Net Assets"))
        sector = h.get("Sector")
        if isinstance(sector, str) and sector and weight is not None and pd.notna(weight):
            sector_alloc[sector] = sector_alloc.get(sector, 0.0) + weight
        market_value = h.get("Market Value (USD)")
        if isinstance(market_value, (int, float)) and pd.notna(market_value):
            total_assets += market_value
        enriched.append(
            {
                "symbol": h.get("Ticker"),
                "description": h.get("Security Description"),
                "sector": sector,
                "sub_industry": h.get("Industry"),
                "pct_net_assets": weight,
                "shares_held": h.get("Shares/Par"),
                "market_value": market_value,
            }
        )
    db.replace_holdings(ticker, enriched)
    db.upsert_fund_summary(
        ticker,
        total_holdings=len(enriched),
        total_assets=total_assets or None,
        sector_allocation=sector_alloc,
    )

    nav_df = fetch_historical_nav(cusip, NAV_HISTORY_START, date.today())
    nav_rows = [
        {
            "date": row["Date"].date().isoformat(),
            "nav": row.get("NAV"),
            "market_price": row.get("Market Price"),
        }
        for _, row in nav_df.iterrows()
    ]
    db.replace_nav_history(ticker, nav_rows)

    return True
