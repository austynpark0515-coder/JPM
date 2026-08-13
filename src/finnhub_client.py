"""Thin Finnhub REST wrapper with a built-in rate limiter.

Endpoint paths and field names are verified against Finnhub's current
docs/client libraries. NOTE: /etf/profile, /etf/holdings, and /etf/sector
sit behind Finnhub's paid "ETFs, Funds and Indices" plan (~$500/mo) —
they will 403 on a free-tier key. /quote and /stock/candle are free-tier.
"""
import threading
import time
from typing import Optional

import requests

from src.config import FINNHUB_BASE_URL, FINNHUB_RATE_LIMIT_PER_MIN, get_finnhub_api_key


class RateLimiter:
    """Blocking, thread-safe spacing so calls never exceed calls_per_minute."""

    def __init__(self, calls_per_minute: int):
        self._min_interval = 60.0 / calls_per_minute
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self):
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            sleep_for = self._min_interval - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last_call = time.monotonic()


class FinnhubClient:
    def __init__(self, api_key: Optional[str] = None, calls_per_minute: int = FINNHUB_RATE_LIMIT_PER_MIN):
        self._api_key = api_key or get_finnhub_api_key()
        self._session = requests.Session()
        self._limiter = RateLimiter(calls_per_minute)

    def _get(self, path: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        params["token"] = self._api_key
        self._limiter.wait()
        resp = self._session.get(f"{FINNHUB_BASE_URL}{path}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def quote(self, symbol: str) -> dict:
        """Current price snapshot: c=current, h=high, l=low, o=open, pc=prev close, t=timestamp."""
        return self._get("/quote", {"symbol": symbol})

    def candles(self, symbol: str, resolution: str, from_ts: int, to_ts: int) -> dict:
        """Historical OHLCV. resolution e.g. 'D'. from_ts/to_ts are unix seconds."""
        return self._get(
            "/stock/candle",
            {"symbol": symbol, "resolution": resolution, "from": from_ts, "to": to_ts},
        )

    def etf_profile(self, symbol: str) -> dict:
        return self._get("/etf/profile", {"symbol": symbol})

    def etf_holdings(self, symbol: str) -> dict:
        return self._get("/etf/holdings", {"symbol": symbol})

    def etf_sector_exposure(self, symbol: str) -> dict:
        return self._get("/etf/sector", {"symbol": symbol})
