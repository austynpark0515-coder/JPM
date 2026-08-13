"""ETF Detail / Holdings Drill-Down — one fund's constituents, modeled on a
brokerage holdings screen but adapted to fund-level (not personal-account)
data: no Quantity/Cost Basis/Gain-Loss/Reinvest fields.

Deferred to v2: Finnhub's constituent-holdings/sector endpoints sit behind
a paid plan outside this project's free-tier scope, so this page has no
live data source yet. It's kept in place (UI + cache plumbing already
built via scripts/refresh_holdings.py) for whenever a holdings data
source — paid Finnhub, or an alternate free one — gets picked.
"""
import plotly.express as px
import streamlit as st

from src import db
from src.fund_reference import load_fund_reference

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

st.warning(
    "Holdings drill-down is a **v2 roadmap item**: Finnhub's constituent-holdings "
    "and sector-exposure data require a paid plan not included in this project's "
    "free-tier v1 scope. The layout below is wired up and ready — it just has no "
    "data source yet."
)

summary = db.get_fund_summary(ticker)
holdings_df = db.get_holdings_df(ticker)

if summary is None:
    st.info("No cached holdings for this fund yet.")
else:
    header_cols = st.columns(4)
    header_cols[0].metric("Total Holdings", summary["total_holdings"])
    aum = summary["total_assets"]
    header_cols[1].metric("Total Assets (AUM)", f"${aum:,.0f}" if aum else "N/A")
    expense_ratio = fund_row.get("expense_ratio")
    header_cols[2].metric(
        "Expense Ratio",
        f"{expense_ratio:.2%}" if expense_ratio == expense_ratio and expense_ratio not in (None, "") else "N/A",
    )
    header_cols[3].metric("Holdings Last Updated", summary["last_updated"])

    sector_alloc = summary["sector_allocation"]
    if sector_alloc:
        st.subheader("Sector Allocation")
        fig = px.pie(names=list(sector_alloc.keys()), values=list(sector_alloc.values()), hole=0.4)
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)

st.subheader("Holdings")
if holdings_df.empty:
    st.info("No holdings data cached for this fund yet.")
else:
    display_columns = {
        "symbol": "Symbol",
        "description": "Description",
        "sub_industry": "Sub-Industry",
        "pct_net_assets": "% of Net Assets",
        "shares_held": "Shares Held",
        "market_value": "Market Value",
        "day_change_pct": "Day Chg %",
        "five_day_change_pct": "5-Day Chg %",
        "one_month_change_pct": "1-Mo Chg %",
        "ytd_change_pct": "YTD Chg %",
        "one_year_change_pct": "1-Yr Chg %",
    }
    table = holdings_df[list(display_columns.keys())].rename(columns=display_columns)
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.caption(f"Last updated: {holdings_df['last_updated'].iloc[0]}")

fact_sheet_url = fund_row.get("fact_sheet_url")
if isinstance(fact_sheet_url, str) and fact_sheet_url:
    st.link_button("Open official fact sheet (PDF)", fact_sheet_url)
