from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st
from supabase import create_client


ASSETS: dict[str, dict[str, Any]] = {
    "DCAM.PA": {"nom": "Amundi PEA MSCI World", "poche": "Socle Zen", "cible": 0.20},
    "PSP5.PA": {"nom": "Amundi PEA S&P 500", "poche": "Socle Zen", "cible": 0.15},
    "PUST.PA": {"nom": "Amundi PEA Nasdaq-100", "poche": "Socle Zen", "cible": 0.10},
    "PCEU.PA": {"nom": "Amundi PEA MSCI Europe", "poche": "Socle Zen", "cible": 0.05},
    "GUARD.PA": {"nom": "BNP Défense Europe", "poche": "Momentum", "cible": 0.10},
    "SU.PA": {"nom": "Schneider Electric", "poche": "Momentum", "cible": 0.05},
    "AI.PA": {"nom": "Air Liquide", "poche": "Momentum", "cible": 0.03},
    "TTE.PA": {"nom": "TotalEnergies", "poche": "Momentum", "cible": 0.02},
    "AM.PA": {"nom": "Dassault Aviation", "poche": "Momentum", "cible": 0.05},
    "HO.PA": {"nom": "Thales", "poche": "Momentum", "cible": 0.05},
    "STMPA.PA": {"nom": "STMicroelectronics", "poche": "Momentum", "cible": 0.05},
    "SAN.PA": {"nom": "Sanofi", "poche": "Satellite", "cible": 0.05},
    "PAEEM.PA": {"nom": "Amundi PEA Émergents", "poche": "Satellite", "cible": 0.10},
}


def _secret(*names: str, default: str = "") -> str:
    """Lecture robuste des secrets Streamlit ou variables d'environnement."""
    for name in names:
        value = os.getenv(name)
        if value:
            return str(value).strip()

    try:
        supabase_block = st.secrets.get("supabase", {})
        for name in names:
            if name.lower() in supabase_block:
                return str(supabase_block[name.lower()]).strip()
            if name in supabase_block:
                return str(supabase_block[name]).strip()
    except Exception:
        pass

    try:
        for name in names:
            if name in st.secrets:
                return str(st.secrets[name]).strip()
    except Exception:
        pass

    return default


def profile_id() -> str:
    return _secret("SUPABASE_PROFILE_ID", "profile_id", default="william")


@st.cache_resource(show_spinner=False)
def client():
    url = _secret("SUPABASE_URL", "url")
    key = _secret("SUPABASE_SECRET_KEY", "secret_key", "SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise RuntimeError(
            "Secrets Supabase manquants. Vérifie SUPABASE_URL et SUPABASE_SECRET_KEY."
        )

    return create_client(url, key)


def _pick_column(df: pd.DataFrame, names: list[str]) -> str | None:
    lower = {str(col).lower(): col for col in df.columns}
    for name in names:
        if name.lower() in lower:
            return lower[name.lower()]
    for col in df.columns:
        low = str(col).lower()
        if any(name.lower() in low for name in names):
            return col
    return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


@st.cache_data(ttl=60, show_spinner=False)
def load_settings() -> dict[str, float]:
    rows: list[dict[str, Any]] = []
    try:
        response = (
            client()
            .table("az_settings")
            .select("*")
            .eq("profile_id", profile_id())
            .limit(1)
            .execute()
        )
        rows = getattr(response, "data", None) or []
    except Exception:
        rows = []

    row = rows[0] if rows else {}

    cash = _safe_float(
        row.get("virtual_cash", row.get("cash", row.get("liquidites", 0.0))),
        0.0,
    )
    capital_reference = _safe_float(
        row.get("capital_reference", row.get("capital", row.get("initial_capital", 0.0))),
        0.0,
    )
    monthly_contribution = _safe_float(
        row.get("monthly_contribution", row.get("versement_mensuel", 1000.0)),
        1000.0,
    )

    return {
        "cash": cash,
        "capital_reference": capital_reference,
        "monthly_contribution": monthly_contribution,
    }


@st.cache_data(ttl=60, show_spinner=False)
def load_positions() -> pd.DataFrame:
    try:
        response = (
            client()
            .table("az_positions")
            .select("*")
            .eq("profile_id", profile_id())
            .execute()
        )
        rows = getattr(response, "data", None) or []
    except Exception as exc:
        raise RuntimeError(f"Impossible de lire az_positions : {exc}") from exc

    if not rows:
        return pd.DataFrame(columns=["Ticker", "Quantité", "PRU"])

    raw = pd.DataFrame(rows)

    ticker_col = _pick_column(raw, ["ticker", "symbol", "actif"])
    qty_col = _pick_column(raw, ["quantity", "quantite", "quantité", "qty", "nombre"])
    pru_col = _pick_column(raw, ["pru", "avg_price", "average_price", "prix_moyen", "cost"])

    if ticker_col is None:
        raise RuntimeError("Colonne ticker introuvable dans az_positions.")

    out = pd.DataFrame()
    out["Ticker"] = raw[ticker_col].astype(str).str.upper().str.strip()
    out["Quantité"] = pd.to_numeric(raw[qty_col], errors="coerce").fillna(0.0) if qty_col else 0.0
    out["PRU"] = pd.to_numeric(raw[pru_col], errors="coerce").fillna(0.0) if pru_col else 0.0

    out = out.groupby("Ticker", as_index=False).agg({"Quantité": "sum", "PRU": "last"})
    return out


@st.cache_data(ttl=60, show_spinner=False)
def load_market_prices() -> pd.DataFrame:
    try:
        response = client().table("az_market_prices").select("*").execute()
        rows = getattr(response, "data", None) or []
    except Exception as exc:
        raise RuntimeError(f"Impossible de lire az_market_prices : {exc}") from exc

    if not rows:
        return pd.DataFrame(columns=["Ticker", "Cours", "Source", "Updated"])

    raw = pd.DataFrame(rows)

    ticker_col = _pick_column(raw, ["ticker", "symbol"])
    price_col = _pick_column(raw, ["price", "last_price", "cours", "close"])
    updated_col = _pick_column(raw, ["updated_at", "date", "timestamp"])

    if ticker_col is None or price_col is None:
        return pd.DataFrame(columns=["Ticker", "Cours", "Source", "Updated"])

    out = pd.DataFrame()
    out["Ticker"] = raw[ticker_col].astype(str).str.upper().str.strip()
    out["Cours"] = pd.to_numeric(raw[price_col], errors="coerce")
    out["Source"] = "Supabase az_market_prices"
    out["Updated"] = raw[updated_col].astype(str) if updated_col else ""

    out = out.dropna(subset=["Ticker", "Cours"])
    if out.empty:
        return pd.DataFrame(columns=["Ticker", "Cours", "Source", "Updated"])

    out = out.sort_values("Updated")
    out = out.groupby("Ticker", as_index=False).last()
    return out


def build_secure_portfolio() -> tuple[pd.DataFrame, dict[str, float], list[str]]:
    settings = load_settings()
    positions = load_positions()
    prices = load_market_prices()

    missing_prices: list[str] = []
    rows: list[dict[str, Any]] = []

    for ticker, meta in ASSETS.items():
        pos = positions.loc[positions["Ticker"] == ticker]
        qty = _safe_float(pos["Quantité"].sum()) if not pos.empty else 0.0
        pru = _safe_float(pos["PRU"].iloc[-1]) if not pos.empty else 0.0

        price_row = prices.loc[prices["Ticker"] == ticker]
        if not price_row.empty:
            price = _safe_float(price_row["Cours"].iloc[-1])
            source = "Cours Supabase"
        else:
            price = pru
            source = "PRU provisoire"
            if qty > 0:
                missing_prices.append(ticker)

        value = qty * price
        cost = qty * pru
        gain = value - cost
        gain_pct = (gain / cost) if cost > 0 else 0.0

        rows.append(
            {
                "Ticker": ticker,
                "Nom": meta["nom"],
                "Poche": meta["poche"],
                "Cible": meta["cible"],
                "Quantité": qty,
                "PRU": pru,
                "Cours": price,
                "Source cours": source,
                "Valeur": value,
                "+/- €": gain,
                "+/- %": gain_pct,
            }
        )

    df = pd.DataFrame(rows)
    total_positions = _safe_float(df["Valeur"].sum())
    total_value = total_positions + settings["cash"]

    if total_value > 0:
        df["Poids actuel"] = df["Valeur"] / total_value
    else:
        df["Poids actuel"] = 0.0

    df["Écart cible"] = df["Cible"] - df["Poids actuel"]

    totals = {
        "cash": settings["cash"],
        "capital_reference": settings["capital_reference"],
        "monthly_contribution": settings["monthly_contribution"],
        "positions_value": total_positions,
        "total_value": total_value,
    }

    return df, totals, missing_prices
