"""Nightly batch job: refreshes holdings + multi-horizon returns for the
full ETF lineup.

NOT meant to run inline with a Streamlit request — a full pass makes
~1-2 Finnhub calls per constituent per fund (holdings list + one candle
call per constituent for multi-horizon returns), which can take 1-2 hours
across ~40 funds at the free-tier 60 calls/min limit. Schedule this
externally (e.g. a GitHub Actions cron job) and let the app read from the
SQLite cache (data/cache.db) the rest of the day.

Run from the project root: python -m scripts.refresh_holdings

IMPORTANT — PLAN GATE (verified live against this project's key, not just
docs): /etf/profile, /etf/holdings, and /etf/sector all 403. So does
/stock/candle, which this script also depends on for multi-horizon
holdings returns — confirmed on both an ETF symbol and a plain equity
(AAPL), so it's a plan-wide restriction, not ETF-specific. Free tier here
is /quote only. Decision: holdings drill-down is deferred to v2 (see
pages/1_Fund_Detail.py). This script's field-name handling is correct
against Finnhub's documented response shapes for whenever a paid key or
alternate holdings source is wired in.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from src import db
from src.finnhub_client import FinnhubClient
from src.fund_reference import load_fund_reference


def _pct_change(latest: Optional[float], prior: Optional[float]) -> Optional[float]:
    if latest is None or prior in (None, 0):
        return None
    return (latest - prior) / prior * 100


def _multi_horizon_returns(client: FinnhubClient, symbol: str) -> dict:
    """One candle call covering ~1 year yields all five horizons at once."""
    now = datetime.now(timezone.utc)
    lookback_start = now - timedelta(days=400)  # buffer for weekends/holidays
    candles = client.candles(symbol, "D", int(lookback_start.timestamp()), int(now.timestamp()))
    if candles.get("s") != "ok" or not candles.get("c"):
        return {}

    closes = candles["c"]
    timestamps = candles.get("t", [])
    latest = closes[-1]

    def close_n_trading_days_back(n: int) -> Optional[float]:
        idx = len(closes) - 1 - n
        return closes[idx] if idx >= 0 else None

    jan1_ts = datetime(now.year, 1, 1, tzinfo=timezone.utc).timestamp()
    jan1_close = next((c for c, t in zip(closes, timestamps) if t >= jan1_ts), None)

    return {
        "day_change_pct": _pct_change(latest, close_n_trading_days_back(1)),
        "five_day_change_pct": _pct_change(latest, close_n_trading_days_back(5)),
        "one_month_change_pct": _pct_change(latest, close_n_trading_days_back(21)),
        "ytd_change_pct": _pct_change(latest, jan1_close),
        "one_year_change_pct": _pct_change(latest, close_n_trading_days_back(252)),
    }


def refresh_fund_holdings(client: FinnhubClient, fund_ticker: str) -> int:
    profile = client.etf_profile(fund_ticker).get("profile", {})
    raw_holdings = client.etf_holdings(fund_ticker).get("holdings", [])
    sector_exposure = client.etf_sector_exposure(fund_ticker).get("sectorExposure", [])

    total_assets = profile.get("aum")
    # Fund-level sector breakdown comes straight from /etf/sector — Finnhub's
    # /etf/holdings rows carry no per-holding sector/industry field, so
    # summing from holdings (as originally sketched) isn't possible.
    sector_alloc = {row["industry"]: row["exposure"] for row in sector_exposure if row.get("industry")}
    enriched = []

    for h in raw_holdings:
        symbol = h.get("symbol")
        weight = h.get("percent")

        try:
            returns = _multi_horizon_returns(client, symbol) if symbol else {}
        except Exception:
            returns = {}

        enriched.append(
            {
                "symbol": symbol,
                "description": h.get("name"),
                # No per-holding sub-industry field exists on Finnhub's ETF
                # holdings endpoint at any plan tier; left blank rather than
                # mislabeling the fund-level sector as a per-holding value.
                "sub_industry": None,
                "pct_net_assets": weight,
                "shares_held": h.get("share"),
                "market_value": h.get("value"),
                **returns,
            }
        )

    db.replace_holdings(fund_ticker, enriched)
    db.upsert_fund_summary(
        fund_ticker,
        total_holdings=len(enriched),
        total_assets=total_assets,
        sector_allocation=sector_alloc,
    )
    return len(enriched)


def refresh_all_holdings():
    db.init_db()
    client = FinnhubClient()
    tickers = load_fund_reference()["ticker"].tolist()
    for ticker in tickers:
        try:
            count = refresh_fund_holdings(client, ticker)
            print(f"{ticker}: {count} holdings refreshed")
        except Exception as exc:
            print(f"{ticker}: failed ({exc})")


if __name__ == "__main__":
    refresh_all_holdings()
