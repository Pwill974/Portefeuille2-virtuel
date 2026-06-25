from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf
from supabase import create_client


TICKERS = [
    "DCAM.PA",
    "PSP5.PA",
    "PUST.PA",
    "PCEU.PA",
    "GUARD.PA",
    "SU.PA",
    "AI.PA",
    "TTE.PA",
    "AM.PA",
    "HO.PA",
    "STMPA.PA",
    "SAN.PA",
    "PAEEM.PA",
]

REUNION_TZ = ZoneInfo("Indian/Reunion")


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Secret GitHub manquant : {name}"
        )
    return value


def response_rows(response) -> list[dict]:
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


def return_at(close: pd.Series, sessions: int) -> float | None:
    if len(close) <= sessions:
        return None
    base = float(close.iloc[-sessions - 1])
    if base == 0:
        return None
    return (float(close.iloc[-1]) / base - 1.0) * 100.0


def scale(value: float | None, low: float, high: float) -> float:
    if value is None or pd.isna(value):
        return 0.0
    return float(
        np.clip(
            (value - low) / (high - low) * 100.0,
            0.0,
            100.0,
        )
    )


def alpha_score(
    m3: float | None,
    m6: float | None,
    m12: float | None,
    distance: float | None,
    volatility: float | None,
) -> float:
    trend = 0.0
    if distance is not None:
        if distance >= 3:
            trend = 100.0
        elif distance >= 0:
            trend = 65.0
        elif distance >= -3:
            trend = 25.0

    volatility_score = (
        float(
            np.clip(
                110.0 - max(float(volatility), 0.0) * 2.5,
                0.0,
                100.0,
            )
        )
        if volatility is not None
        else 0.0
    )

    score = (
        0.20 * scale(m3, -15.0, 30.0)
        + 0.30 * scale(m6, -25.0, 50.0)
        + 0.30 * scale(m12, -35.0, 80.0)
        + 0.15 * trend
        + 0.05 * volatility_score
    )
    return round(float(score), 0)


def signal(score: float, distance: float | None) -> str:
    if distance is None:
        return "⚪ Données insuffisantes"
    if distance < 0:
        return "🔴 Sous MM200"
    if distance < 3:
        return "🟠 Surveiller"
    if score >= 75:
        return "🟢 Renforcer"
    if score >= 55:
        return "✅ Conserver"
    return "🟠 Surveiller"


def fetch_quote(ticker: str) -> dict | None:
    history = yf.Ticker(ticker).history(
        period="3y",
        interval="1d",
        auto_adjust=False,
        repair=True,
        actions=False,
        timeout=25,
    )
    if history.empty or "Close" not in history.columns:
        return None

    close = history["Close"].dropna().astype(float)
    if close.empty:
        return None

    price = float(close.iloc[-1])
    mm50 = (
        float(close.tail(50).mean())
        if len(close) >= 50
        else None
    )
    mm200 = (
        float(close.tail(200).mean())
        if len(close) >= 200
        else None
    )
    distance = (
        (price / mm200 - 1.0) * 100.0
        if mm200 not in (None, 0)
        else None
    )
    returns = close.pct_change().dropna()
    volatility = (
        float(
            returns.tail(252).std()
            * np.sqrt(252)
            * 100.0
        )
        if len(returns) >= 20
        else None
    )
    m3 = return_at(close, 63)
    m6 = return_at(close, 126)
    m12 = return_at(close, 252)

    last_date = pd.Timestamp(close.index[-1])
    previous_year = close[
        close.index.year < last_date.year
    ]
    ytd = None
    if not previous_year.empty:
        base = float(previous_year.iloc[-1])
        if base:
            ytd = (price / base - 1.0) * 100.0

    score = alpha_score(
        m3,
        m6,
        m12,
        distance,
        volatility,
    )

    if last_date.tzinfo is None:
        quote_date = last_date.tz_localize("UTC")
    else:
        quote_date = last_date.tz_convert("UTC")

    return {
        "price": price,
        "quote_date": quote_date.isoformat(),
        "mm50": mm50,
        "mm200": mm200,
        "distance_mm200": distance,
        "momentum_3m": m3,
        "momentum_6m": m6,
        "momentum_12m": m12,
        "performance_ytd": ytd,
        "volatility_1y": volatility,
        "alpha_zen_score": score,
        "signal": signal(score, distance),
    }


def main() -> None:
    url = required_env("SUPABASE_URL")
    key = required_env("SUPABASE_SECRET_KEY")
    profile_id = os.getenv(
        "SUPABASE_PROFILE_ID",
        "william",
    ).strip() or "william"

    client = create_client(url, key)
    now = datetime.now(timezone.utc).isoformat()

    settings_rows = response_rows(
        client.table("az_settings")
        .select("*")
        .eq("profile_id", profile_id)
        .limit(1)
        .execute()
    )
    position_rows = response_rows(
        client.table("az_positions")
        .select("ticker,quantity,pru")
        .eq("profile_id", profile_id)
        .execute()
    )
    transaction_rows = response_rows(
        client.table("az_transactions")
        .select("fees,realized_gain")
        .eq("profile_id", profile_id)
        .execute()
    )
    saved_price_rows = response_rows(
        client.table("az_market_prices")
        .select("*")
        .eq("profile_id", profile_id)
        .execute()
    )

    settings = settings_rows[0] if settings_rows else {}
    saved_prices = {
        str(row.get("ticker", "")): row
        for row in saved_price_rows
    }

    prices: dict[str, float] = {}
    market_records: list[dict] = []
    latest_quote = None

    for ticker in TICKERS:
        quote = None
        try:
            quote = fetch_quote(ticker)
        except Exception as error:
            print(
                f"{ticker}: Yahoo indisponible : "
                f"{type(error).__name__}"
            )

        if quote is None:
            previous = saved_prices.get(ticker)
            if previous:
                previous_price = float(
                    previous.get("price", 0) or 0
                )
                if previous_price > 0:
                    prices[ticker] = previous_price
            continue

        prices[ticker] = float(quote["price"])
        quote_time = pd.to_datetime(
            quote["quote_date"],
            utc=True,
        )
        if (
            latest_quote is None
            or quote_time > latest_quote
        ):
            latest_quote = quote_time

        market_records.append(
            {
                "profile_id": profile_id,
                "ticker": ticker,
                **quote,
                "updated_at": now,
            }
        )

    if market_records:
        (
            client.table("az_market_prices")
            .upsert(
                market_records,
                on_conflict="profile_id,ticker",
            )
            .execute()
        )

    invested = 0.0
    positions_value = 0.0
    active_lines = 0

    for row in position_rows:
        ticker = str(row.get("ticker", ""))
        quantity = float(
            row.get("quantity", 0) or 0
        )
        pru = float(row.get("pru", 0) or 0)
        price = float(prices.get(ticker, 0.0))

        if quantity > 0:
            active_lines += 1

        invested += quantity * pru
        positions_value += quantity * price

    cash = float(settings.get("cash", 0) or 0)
    capital_reference = float(
        settings.get("capital_reference", 0) or 0
    )
    total_value = positions_value + cash
    unrealized_gain = positions_value - invested
    performance = (
        unrealized_gain / invested * 100.0
        if invested > 0
        else 0.0
    )
    realized_gain = sum(
        float(row.get("realized_gain", 0) or 0)
        for row in transaction_rows
    )
    cumulative_fees = sum(
        float(row.get("fees", 0) or 0)
        for row in transaction_rows
    )
    net_performance = (
        (total_value / capital_reference - 1.0)
        * 100.0
        if capital_reference > 0
        else 0.0
    )

    quote_date_text = (
        latest_quote.isoformat()
        if latest_quote is not None
        else None
    )

    live_record = {
        "profile_id": profile_id,
        "capital_reference": capital_reference,
        "cash": cash,
        "invested": invested,
        "positions_value": positions_value,
        "total_value": total_value,
        "unrealized_gain": unrealized_gain,
        "performance": performance,
        "active_lines": active_lines,
        "quote_date": quote_date_text,
        "updated_at": now,
    }
    (
        client.table("az_live_portfolio")
        .upsert(
            live_record,
            on_conflict="profile_id",
        )
        .execute()
    )

    snapshot_record = {
        "profile_id": profile_id,
        "snapshot_date": datetime.now(
            REUNION_TZ
        ).date().isoformat(),
        "total_value": total_value,
        "positions_value": positions_value,
        "cash": cash,
        "invested": invested,
        "capital_reference": capital_reference,
        "unrealized_gain": unrealized_gain,
        "realized_gain": realized_gain,
        "cumulative_fees": cumulative_fees,
        "net_performance": net_performance,
        "updated_at": now,
    }
    (
        client.table("az_snapshots")
        .upsert(
            snapshot_record,
            on_conflict="profile_id,snapshot_date",
        )
        .execute()
    )

    print(
        "Mise à jour terminée — "
        f"valeur totale : {total_value:.2f} €, "
        f"plus-value latente : {unrealized_gain:.2f} €."
    )


if __name__ == "__main__":
    main()
