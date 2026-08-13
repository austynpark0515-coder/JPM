"""Central configuration: paths, refresh intervals, rate limits."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
FUND_REFERENCE_CSV = DATA_DIR / "fund_reference.csv"
CACHE_DB_PATH = DATA_DIR / "cache.db"

# Finnhub free tier: 60 calls/minute.
FINNHUB_RATE_LIMIT_PER_MIN = 60
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# Main table (price/NAV/volume) refresh cadence during market hours.
MAIN_TABLE_REFRESH_MINUTES = 15

# Holdings + multi-horizon constituent returns are refreshed by the nightly
# batch job only (scripts/refresh_holdings.py), never on-demand — a full
# lineup pass can take 1-2 hours at the free-tier rate limit.
HOLDINGS_STALE_AFTER_HOURS = 30


def get_finnhub_api_key() -> str:
    """Reads the Finnhub API key from Streamlit secrets, falling back to env var."""
    try:
        import streamlit as st
        if "FINNHUB_API_KEY" in st.secrets:
            return st.secrets["FINNHUB_API_KEY"]
    except Exception:
        pass
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        raise RuntimeError(
            "FINNHUB_API_KEY not found. Set it in .streamlit/secrets.toml "
            "(copy from secrets.toml.example) or as an environment variable."
        )
    return api_key
