from __future__ import annotations

from typing import Any

import pandas as pd
import yfinance as yf


def get_market_snapshot(tickers: list[str], period: str = "2y") -> pd.DataFrame:
    """Télécharge cours, MM200 et momentum 6 mois pour une liste de tickers."""
    rows: list[dict[str, Any]] = []

    for ticker in tickers:
        row: dict[str, Any] = {
            "Ticker": ticker,
            "Cours (€)": pd.NA,
            "Date du cours": pd.NaT,
            "MM200 (€)": pd.NA,
            "Momentum 6M (%)": pd.NA,
            "Statut données": "Indisponible",
        }

        try:
            history = yf.Ticker(ticker).history(
                period=period,
                interval="1d",
                auto_adjust=False,
                repair=True,
                actions=False,
                timeout=15,
            )

            if history.empty or "Close" not in history.columns:
                rows.append(row)
                continue

            close = history["Close"].dropna()
            if close.empty:
                rows.append(row)
                continue

            latest_price = float(close.iloc[-1])
            latest_date = pd.Timestamp(close.index[-1]).tz_localize(None)

            mm200 = float(close.tail(200).mean()) if len(close) >= 200 else pd.NA
            momentum_6m = (
                (latest_price / float(close.iloc[-126]) - 1.0) * 100.0
                if len(close) >= 127
                else pd.NA
            )

            row.update(
                {
                    "Cours (€)": latest_price,
                    "Date du cours": latest_date,
                    "MM200 (€)": mm200,
                    "Momentum 6M (%)": momentum_6m,
                    "Statut données": "OK",
                }
            )

        except Exception as exc:
            row["Statut données"] = f"Erreur: {type(exc).__name__}"

        rows.append(row)

    return pd.DataFrame(rows)


def mm200_signal(price: object, mm200: object) -> str:
    """Retourne un signal simple selon la position du cours face à la MM200."""
    if pd.isna(price) or pd.isna(mm200):
        return "⚪ Données insuffisantes"

    price_value = float(price)
    mm200_value = float(mm200)
    distance = (price_value / mm200_value - 1.0) * 100.0

    if distance >= 3.0:
        return "🟢 Au-dessus MM200"
    if distance >= 0.0:
        return "🟠 Proche MM200"
    return "🔴 Sous MM200"
