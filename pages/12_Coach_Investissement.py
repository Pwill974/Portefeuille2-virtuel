
from __future__ import annotations

import math
from typing import Any
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Alpha Zen Pro — Coach Investissement", page_icon="🧭", layout="wide")

from services.auth import require_authentication, show_logout_button
from services.supabase_service import load_cloud_state_into_session, supabase_is_configured

ASSETS = {
    "DCAM.PA": {"nom": "Amundi PEA MSCI World", "type": "ETF", "poche": "Socle Zen", "cible": 0.20},
    "PSP5.PA": {"nom": "Amundi PEA S&P 500", "type": "ETF", "poche": "Socle Zen", "cible": 0.15},
    "PUST.PA": {"nom": "Amundi PEA Nasdaq-100", "type": "ETF", "poche": "Socle Zen", "cible": 0.10},
    "PCEU.PA": {"nom": "Amundi PEA MSCI Europe", "type": "ETF", "poche": "Socle Zen", "cible": 0.05},
    "GUARD.PA": {"nom": "BNP Défense Europe", "type": "ETF", "poche": "Momentum", "cible": 0.10},
    "SU.PA": {"nom": "Schneider Electric", "type": "Action", "poche": "Momentum", "cible": 0.05},
    "AI.PA": {"nom": "Air Liquide", "type": "Action", "poche": "Momentum", "cible": 0.03},
    "TTE.PA": {"nom": "TotalEnergies", "type": "Action", "poche": "Momentum", "cible": 0.02},
    "AM.PA": {"nom": "Dassault Aviation", "type": "Action", "poche": "Momentum", "cible": 0.05},
    "HO.PA": {"nom": "Thales", "type": "Action", "poche": "Momentum", "cible": 0.05},
    "STMPA.PA": {"nom": "STMicroelectronics", "type": "Action", "poche": "Momentum", "cible": 0.05},
    "SAN.PA": {"nom": "Sanofi", "type": "Action", "poche": "Satellite", "cible": 0.05},
    "PAEEM.PA": {"nom": "Amundi PEA Émergents", "type": "ETF", "poche": "Satellite", "cible": 0.10},
}

require_authentication()
show_logout_button()

def euro(x: float) -> str:
    return f"{float(x):,.2f} €".replace(",", " ").replace(".", ",")

def pf(x: float) -> str:
    return f"{float(x)*100:.2f} %".replace(".", ",")

def sf(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default

def positions_clean(df):
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame(columns=["Ticker", "Quantité", "PRU (€)"])
    d = df.copy()
    cols = {str(c).lower(): c for c in d.columns}
    ticker = next((c for c in d.columns if "ticker" in str(c).lower()), None)
    qty = next((c for c in d.columns if "quant" in str(c).lower() or str(c).lower() in ["qty", "quantity"]), None)
    pru = next((c for c in d.columns if "pru" in str(c).lower() or "prix" in str(c).lower() or "cost" in str(c).lower()), None)
    out = pd.DataFrame()
    out["Ticker"] = d[ticker].astype(str).str.upper().str.strip() if ticker else ""
    out["Quantité"] = pd.to_numeric(d[qty], errors="coerce").fillna(0.0) if qty else 0.0
    out["PRU (€)"] = pd.to_numeric(d[pru], errors="coerce").fillna(0.0) if pru else 0.0
    return out

@st.cache_data(ttl=1200, show_spinner=False)
def histo(ticker: str) -> pd.DataFrame:
    data = yf.download(ticker, period="2y", interval="1d", auto_adjust=True, progress=False)
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    close = data["Close"].dropna()
    h = pd.DataFrame(index=close.index)
    h["Prix"] = close
    h["MM50"] = close.rolling(50).mean()
    h["MM200"] = close.rolling(200).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    h["RSI14"] = 100 - (100 / (1 + rs))
    h["Momentum 3M"] = close / close.shift(63) - 1
    h["Momentum 6M"] = close / close.shift(126) - 1
    h["Momentum 12M"] = close / close.shift(252) - 1
    return h

def last_ind(ticker: str) -> dict:
    h = histo(ticker)
    if h.empty:
        return {"Prix":0,"MM50":0,"MM200":0,"RSI14":0,"Momentum 3M":0,"Momentum 6M":0,"Momentum 12M":0}
    r = h.dropna(subset=["Prix"]).iloc[-1]
    return {k: sf(r.get(k)) for k in ["Prix","MM50","MM200","RSI14","Momentum 3M","Momentum 6M","Momentum 12M"]}

def score(ind: dict) -> tuple[int, str]:
    s, reasons = 0, []
    if ind["Prix"] > ind["MM200"] > 0:
        s += 2; reasons.append("prix > MM200")
    else:
        reasons.append("prix sous MM200")
    if ind["Prix"] > ind["MM50"] > 0:
        s += 1; reasons.append("prix > MM50")
    else:
        reasons.append("prix sous MM50")
    for key, label in [("Momentum 3M","momentum 3M"),("Momentum 6M","momentum 6M"),("Momentum 12M","momentum 12M")]:
        if ind[key] > 0:
            s += 1; reasons.append(label + " positif")
        else:
            reasons.append(label + " négatif")
    if 35 <= ind["RSI14"] <= 70:
        s += 1; reasons.append("RSI correct")
    elif ind["RSI14"] > 70:
        reasons.append("RSI élevé")
    else:
        reasons.append("RSI faible ou indisponible")
    return s, " ; ".join(reasons)

def build_table(pos, cash, mode, booster_percent):
    rows = []
    for ticker, meta in ASSETS.items():
        ind = last_ind(ticker)
        qty = sf(pos.loc[pos["Ticker"] == ticker, "Quantité"].sum())
        pru = sf(pos.loc[pos["Ticker"] == ticker, "PRU (€)"].iloc[-1]) if not pos.loc[pos["Ticker"] == ticker].empty else 0
        sc, rs = score(ind)
        rows.append({**meta, "Ticker":ticker, "Prix":ind["Prix"], "Quantité":qty, "PRU":pru,
                     "Valeur":qty*ind["Prix"], "Score":sc, "Raisons":rs, **ind})
    df = pd.DataFrame(rows)
    total = sf(df["Valeur"].sum()) + cash
    if total <= 0:
        total = 1
    if mode == "Strict cible":
        extra_etf, extra_action = 0, 0
    elif mode == "Booster prudent":
        extra_etf, extra_action = 0.02, 0.01
    else:
        extra_etf, extra_action = 0.03, 0.02
    df["Poids actuel"] = df["Valeur"] / total
    df["Valeur cible"] = df["cible"] * total
    df["Manque cible"] = (df["Valeur cible"] - df["Valeur"]).clip(lower=0)
    df["Marge booster"] = np.where(df["type"].eq("ETF"), extra_etf, extra_action)
    df["Poids max"] = df["cible"] + df["Marge booster"]
    df["Valeur max"] = df["Poids max"] * total
    df["Marge achat max"] = (df["Valeur max"] - df["Valeur"]).clip(lower=0)

    decisions = []
    for _, r in df.iterrows():
        if r["Prix"] <= 0:
            d = "Données indisponibles"
        elif r["Poids actuel"] > r["Poids max"]:
            d = "⚫ Trop pondéré"
        elif r["Prix"] < r["MM200"]:
            d = "🔴 Attendre"
        elif r["Manque cible"] > 0 and r["Score"] >= 4:
            d = "🟢 Achat prioritaire"
        elif r["Manque cible"] > 0:
            d = "🟠 Sous cible mais prudent"
        elif r["Score"] >= 6 and r["RSI14"] <= 75 and r["Marge achat max"] > 0:
            d = "⚡ Booster autorisé"
        elif r["Score"] >= 5:
            d = "🔵 Conserver"
        else:
            d = "🔴 Attendre"
        decisions.append(d)
    df["Décision"] = decisions

    df["Budget proposé"] = 0.0
    df["Titres proposés"] = 0
    rebalance_budget = cash * (100 - booster_percent) / 100
    booster_budget = cash * booster_percent / 100

    remaining = rebalance_budget
    prio = df[df["Décision"].isin(["🟢 Achat prioritaire","🟠 Sous cible mais prudent"])].sort_values(["Manque cible","Score"], ascending=[False,False])
    for idx, r in prio.iterrows():
        if remaining <= 0: break
        if r["Prix"] <= 0: continue
        amount = min(remaining, r["Manque cible"])
        qty = math.floor(amount / r["Prix"])
        spend = qty * r["Prix"]
        if qty > 0:
            df.loc[idx, "Titres proposés"] += qty
            df.loc[idx, "Budget proposé"] += spend
            remaining -= spend

    remaining_boost = booster_budget + remaining
    boost = df[df["Décision"].eq("⚡ Booster autorisé")].sort_values(["Score","Momentum 6M","Momentum 3M"], ascending=[False,False,False])
    for idx, r in boost.iterrows():
        if remaining_boost <= 0: break
        if r["Prix"] <= 0: continue
        amount = min(remaining_boost, r["Marge achat max"])
        qty = math.floor(amount / r["Prix"])
        spend = qty * r["Prix"]
        if qty > 0:
            df.loc[idx, "Titres proposés"] += qty
            df.loc[idx, "Budget proposé"] += spend
            remaining_boost -= spend
    return df, total

st.title("🧭 Coach Investissement")
st.caption("Plan simple : 1) rééquilibrer les actifs sous cible ; 2) booster seulement les meilleurs momentum ; 3) éviter les achats sous MM200.")

if supabase_is_configured():
    try:
        load_cloud_state_into_session(force=True)
    except Exception as e:
        st.warning(f"Chargement Supabase incomplet : {e}")

pos = positions_clean(st.session_state.get("virtual_positions"))
cash = sf(st.session_state.get("virtual_cash", 0.0))

with st.sidebar:
    st.header("Réglages")
    mode = st.selectbox("Mode", ["Strict cible", "Booster prudent", "Booster dynamique"], index=1)
    default = 0 if mode == "Strict cible" else 30 if mode == "Booster prudent" else 40
    booster_percent = st.slider("Part booster du cash", 0, 50, default, 5)

with st.spinner("Analyse en cours..."):
    df, total = build_table(pos, cash, mode, booster_percent)

budget = sf(df["Budget proposé"].sum())
c1,c2,c3,c4 = st.columns(4)
c1.metric("Portefeuille total", euro(total))
c2.metric("Liquidités", euro(cash))
c3.metric("Budget proposé", euro(budget))
c4.metric("Mode", mode)

st.divider()
st.subheader("Plan d'achat proposé")

if cash <= 0:
    st.warning("Aucune liquidité disponible. Ajoute d'abord ton versement mensuel.")
elif budget <= 0:
    st.info("Aucun achat proposé : soit les cibles sont atteintes, soit les tendances sont insuffisantes.")
else:
    orders = df[df["Titres proposés"] > 0].sort_values("Budget proposé", ascending=False)
    for _, r in orders.iterrows():
        with st.container(border=True):
            a,b,c,d = st.columns([2,1,1,1])
            a.markdown(f"**{r['Ticker']} — {r['nom']}**  \n{r['Décision']}")
            b.metric("Titres", int(r["Titres proposés"]))
            c.metric("Montant", euro(r["Budget proposé"]))
            d.metric("Score", f"{int(r['Score'])}/7")
            st.caption(r["Raisons"])
    st.success("Passe ensuite ces ordres manuellement dans la page Ordres ou Actifs & Ordres.")

st.divider()
st.subheader("Tableau complet")

show = df.copy()
for col in ["cible","Poids actuel","Poids max","Momentum 3M","Momentum 6M","Momentum 12M"]:
    show[col] = show[col] * 100

st.dataframe(
    show[["Ticker","nom","poche","Décision","Prix","Quantité","Valeur","cible","Poids actuel","Poids max","Score","Momentum 3M","Momentum 6M","Momentum 12M","RSI14","Manque cible","Marge achat max","Titres proposés","Budget proposé"]],
    hide_index=True,
    use_container_width=True,
    column_config={
        "Prix": st.column_config.NumberColumn("Prix", format="%.2f €"),
        "Valeur": st.column_config.NumberColumn("Valeur", format="%.2f €"),
        "cible": st.column_config.NumberColumn("Cible %", format="%.2f %%"),
        "Poids actuel": st.column_config.NumberColumn("Poids actuel %", format="%.2f %%"),
        "Poids max": st.column_config.NumberColumn("Poids max %", format="%.2f %%"),
        "Momentum 3M": st.column_config.NumberColumn("Momentum 3M", format="%.2f %%"),
        "Momentum 6M": st.column_config.NumberColumn("Momentum 6M", format="%.2f %%"),
        "Momentum 12M": st.column_config.NumberColumn("Momentum 12M", format="%.2f %%"),
        "Manque cible": st.column_config.NumberColumn("Manque cible", format="%.2f €"),
        "Marge achat max": st.column_config.NumberColumn("Marge achat max", format="%.2f €"),
        "Budget proposé": st.column_config.NumberColumn("Budget proposé", format="%.2f €"),
    },
)

st.divider()
st.subheader("Détail et graphique")

choice = st.selectbox("Actif", [f"{r['Ticker']} — {r['nom']} — {r['Décision']}" for _, r in df.iterrows()])
ticker = choice.split(" — ")[0]
r = df[df["Ticker"] == ticker].iloc[0]
h = histo(ticker)

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Prix", euro(r["Prix"]))
m2.metric("MM50", euro(r["MM50"]))
m3.metric("MM200", euro(r["MM200"]))
m4.metric("RSI14", f"{sf(r['RSI14']):.2f}".replace(".", ","))
m5.metric("Score", f"{int(r['Score'])}/7")

st.write(f"**Décision :** {r['Décision']}")
st.write(f"**Pourquoi :** {r['Raisons']}")

if not h.empty:
    st.line_chart(h[["Prix","MM50","MM200"]].dropna(how="all"), use_container_width=True)

st.info("Cette page donne un plan et une discipline. Elle ne passe pas les ordres automatiquement.")
