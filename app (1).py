# app.py
# V2 PRO OPTIONS BUYING SCANNER
# Run: streamlit run app.py

import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime

# ---------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------
st.set_page_config(
    page_title="V2 Pro Options Scanner",
    page_icon="📈",
    layout="wide"
)

# ---------------------------------------------------
# STYLE
# ---------------------------------------------------
st.markdown("""
<style>
.main {padding:0.6rem;}
.stButton > button {
    width:100%;
    background:#1a56db;
    color:white;
    border-radius:8px;
    font-weight:700;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------
# NSE HEADERS
# ---------------------------------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/"
}

# ---------------------------------------------------
# NIFTY50 / LIQUID STOCKS
# ---------------------------------------------------
WATCHLIST = [
    "RELIANCE","HDFCBANK","ICICIBANK","SBIN","AXISBANK",
    "KOTAKBANK","INFY","TCS","LT","ITC","BHARTIARTL",
    "MARUTI","TATAMOTORS","BAJFINANCE","SUNPHARMA",
    "ULTRACEMCO","POWERGRID","M&M","NTPC","WIPRO"
]

# ---------------------------------------------------
# SESSION
# ---------------------------------------------------
@st.cache_resource(ttl=300)
def get_session():
    s = requests.Session()
    s.headers.update(HEADERS)

    try:
        s.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
        s.get("https://www.nseindia.com/option-chain", timeout=10)
    except:
        pass

    return s

# ---------------------------------------------------
# FETCH OPTION CHAIN
# ---------------------------------------------------
def fetch_chain(symbol, session):
    url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"

    try:
        r = session.get(url, timeout=10)

        if r.status_code in [401, 403]:
            session = get_session()
            r = session.get(url, timeout=10)

        r.raise_for_status()
        return r.json()

    except:
        return None

# ---------------------------------------------------
# ANALYSE
# ---------------------------------------------------
def analyse(symbol, data):
    try:
        records = data["records"]["data"]
        ltp = data["records"]["underlyingValue"]

        ce = []
        pe = []

        for row in records:
            strike = row["strikePrice"]

            if "CE" in row:
                ce.append({
                    "strike": strike,
                    "oi": row["CE"].get("openInterest", 0),
                    "vol": row["CE"].get("totalTradedVolume", 0)
                })

            if "PE" in row:
                pe.append({
                    "strike": strike,
                    "oi": row["PE"].get("openInterest", 0),
                    "vol": row["PE"].get("totalTradedVolume", 0)
                })

        total_ce = sum(x["oi"] for x in ce)
        total_pe = sum(x["oi"] for x in pe)

        pcr = round(total_pe / total_ce, 2) if total_ce else 0

        max_ce = max(ce, key=lambda x: x["oi"])
        max_pe = max(pe, key=lambda x: x["oi"])

        act_ce = max(ce, key=lambda x: x["vol"])
        act_pe = max(pe, key=lambda x: x["vol"])

        resistance = max_ce["strike"]
        support = max_pe["strike"]

        # ---------------------------------------------------
        # SIGNAL ENGINE
        # ---------------------------------------------------
        signal = "WATCH"
        option = "-"

        # CE BUY
        if pcr > 1 and ltp > support and act_pe["vol"] > act_ce["vol"]:
            signal = "🟢 CE BUY"
            option = "CALL"

        # PE BUY
        elif pcr < 0.8 and ltp < resistance and act_ce["vol"] > act_pe["vol"]:
            signal = "🔴 PE BUY"
            option = "PUT"

        # Strength Score
        score = 0
        if pcr > 1: score += 2
        if act_pe["vol"] > act_ce["vol"]: score += 2
        if ltp > support: score += 2
        if ltp < resistance: score += 2
        if abs(resistance - ltp) > abs(ltp - support): score += 2

        return {
            "Stock": symbol,
            "LTP": round(ltp, 2),
            "PCR": pcr,
            "Support": support,
            "Resistance": resistance,
            "CE Vol": act_ce["vol"],
            "PE Vol": act_pe["vol"],
            "Signal": signal,
            "Option": option,
            "Score": score
        }

    except:
        return None

# ---------------------------------------------------
# TITLE
# ---------------------------------------------------
st.title("📈 V2 Pro Options Buying Scanner")
st.caption("Support/Resistance via OI • CE/PE Buy Opportunities")

# ---------------------------------------------------
# SIDEBAR
# ---------------------------------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    max_stocks = st.slider("Stocks", 5, 20, 15)
    delay = st.slider("Delay", 1, 3, 1)

# ---------------------------------------------------
# BUTTON
# ---------------------------------------------------
run = st.button("🔍 Run Scanner")

if "df" not in st.session_state:
    st.session_state.df = None

# ---------------------------------------------------
# RUN SCAN
# ---------------------------------------------------
if run:

    session = get_session()
    results = []

    progress = st.progress(0)

    for i, sym in enumerate(WATCHLIST[:max_stocks]):

        data = fetch_chain(sym, session)

        if data:
            row = analyse(sym, data)
            if row:
                results.append(row)

        progress.progress((i + 1) / max_stocks)
        time.sleep(delay)

    if results:
        st.session_state.df = pd.DataFrame(results)

# ---------------------------------------------------
# DISPLAY
# ---------------------------------------------------
if st.session_state.df is not None:

    df = st.session_state.df.copy()

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Stocks", len(df))
    c2.metric("CE Buy", len(df[df["Signal"] == "🟢 CE BUY"]))
    c3.metric("PE Buy", len(df[df["Signal"] == "🔴 PE BUY"]))
    c4.metric("Updated", datetime.now().strftime("%H:%M"))

    st.divider()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🎯 Top Trades",
        "🟢 CE Buy",
        "🔴 PE Buy",
        "📌 Support Bounce",
        "📉 Resistance Reject"
    ])

    # ---------------------------------------------------
    # TOP TRADES
    # ---------------------------------------------------
    with tab1:
        top = df.sort_values("Score", ascending=False)
        st.dataframe(top, use_container_width=True)

    # ---------------------------------------------------
    # CE BUY
    # ---------------------------------------------------
    with tab2:
        ce = df[df["Signal"] == "🟢 CE BUY"]
        st.dataframe(ce, use_container_width=True)

    # ---------------------------------------------------
    # PE BUY
    # ---------------------------------------------------
    with tab3:
        pe = df[df["Signal"] == "🔴 PE BUY"]
        st.dataframe(pe, use_container_width=True)

    # ---------------------------------------------------
    # SUPPORT BOUNCE
    # ---------------------------------------------------
    with tab4:
        sup = df[abs(df["LTP"] - df["Support"]) < (df["LTP"] * 0.01)]
        st.dataframe(sup, use_container_width=True)

    # ---------------------------------------------------
    # RESISTANCE REJECT
    # ---------------------------------------------------
    with tab5:
        res = df[abs(df["LTP"] - df["Resistance"]) < (df["LTP"] * 0.01)]
        st.dataframe(res, use_container_width=True)

    # ---------------------------------------------------
    # DETAIL
    # ---------------------------------------------------
    st.divider()
    st.subheader("🔎 Stock Detail")

    stock = st.selectbox("Select Stock", df["Stock"])

    row = df[df["Stock"] == stock].iloc[0]

    x1, x2 = st.columns(2)

    x1.metric("LTP", row["LTP"])
    x1.metric("PCR", row["PCR"])
    x1.metric("Signal", row["Signal"])
    x1.metric("Score", row["Score"])

    x2.metric("Support", row["Support"])
    x2.metric("Resistance", row["Resistance"])
    x2.metric("Option", row["Option"])
    x2.metric("PE Vol", row["PE Vol"])

    # ---------------------------------------------------
    # CSV
    # ---------------------------------------------------
    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "⬇️ Download CSV",
        csv,
        "v2_pro_scanner.csv",
        "text/csv"
    )

else:
    st.info("Click Run Scanner to start.")
