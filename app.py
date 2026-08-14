"""JPMorgan ETF Tracking Dashboard — main lineup view.

Business/product lens on JPM AM's ETF lineup: price snapshot grouped by
asset class. Holdings drill-down lives on the Fund Detail page (see
pages/).

Price/OHLC comes from Finnhub's free /quote endpoint (verified live —
/stock/candle and all /etf/* endpoints are paid on this plan). NAV / NAV
Change come from JPM's own historical-NAV export
(src/jpm_data_client.py, src/refresh_nav.py) — Finnhub has no NAV field
at all on any plan tier for ETFs.

Price and NAV are pulled from two different sources on two different
cadences under the hood (NAV is end-of-day and rarely worth re-pulling
more than once a day), but share a single "Refresh all data" button —
simpler for a viewer than reasoning about two buttons.
"""
import pandas as pd
import streamlit as st

from src import db
from src.fund_reference import ASSET_CLASS_ORDER, load_fund_reference
from src.refresh_main import refresh_main_table
from src.refresh_nav import refresh_nav_snapshot

st.set_page_config(page_title="JPM ETF Tracking Dashboard", layout="wide")
db.init_db()

st.title("J.P. Morgan ETF Tracking Dashboard")
st.caption(
    "Public market data via Finnhub, refreshed on a polling interval — not true real-time. "
    "Self-directed analytical project; not affiliated with or sourced from JPM's internal systems."
)

reference = load_fund_reference()
quotes = db.get_quotes_df()

col_refresh, col_freshness = st.columns([1, 3])
with col_refresh:
    if st.button("Refresh all data", help="Pulls current prices from Finnhub and NAV from JPM's site for the full lineup (~2-3 min)."):
        with st.spinner("Refreshing prices from Finnhub..."):
            n_price, price_error = refresh_main_table()
        with st.spinner("Refreshing NAV from JPM..."):
            n_nav, nav_error = refresh_nav_snapshot()
        st.success(f"Refreshed prices for {n_price} funds and NAV for {n_nav} funds.")
        if price_error:
            st.error(f"Price refresh got 0 funds — sample error: {price_error}")
        if nav_error:
            st.error(f"NAV refresh got 0 funds — sample error: {nav_error}")
        quotes = db.get_quotes_df()
with col_freshness:
    if not quotes.empty:
        oldest_price = quotes["last_updated"].min()
        st.caption(f"Oldest price in cache: {oldest_price}")
        nav_timestamps = quotes["nav_last_updated"].dropna()
        if not nav_timestamps.empty:
            st.caption(f"Oldest NAV in cache: {nav_timestamps.min()}")

merged = reference.merge(quotes, left_on="ticker", right_on="ticker", how="left")

_numeric_quote_cols = ["open", "high", "low", "close", "prev_close", "day_change", "day_change_pct", "nav", "nav_change", "nav_change_pct"]
merged[_numeric_quote_cols] = merged[_numeric_quote_cols].apply(pd.to_numeric, errors="coerce")

with st.sidebar:
    st.header("Filters")
    selected_classes = st.multiselect("Asset class", ASSET_CLASS_ORDER, default=ASSET_CLASS_ORDER)
    search = st.text_input("Search ticker or fund name")

filtered = merged[merged["asset_class"].isin(selected_classes)]
if search:
    needle = search.strip().lower()
    filtered = filtered[
        filtered["ticker"].str.lower().str.contains(needle)
        | filtered["fund_name"].str.lower().str.contains(needle)
    ]

if quotes.empty:
    st.info("No cached prices yet — click **Refresh all data** to pull the current lineup.")

display_columns = {
    "ticker": "Ticker",
    "fund_name": "Fund Name",
    "close": "Close",
    "day_change": "Day Chg $",
    "day_change_pct": "Day Chg %",
    "nav": "NAV",
    "nav_change": "NAV Chg $",
    "nav_change_pct": "NAV Chg %",
    "open": "Open",
    "high": "High",
    "low": "Low",
    "prev_close": "Prev Close",
    "fact_sheet_url": "Fact Sheet",
    "last_updated": "Last Updated",
}

for asset_class in ASSET_CLASS_ORDER:
    section = filtered[filtered["asset_class"] == asset_class]
    if section.empty:
        continue
    with st.expander(f"{asset_class} ({len(section)} funds)", expanded=True):
        table = section[list(display_columns.keys())].rename(columns=display_columns)
        event = st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
            key=f"table_{asset_class}",
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Fact Sheet": st.column_config.LinkColumn(display_text="Open PDF"),
                "NAV": st.column_config.NumberColumn(help="Sourced from JPM's own site (end-of-day) — click Refresh all data to populate."),
            },
        )
        rows = event.selection.rows if event and event.selection else []
        if rows:
            picked_ticker = table.iloc[rows[0]]["Ticker"]
            st.session_state["selected_ticker"] = picked_ticker
            st.page_link("pages/1_Fund_Detail.py", label=f"Open {picked_ticker} holdings detail →")

st.markdown(
    """
    <div style="margin-top:3rem; padding:1.75rem 1rem 1.25rem; border-top:1px solid #E0E4E8; text-align:center;">
        <div style="color:#00263E; font-weight:700; font-size:1rem; letter-spacing:0.04em;">
            J.P. MORGAN ASSET MANAGEMENT
        </div>
        <div style="color:#8A8F98; font-size:0.75rem; margin-top:0.4rem; max-width:560px; margin-left:auto; margin-right:auto;">
            Self-directed analytical project built on public market data. Not affiliated with,
            endorsed by, or sourced from J.P. Morgan Asset Management's internal systems.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
