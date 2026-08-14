"""ETF Detail / Holdings Drill-Down — one fund's constituents and price
history, modeled on a brokerage holdings screen but adapted to fund-level
(not personal-account) data: no Quantity/Cost Basis/Gain-Loss/Reinvest
fields.

Holdings and NAV/market-price history are sourced directly from JPM's own
public fund-data export endpoints (src/jpm_data_client.py) — no API key,
no paid plan. Fetched on-demand per fund (fast: 2 HTTP requests) and
cached in SQLite; see src/refresh_fund_detail.py.
"""
from datetime import date, timedelta

import plotly.graph_objects as go
import streamlit as st

from src import db
from src.fund_reference import load_fund_reference
from src.refresh_fund_detail import get_cusip, refresh_fund_detail

st.set_page_config(page_title="Fund Detail — JPM ETF Dashboard", layout="wide")
db.init_db()

reference = load_fund_reference()
tickers = reference["ticker"].tolist()
default_ticker = st.session_state.get("selected_ticker", tickers[0] if tickers else None)

ticker = st.selectbox(
    "Fund",
    tickers,
    index=tickers.index(default_ticker) if default_ticker in tickers else 0,
)
fund_row = reference[reference["ticker"] == ticker].iloc[0]

st.title(f"{fund_row['fund_name']} ({ticker})")
st.caption(f"Asset class: {fund_row['asset_class']}")

cusip = get_cusip(ticker)
if not cusip:
    st.warning(
        "No CUSIP on file for this fund yet, so holdings and price history can't be "
        "fetched — this fund is likely too newly launched to have a JPM fact sheet "
        "published (CUSIPs are extracted from fact sheets; see scripts/extract_cusips.py)."
    )
    st.stop()

nav_df = db.get_nav_history_df(ticker)
holdings_df = db.get_holdings_df(ticker)
summary = db.get_fund_summary(ticker)

col_refresh, col_note = st.columns([1, 4])
with col_refresh:
    refresh_clicked = st.button("Refresh holdings & price history")
with col_note:
    if summary:
        st.caption(f"Holdings as of: {summary['last_updated']}")

if refresh_clicked or (nav_df.empty and holdings_df.empty):
    with st.spinner(f"Fetching {ticker} holdings and price history from JPM..."):
        refresh_fund_detail(ticker)
    nav_df = db.get_nav_history_df(ticker)
    holdings_df = db.get_holdings_df(ticker)
    summary = db.get_fund_summary(ticker)

if summary:
    header_cols = st.columns(4)
    header_cols[0].metric("Total Holdings", summary["total_holdings"])
    aum = summary["total_assets"]
    header_cols[1].metric("Total Assets (approx.)", f"${aum:,.0f}" if aum else "N/A")
    expense_ratio = fund_row.get("expense_ratio")
    header_cols[2].metric(
        "Expense Ratio",
        f"{expense_ratio:.2%}" if expense_ratio == expense_ratio and expense_ratio not in (None, "") else "N/A",
    )
    if not nav_df.empty:
        latest = nav_df.iloc[-1]
        header_cols[3].metric("Latest NAV", f"${latest['nav']:.2f}", help=f"As of {latest['date'].date()}")
    st.caption(
        "Total Assets is an approximation: sum of disclosed holdings' market value. "
        "Funds using an options overlay or holding cash/derivatives will undercount "
        "official AUM by that amount."
    )

# ---- Performance chart, switchable by date range ----
st.subheader("Performance")
if nav_df.empty:
    st.info("No price history cached for this fund yet.")
else:
    min_date = nav_df["date"].min().date()
    max_date = nav_df["date"].max().date()

    RANGE_OPTIONS = {
        "1M": 30,
        "3M": 91,
        "6M": 182,
        "YTD": None,
        "1Y": 365,
        "3Y": 365 * 3,
        "5Y": 365 * 5,
        "Max": None,
    }
    choice = st.radio("Range", list(RANGE_OPTIONS.keys()), index=4, horizontal=True, key="perf_range")

    if choice == "Max":
        range_start = min_date
    elif choice == "YTD":
        range_start = date(max_date.year, 1, 1)
    else:
        range_start = max(min_date, max_date - timedelta(days=RANGE_OPTIONS[choice]))
    range_end = max_date

    with st.expander("Custom date range"):
        custom_range = st.date_input(
            "Select a range",
            value=(range_start, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        if isinstance(custom_range, tuple) and len(custom_range) == 2:
            range_start, range_end = custom_range

    plot_df = nav_df[(nav_df["date"].dt.date >= range_start) & (nav_df["date"].dt.date <= range_end)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=plot_df["date"], y=plot_df["nav"], name="NAV", mode="lines"))
    fig.add_trace(go.Scatter(x=plot_df["date"], y=plot_df["market_price"], name="Market Price", mode="lines"))
    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis_title="Price ($)",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"Source: JPM historical NAV export. Data through {max_date}.")

# ---- Sector allocation ----
if summary and summary["sector_allocation"]:
    st.subheader("Sector Allocation")
    sector_alloc = summary["sector_allocation"]
    import plotly.express as px

    pie = px.pie(names=list(sector_alloc.keys()), values=list(sector_alloc.values()), hole=0.4)
    pie.update_layout(margin=dict(t=10, b=10, l=10, r=10))
    st.plotly_chart(pie, use_container_width=True)
    if sum(sector_alloc.values()) < 99:
        st.caption(
            f"Sectors sum to {sum(sector_alloc.values()):.1f}% of net assets — the "
            "remainder is cash, derivatives, or other non-equity positions not "
            "classified by GICS sector."
        )

# ---- Holdings table ----
st.subheader("Holdings")
if holdings_df.empty:
    st.info("No holdings data cached for this fund yet.")
else:
    display_columns = {
        "symbol": "Symbol",
        "description": "Description",
        "sector": "Sector",
        "sub_industry": "Sub-Industry",
        "pct_net_assets": "% of Net Assets",
        "shares_held": "Shares Held",
        "market_value": "Market Value",
    }
    table = holdings_df[list(display_columns.keys())].rename(columns=display_columns)
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "% of Net Assets": st.column_config.NumberColumn(format="%.2f%%"),
            "Market Value": st.column_config.NumberColumn(format="$%d"),
        },
    )
    st.caption(f"{len(table)} holdings, as of {holdings_df['last_updated'].iloc[0]}")

fact_sheet_url = fund_row.get("fact_sheet_url")
if isinstance(fact_sheet_url, str) and fact_sheet_url:
    st.link_button("Open official fact sheet (PDF)", fact_sheet_url)
