from __future__ import annotations

from typing import Any
import pandas as pd
import yfinance as yf

DATE_COLUMNS = ["snapshot_date", "date", "created_at", "updated_at", "timestamp"]
VALUE_COLUMNS = ["total_value", "portfolio_value", "total_portfolio_value", "value", "valeur_totale", "valeur_portefeuille"]


def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower_map = {str(col).lower(): col for col in df.columns}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


def normalize_snapshots(raw_rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not raw_rows:
        return pd.DataFrame(columns=["Date", "Portefeuille"])
    df = pd.DataFrame(raw_rows)
    if df.empty:
        return pd.DataFrame(columns=["Date", "Portefeuille"])

    date_col = _first_existing_column(df, DATE_COLUMNS)
    value_col = _first_existing_column(df, VALUE_COLUMNS)

    if date_col is None or value_col is None:
        return pd.DataFrame(columns=["Date", "Portefeuille"])

    out = pd.DataFrame()
    out["Date"] = pd.to_datetime(df[date_col], errors="coerce").dt.tz_localize(None).dt.date
    out["Portefeuille"] = pd.to_numeric(df[value_col], errors="coerce")
    out = out.dropna(subset=["Date", "Portefeuille"])
    out = out.sort_values("Date")
    out = out.groupby("Date", as_index=False)["Portefeuille"].last()
    return out


def load_sp500_normalized(start_date, end_date, start_value: float, ticker: str = "^GSPC") -> pd.DataFrame:
    if start_value <= 0:
        return pd.DataFrame(columns=["Date", "S&P 500 normalisé"])

    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date) + pd.Timedelta(days=1)

    data = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=True,
        progress=False,
    )

    if data is None or data.empty:
        return pd.DataFrame(columns=["Date", "S&P 500 normalisé"])

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    close = pd.to_numeric(data["Close"], errors="coerce").dropna()
    if close.empty:
        return pd.DataFrame(columns=["Date", "S&P 500 normalisé"])

    first = float(close.iloc[0])
    if first <= 0:
        return pd.DataFrame(columns=["Date", "S&P 500 normalisé"])

    out = pd.DataFrame()
    out["Date"] = close.index.tz_localize(None).date
    out["S&P 500 normalisé"] = close.values / first * float(start_value)
    return out


def build_portfolio_vs_sp500(raw_rows: list[dict[str, Any]]) -> pd.DataFrame:
    portfolio = normalize_snapshots(raw_rows)
    if portfolio.empty or len(portfolio) < 2:
        return pd.DataFrame(columns=["Date", "Portefeuille", "S&P 500 normalisé"])

    start_date = portfolio["Date"].min()
    end_date = portfolio["Date"].max()
    start_value = float(portfolio["Portefeuille"].iloc[0])

    sp500 = load_sp500_normalized(start_date, end_date, start_value)
    if sp500.empty:
        portfolio["S&P 500 normalisé"] = pd.NA
        return portfolio

    chart = pd.merge(portfolio, sp500, on="Date", how="left")
    chart["S&P 500 normalisé"] = chart["S&P 500 normalisé"].ffill().bfill()
    return chart
