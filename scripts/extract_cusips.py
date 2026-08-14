"""One-off: extracts each fund's CUSIP from its already-known fact sheet
PDF (data/fund_reference.csv's fact_sheet_url) and writes it into a new
`cusip` column. CUSIP is required to call JPM's FundsMarketingHandler
endpoints (holdings/historical NAV) — those take cusip, not ticker.

Run from the project root: python -m scripts.extract_cusips
"""
import re
import time

import pandas as pd
import requests
from pypdf import PdfReader
from io import BytesIO

from src.config import FUND_REFERENCE_CSV

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
CUSIP_RE = re.compile(r"CUSIP\s*\n?\s*([A-Z0-9]{8,9})")


def extract_cusip(pdf_url: str) -> str | None:
    resp = requests.get(pdf_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    reader = PdfReader(BytesIO(resp.content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    m = CUSIP_RE.search(text)
    return m.group(1) if m else None


def main():
    df = pd.read_csv(FUND_REFERENCE_CSV)
    if "cusip" not in df.columns:
        df["cusip"] = None

    for i, row in df.iterrows():
        url = row.get("fact_sheet_url")
        if not isinstance(url, str) or not url:
            print(f"{row['ticker']}: no fact sheet URL, skipping")
            continue
        try:
            cusip = extract_cusip(url)
            df.at[i, "cusip"] = cusip
            print(f"{row['ticker']}: {cusip or 'NOT FOUND'}")
        except Exception as exc:
            print(f"{row['ticker']}: FAILED ({exc})")
        time.sleep(0.2)

    df.to_csv(FUND_REFERENCE_CSV, index=False)
    print(f"\nDone. {df['cusip'].notna().sum()}/{len(df)} funds have a CUSIP.")


if __name__ == "__main__":
    main()
