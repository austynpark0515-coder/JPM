"""Client for JPM's own public fund-data export endpoints
(FundsMarketingHandler) — no API key or login required, verified live.
These are the source for constituent holdings and historical NAV/market
price, which Finnhub only exposes on a paid plan (see finnhub_client.py).
Both endpoints are keyed by CUSIP, not ticker — see fund_reference.py's
`cusip` column (extracted from each fund's own fact sheet PDF via
scripts/extract_cusips.py).
"""
import io
from datetime import date
from typing import Optional

import pandas as pd
import requests

BASE_URL = "https://am.jpmorgan.com/FundsMarketingHandler/excel"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_holdings(cusip: str) -> pd.DataFrame:
    """Full daily constituent holdings for an ETF, as published by JPM.

    Returns columns: Ticker, Security Description, Security Type, Method,
    Shares/Par, Market Value (USD), Country, Currency, Sector, Industry,
    % of Net Assets (plus a few bond-only fields, blank for equity funds).
    """
    params = {
        "type": "dailyETFHoldings",
        "cusip": cusip,
        "country": "us",
        "role": "adv",
        "fundType": "N_ETF",
        "locale": "en-US",
        "isUnderlyingHolding": "false",
        "isProxyHolding": "false",
    }
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    raw = pd.read_excel(io.BytesIO(resp.content), engine="openpyxl", header=None)

    header_rows = raw.index[raw.iloc[:, 0] == "Ticker"]
    if len(header_rows) == 0:
        return pd.DataFrame()
    header_row = header_rows[0]

    df = raw.iloc[header_row + 1:].copy()
    df.columns = raw.iloc[header_row]
    df = df.dropna(subset=["Ticker"]).reset_index(drop=True)
    return df


def fetch_historical_nav(cusip: str, from_date: date, to_date: date) -> pd.DataFrame:
    """Historical daily NAV + market price, as published by JPM.

    Returns columns: Date (datetime64), NAV (float), Market Price (float).
    """
    params = {
        "type": "historicalNav",
        "cusip": cusip,
        "country": "us",
        "role": "adv",
        "locale": "en-US",
        "fromDate": from_date.isoformat(),
        "toDate": to_date.isoformat(),
    }
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    raw = pd.read_excel(io.BytesIO(resp.content), engine="openpyxl", header=None)

    header_rows = raw.index[raw.iloc[:, 0] == "Date"]
    if len(header_rows) == 0:
        return pd.DataFrame()
    header_row = header_rows[0]

    df = raw.iloc[header_row + 1:].copy()
    df.columns = raw.iloc[header_row]
    df = df.dropna(subset=["Date"]).reset_index(drop=True)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df["NAV"] = pd.to_numeric(df["NAV"], errors="coerce")
    if "Market Price" in df.columns:
        df["Market Price"] = pd.to_numeric(df["Market Price"], errors="coerce")
    return df
