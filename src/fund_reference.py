"""Loads the static fund lineup / expense-ratio / fact-sheet reference table.

This table is intentionally NOT fetched live — per the project's data
architecture, fund lineup and expense ratio come from JPM's own public
pages and are maintained by hand since they change infrequently.
`expense_ratio` and `fact_sheet_url` ship blank and must be filled in from
each fund's official JPM product page before this data reaches a viewer.
"""
import pandas as pd

from src.config import FUND_REFERENCE_CSV

ASSET_CLASS_ORDER = [
    "U.S. Equity",
    "International Equity",
    "Fixed Income Taxable",
    "Fixed Income Tax-Free",
    "Multi-Asset",
    "Alternatives",
]


def load_fund_reference() -> pd.DataFrame:
    df = pd.read_csv(FUND_REFERENCE_CSV)
    df["asset_class"] = pd.Categorical(df["asset_class"], categories=ASSET_CLASS_ORDER, ordered=True)
    return df.sort_values(["asset_class", "fund_name"]).reset_index(drop=True)
