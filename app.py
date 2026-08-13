"""JPMorgan ETF Tracking Dashboard — main lineup view.

Business/product lens on JPM AM's ETF lineup: price snapshot grouped by
asset class. Holdings drill-down lives on the Fund Detail page (see
pages/) — deferred to v2, see that page's docstring.

Only /quote is free on this project's Finnhub plan (verified live), so
this table shows Close/Open/High/Low/Prev Close/Day Change $ and %.
Volume and YTD Return need /stock/candle, which is paid; NAV needs the
paid /etf/profile. Both are left blank rather than faked.
"""
import pandas as pd
import streamlit as st

from src import db
from src.fund_reference import ASSET_CLASS_ORDER, load_fund_reference
from src.refresh_main import refresh_main_table

st.set_page_config(page_title="JPM ETF Tracking Dashboard", layout="wide")
db.init_db()

st.title("J.P. Morgan ETF Tracking Dashboard")
st.caption(
    "Public market data via Finnhub, refreshed on a polling interval — not true real-time. "
    "Self-directed analytical project; not affiliated with or sourced from JPM's internal systems."
)

reference = load_fund_reference()
quotes = db.get_quotes_df()

col_refresh, col_freshness = st.columns([1, 4])
with col_refresh:
    if st.button("Refresh prices now", help="Pulls a current price snapshot for the full lineup (~1 min)."):
        with st.spinner("Refreshing lineup from Finnhub..."):
            n = refresh_main_table()
        st.success(f"Refreshed {n} funds.")
        quotes = db.get_quotes_df()
with col_freshness:
    if not quotes.empty:
        oldest = quotes["last_updated"].min()
        st.caption(f"Oldest price in cache: {oldest}")

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
    st.info("No cached prices yet — click **Refresh prices now** to pull the current lineup.")

display_columns = {
    "ticker": "Ticker",
    "fund_name": "Fund Name",
    "close": "Close",
    "day_change": "Day Chg $",
    "day_change_pct": "Day Chg %",
    "nav": "NAV",
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
                "NAV": st.column_config.NumberColumn(help="Not available on Finnhub's free tier — market price only."),
            },
        )
        rows = event.selection.rows if event and event.selection else []
        if rows:
            picked_ticker = table.iloc[rows[0]]["Ticker"]
            st.session_state["selected_ticker"] = picked_ticker
            st.page_link("pages/1_Fund_Detail.py", label=f"Open {picked_ticker} holdings detail →")

st.caption(
    "NAV / NAV Change columns are blank pending a NAV-capable data source — "
    "Finnhub's free tier exposes market price, not official fund NAV."
)
