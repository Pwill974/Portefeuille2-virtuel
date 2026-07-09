from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="Alpha Zen Pro — Analyse achat actif",
    page_icon="📈",
    layout="wide",
)

from services.auth import require_authentication, show_logout_button
from services.supabase_service import (
    SupabaseSyncError,
    load_cloud_state_into_session,
    supabase_is_configured,
)

REUNION_TZ = ZoneInfo("Indian/Reunion")


ASSETS = {
    "DCAM.PA": {
        "nom": "Amundi PEA MSCI World",
        "isin": "FR001400U5Q4",
        "type": "ETF",
        "poche": "Socle Zen",
        "cible": 0.20,
    },
    "PSP5.PA": {
        "nom": "Amundi PEA S&P 500",
        "isin": "FR0011871128",
        "type": "ETF",
        "poche": "Socle Zen",
        "cible": 0.15,
    },
    "PUST.PA": {
        "nom": "Amundi PEA Nasdaq-100",
        "isin": "FR0011871110",
        "type": "ETF",
        "poche": "Socle Zen",
        "cible": 0.10,
    },
    "PCEU.PA": {
        "nom": "Amundi PEA MSCI Europe",
        "isin": "FR0013412038",
        "type": "ETF",
        "poche": "Socle Zen",
        "cible": 0.05,
    },
    "GUARD.PA": {
        "nom": "BNP Défense Europe",
        "isin": "LU3047998896",
        "type": "ETF",
        "poche": "Momentum",
        "cible": 0.10,
    },
    "SU.PA": {
        "nom": "Schneider Electric",
        "isin": "FR0000121972",
        "type": "Action",
        "poche": "Momentum",
        "cible": 0.05,
    },
    "AI.PA": {
        "nom": "Air Liquide",
        "isin": "FR0000120073",
        "type": "Action",
        "poche": "Momentum",
        "cible": 0.03,
    },
    "TTE.PA": {
        "nom": "TotalEnergies",
        "isin": "FR0000120271",
        "type": "Action",
        "poche": "Momentum",
        "cible": 0.02,
    },
    "AM.PA": {
        "nom": "Dassault Aviation",
        "isin": "FR0014004L86",
        "type": "Action",
        "poche": "Momentum",
        "cible": 0.05,
    },
    "HO.PA": {
        "nom": "Thales",
        "isin": "FR0000121329",
        "type": "Action",
        "poche": "Momentum",
        "cible": 0.05,
    },
    "STMPA.PA": {
        "nom": "STMicroelectronics",
        "isin": "NL0000226223",
        "type": "Action",
        "poche": "Momentum",
        "cible": 0.05,
    },
    "SAN.PA": {
        "nom": "Sanofi",
        "isin": "FR0000120578",
        "type": "Action",
        "poche": "Satellite",
        "cible": 0.05,
    },
    "PAEEM.PA": {
        "nom": "Amundi PEA Émergents",
        "isin": "FR0013412020",
        "type": "ETF",
        "poche": "Satellite",
        "cible": 0.10,
    },
}


require_authentication()
show_logout_button()


def euro(value: float) -> str:
    return f"{float(value):,.2f} €".replace(",", " ").replace(".", ",")


def pct(value: float) -> str:
    return f"{float(value) * 100:.2f} %".replace(".", ",")


def safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def normalize_positions(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Ticker", "Quantité", "PRU (€)"])

    data = df.copy()

    ticker_col = None
    qty_col = None
    pru_col = None

    for col in data.columns:
        low = str(col).lower()
        if ticker_col is None and "ticker" in low:
            ticker_col = col
        if qty_col is None and ("quant" in low or low in {"qty", "quantity"}):
            qty_col = col
        if pru_col is None and ("pru" in low or "prix" in low or "cost" in low):
            pru_col = col

    if ticker_col is None:
        data["Ticker"] = ""
        ticker_col = "Ticker"
    if qty_col is None:
        data["Quantité"] = 0.0
        qty_col = "Quantité"
    if pru_col is None:
        data["PRU (€)"] = 0.0
        pru_col = "PRU (€)"

    out = pd.DataFrame(
        {
            "Ticker": data[ticker_col].astype(str).str.upper().str.strip(),
            "Quantité": pd.to_numeric(data[qty_col], errors="coerce").fillna(0.0),
            "PRU (€)": pd.to_numeric(data[pru_col], errors="coerce").fillna(0.0),
        }
    )
    return out


@st.cache_data(ttl=60 * 20, show_spinner=False)
def load_history(ticker: str) -> pd.DataFrame:
    data = yf.download(
        ticker,
        period="2y",
        interval="1d",
        auto_adjust=True,
        progress=False,
    )

    if data is None or data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    close = data["Close"].dropna()
    hist = pd.DataFrame(index=close.index)
    hist["Prix"] = close
    hist["MM50"] = close.rolling(50).mean()
    hist["MM200"] = close.rolling(200).mean()
    hist["Plus haut 20j"] = close.rolling(20).max()
    hist["Plus bas 20j"] = close.rolling(20).min()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    hist["RSI14"] = 100 - (100 / (1 + rs))

    hist["Momentum 3M"] = close / close.shift(63) - 1
    hist["Momentum 6M"] = close / close.shift(126) - 1
    hist["Momentum 12M"] = close / close.shift(252) - 1

    return hist.dropna(how="all")


@st.cache_data(ttl=60 * 20, show_spinner=False)
def last_price(ticker: str) -> float:
    hist = load_history(ticker)
    if hist.empty:
        return 0.0
    return safe_float(hist["Prix"].dropna().iloc[-1], 0.0)


def price_map() -> dict[str, float]:
    prices: dict[str, float] = {}
    for ticker in ASSETS:
        prices[ticker] = last_price(ticker)
    return prices


def portfolio_values(positions: pd.DataFrame, prices: dict[str, float]) -> pd.DataFrame:
    rows = []
    for ticker, meta in ASSETS.items():
        qty = safe_float(
            positions.loc[positions["Ticker"] == ticker, "Quantité"].sum(),
            0.0,
        )
        pru = 0.0
        if qty > 0:
            match = positions.loc[positions["Ticker"] == ticker, "PRU (€)"]
            pru = safe_float(match.iloc[-1], 0.0) if not match.empty else 0.0
        price = safe_float(prices.get(ticker, 0.0), 0.0)
        value = qty * price
        rows.append(
            {
                "Ticker": ticker,
                "Nom": meta["nom"],
                "Cible": meta["cible"],
                "Quantité": qty,
                "PRU": pru,
                "Prix": price,
                "Valeur": value,
            }
        )
    return pd.DataFrame(rows)


def trend_signal(hist: pd.DataFrame) -> tuple[str, str, int]:
    if hist.empty or "Prix" not in hist:
        return "Données indisponibles", "Attendre", 0

    last = hist.dropna(subset=["Prix"]).iloc[-1]

    price = safe_float(last.get("Prix"))
    mm50 = safe_float(last.get("MM50"))
    mm200 = safe_float(last.get("MM200"))
    rsi = safe_float(last.get("RSI14"))
    mom3 = safe_float(last.get("Momentum 3M"))
    mom6 = safe_float(last.get("Momentum 6M"))
    mom12 = safe_float(last.get("Momentum 12M"))

    score = 0
    reasons = []

    if price > mm200 > 0:
        score += 2
        reasons.append("prix au-dessus de la MM200")
    else:
        reasons.append("prix sous la MM200")

    if price > mm50 > 0:
        score += 1
        reasons.append("prix au-dessus de la MM50")
    else:
        reasons.append("prix sous la MM50")

    if mom3 > 0:
        score += 1
        reasons.append("momentum 3 mois positif")
    else:
        reasons.append("momentum 3 mois négatif")

    if mom6 > 0:
        score += 1
        reasons.append("momentum 6 mois positif")
    else:
        reasons.append("momentum 6 mois négatif")

    if mom12 > 0:
        score += 1
        reasons.append("momentum 12 mois positif")
    else:
        reasons.append("momentum 12 mois négatif")

    if 35 <= rsi <= 70:
        score += 1
        reasons.append("RSI correct")
    elif rsi > 70:
        reasons.append("RSI élevé, risque de surachat")
    elif rsi > 0:
        reasons.append("RSI faible")

    if score >= 6:
        decision = "Achat favorable"
    elif score >= 4:
        decision = "Achat possible mais prudent"
    else:
        decision = "Attendre"

    return " ; ".join(reasons), decision, score


def recommendation(
    selected: str,
    positions: pd.DataFrame,
    prices: dict[str, float],
    cash: float,
) -> dict:
    values = portfolio_values(positions, prices)
    total_positions = float(values["Valeur"].sum())
    total_value = total_positions + float(cash)

    row = values.loc[values["Ticker"] == selected].iloc[0]
    target_weight = safe_float(row["Cible"], 0.0)
    current_value = safe_float(row["Valeur"], 0.0)
    price = safe_float(row["Prix"], 0.0)

    target_value = total_value * target_weight
    missing_to_target = max(0.0, target_value - current_value)
    raw_buy_amount = min(float(cash), missing_to_target)

    if price > 0:
        quantity = math.floor(raw_buy_amount / price)
        real_buy_amount = quantity * price
    else:
        quantity = 0
        real_buy_amount = 0.0

    current_weight = current_value / total_value if total_value > 0 else 0.0

    return {
        "total_value": total_value,
        "cash": float(cash),
        "target_weight": target_weight,
        "current_weight": current_weight,
        "current_value": current_value,
        "target_value": target_value,
        "missing_to_target": missing_to_target,
        "price": price,
        "quantity": quantity,
        "buy_amount": real_buy_amount,
    }


st.title("📈 Analyse achat par actif")
st.caption(
    "Sélectionne un actif pour voir son graphique, ses indicateurs et une proposition "
    "de montant à acheter selon la tendance et l'écart à la cible."
)

if supabase_is_configured():
    try:
        load_cloud_state_into_session(force=True)
    except Exception as error:
        st.warning(f"Chargement cloud incomplet : {error}")

positions = normalize_positions(st.session_state.get("virtual_positions"))
cash = safe_float(st.session_state.get("virtual_cash", 0.0), 0.0)

asset_labels = [
    f"{ticker} — {meta['nom']} — cible {meta['cible']*100:.0f}%"
    for ticker, meta in ASSETS.items()
]
label_to_ticker = {
    f"{ticker} — {meta['nom']} — cible {meta['cible']*100:.0f}%": ticker
    for ticker, meta in ASSETS.items()
}

selected_label = st.selectbox("Actif à analyser", asset_labels)
selected = label_to_ticker[selected_label]
meta = ASSETS[selected]

with st.spinner("Chargement des données de marché..."):
    hist = load_history(selected)
    prices = price_map()

rec = recommendation(selected, positions, prices, cash)
reasons, tech_decision, score = trend_signal(hist)

st.subheader(f"{selected} — {meta['nom']}")

top = st.columns(5)
top[0].metric("Cours actuel", euro(rec["price"]))
top[1].metric("Cible portefeuille", pct(rec["target_weight"]))
top[2].metric("Poids actuel", pct(rec["current_weight"]))
top[3].metric("Liquidités", euro(rec["cash"]))
top[4].metric("Score tendance", f"{score}/7")

st.divider()

col_graph, col_advice = st.columns([2, 1])

with col_graph:
    st.markdown("### Graphique avec indicateurs")
    if hist.empty:
        st.error("Impossible de charger l'historique de cet actif.")
    else:
        chart_data = hist[["Prix", "MM50", "MM200"]].dropna(how="all")
        st.line_chart(chart_data, use_container_width=True)

        st.markdown("### RSI 14")
        st.line_chart(hist[["RSI14"]].dropna(), use_container_width=True)

with col_advice:
    st.markdown("### Décision")

    allocation_ok = rec["buy_amount"] > 0 and rec["quantity"] > 0

    if tech_decision == "Achat favorable" and allocation_ok:
        st.success("✅ Achat possible")
    elif tech_decision == "Achat possible mais prudent" and allocation_ok:
        st.warning("🟠 Achat possible mais prudent")
    elif not allocation_ok:
        st.info("ℹ️ Pas d'achat nécessaire selon la cible")
    else:
        st.error("⛔ Attendre")

    st.write(f"**Signal technique :** {tech_decision}")
    st.write(f"**Analyse :** {reasons}")

    st.markdown("### Combien acheter ?")

    st.write(f"Valeur actuelle sur cet actif : **{euro(rec['current_value'])}**")
    st.write(f"Valeur cible théorique : **{euro(rec['target_value'])}**")
    st.write(f"Manque pour atteindre la cible : **{euro(rec['missing_to_target'])}**")

    if rec["quantity"] > 0:
        st.success(
            f"Proposition : acheter **{rec['quantity']} titre(s)** "
            f"pour environ **{euro(rec['buy_amount'])}**."
        )
    else:
        if rec["cash"] <= 0:
            st.warning("Aucune liquidité disponible. Ajoute d'abord ton versement mensuel.")
        elif rec["price"] <= 0:
            st.warning("Cours indisponible, impossible de calculer la quantité.")
        else:
            st.info(
                "Aucun achat proposé : l'actif est déjà proche ou au-dessus "
                "de sa pondération cible, ou le cash disponible est insuffisant "
                "pour acheter 1 titre entier."
            )

st.divider()

st.subheader("Résumé des indicateurs")

if hist.empty:
    st.info("Aucun indicateur disponible.")
else:
    last = hist.dropna(subset=["Prix"]).iloc[-1]
    indicators = pd.DataFrame(
        [
            {"Indicateur": "Prix", "Valeur": euro(safe_float(last.get("Prix")))},
            {"Indicateur": "MM50", "Valeur": euro(safe_float(last.get("MM50")))},
            {"Indicateur": "MM200", "Valeur": euro(safe_float(last.get("MM200")))},
            {"Indicateur": "RSI14", "Valeur": f"{safe_float(last.get('RSI14')):.2f}".replace(".", ",")},
            {"Indicateur": "Momentum 3 mois", "Valeur": pct(safe_float(last.get("Momentum 3M")))},
            {"Indicateur": "Momentum 6 mois", "Valeur": pct(safe_float(last.get("Momentum 6M")))},
            {"Indicateur": "Momentum 12 mois", "Valeur": pct(safe_float(last.get("Momentum 12M")))},
        ]
    )
    st.dataframe(indicators, hide_index=True, use_container_width=True)

st.subheader("Tous les actifs — priorité d'achat")

all_values = portfolio_values(positions, prices)
all_values["Poids actuel"] = all_values["Valeur"] / rec["total_value"] if rec["total_value"] > 0 else 0.0
all_values["Valeur cible"] = all_values["Cible"] * rec["total_value"]
all_values["Manque cible"] = (all_values["Valeur cible"] - all_values["Valeur"]).clip(lower=0.0)

display = all_values.sort_values("Manque cible", ascending=False).copy()
display["Cible"] = display["Cible"] * 100
display["Poids actuel"] = display["Poids actuel"] * 100

st.dataframe(
    display[
        [
            "Ticker",
            "Nom",
            "Prix",
            "Quantité",
            "Valeur",
            "Cible",
            "Poids actuel",
            "Valeur cible",
            "Manque cible",
        ]
    ],
    hide_index=True,
    use_container_width=True,
    column_config={
        "Prix": st.column_config.NumberColumn("Prix", format="%.2f €"),
        "Quantité": st.column_config.NumberColumn("Quantité", format="%.4f"),
        "Valeur": st.column_config.NumberColumn("Valeur actuelle", format="%.2f €"),
        "Cible": st.column_config.NumberColumn("Cible %", format="%.2f %%"),
        "Poids actuel": st.column_config.NumberColumn("Poids actuel %", format="%.2f %%"),
        "Valeur cible": st.column_config.NumberColumn("Valeur cible", format="%.2f €"),
        "Manque cible": st.column_config.NumberColumn("Manque cible", format="%.2f €"),
    },
)

st.caption(
    "Indication automatique uniquement. Elle ne remplace pas une décision personnelle "
    "ni un conseil financier. Les achats doivent rester manuels dans la page Ordres."
)
