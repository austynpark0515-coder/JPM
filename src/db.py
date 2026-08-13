"""SQLite cache layer. Main table is refreshed on a frequent interval;
holdings/fund_summary are written only by the nightly batch job
(scripts/refresh_holdings.py). Every row carries its own last_updated
timestamp so the UI can show live-vs-cached staleness per data point.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from src.config import CACHE_DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS quotes (
    ticker TEXT PRIMARY KEY,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    prev_close REAL,
    day_change REAL,
    day_change_pct REAL,
    nav REAL,
    nav_change REAL,
    nav_change_pct REAL,
    last_updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fund_summary (
    fund_ticker TEXT PRIMARY KEY,
    total_holdings INTEGER,
    total_assets REAL,
    sector_allocation_json TEXT,
    last_updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS holdings (
    fund_ticker TEXT NOT NULL,
    symbol TEXT NOT NULL,
    description TEXT,
    sub_industry TEXT,
    pct_net_assets REAL,
    shares_held REAL,
    market_value REAL,
    day_change_pct REAL,
    five_day_change_pct REAL,
    one_month_change_pct REAL,
    ytd_change_pct REAL,
    one_year_change_pct REAL,
    last_updated TEXT NOT NULL,
    PRIMARY KEY (fund_ticker, symbol)
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_conn():
    CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def upsert_quote(ticker: str, **fields):
    fields["last_updated"] = _now_iso()
    columns = ["ticker"] + list(fields.keys())
    values = [ticker] + list(fields.values())
    placeholders = ", ".join(["?"] * len(columns))
    update_clause = ", ".join(f"{c}=excluded.{c}" for c in fields.keys())
    with get_conn() as conn:
        conn.execute(
            f"INSERT INTO quotes ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(ticker) DO UPDATE SET {update_clause}",
            values,
        )


def get_quotes_df() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query("SELECT * FROM quotes", conn)


def upsert_fund_summary(fund_ticker: str, total_holdings: int, total_assets: float, sector_allocation: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO fund_summary (fund_ticker, total_holdings, total_assets, sector_allocation_json, last_updated)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(fund_ticker) DO UPDATE SET
                 total_holdings=excluded.total_holdings,
                 total_assets=excluded.total_assets,
                 sector_allocation_json=excluded.sector_allocation_json,
                 last_updated=excluded.last_updated""",
            (fund_ticker, total_holdings, total_assets, json.dumps(sector_allocation), _now_iso()),
        )


def get_fund_summary(fund_ticker: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT total_holdings, total_assets, sector_allocation_json, last_updated "
            "FROM fund_summary WHERE fund_ticker = ?",
            (fund_ticker,),
        ).fetchone()
    if row is None:
        return None
    total_holdings, total_assets, sector_json, last_updated = row
    return {
        "total_holdings": total_holdings,
        "total_assets": total_assets,
        "sector_allocation": json.loads(sector_json) if sector_json else {},
        "last_updated": last_updated,
    }


def replace_holdings(fund_ticker: str, holdings: list[dict]):
    """Wholesale-replaces one fund's holdings snapshot (nightly batch semantics)."""
    now = _now_iso()
    with get_conn() as conn:
        conn.execute("DELETE FROM holdings WHERE fund_ticker = ?", (fund_ticker,))
        conn.executemany(
            """INSERT INTO holdings
               (fund_ticker, symbol, description, sub_industry, pct_net_assets, shares_held,
                market_value, day_change_pct, five_day_change_pct, one_month_change_pct,
                ytd_change_pct, one_year_change_pct, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    fund_ticker,
                    h.get("symbol"),
                    h.get("description"),
                    h.get("sub_industry"),
                    h.get("pct_net_assets"),
                    h.get("shares_held"),
                    h.get("market_value"),
                    h.get("day_change_pct"),
                    h.get("five_day_change_pct"),
                    h.get("one_month_change_pct"),
                    h.get("ytd_change_pct"),
                    h.get("one_year_change_pct"),
                    now,
                )
                for h in holdings
            ],
        )


def get_holdings_df(fund_ticker: str) -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query(
            "SELECT * FROM holdings WHERE fund_ticker = ? ORDER BY pct_net_assets DESC",
            conn,
            params=(fund_ticker,),
        )
