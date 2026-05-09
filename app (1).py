"""
NSE F&O Scanner — Streamlit Mobile App (Fixed)
- Better session warm-up
- Connection test before bulk scan
- Retry logic per stock
- Shows actual errors for debugging
"""

import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime

st.set_page_config(
    page_title="F&O Scanner",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  .main { padding: 0.5rem 0.8rem; }
  h1 { font-size: 1.4rem !important; }
  .stButton > button {
      width: 100%; background: #1a56db; color: white;
      border-radius: 8px; padding: 0.6rem; font-size: 1rem; font-weight: 600;
  }
  .metric-card {
      background: #f0f4ff; border-radius: 10px;
      padding: 0.6rem 1rem; margin: 0.3rem 0;
      border-left: 4px solid #1a56db;
  }
</style>
""", unsafe_allow_html=True)

HEADERS = {
    "User-Agent":                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                                 "Chrome/124.0.0.0 Safari/537.36",
    "Accept":                    "text/html,application/xhtml+xml,application/xml;"
                                 "q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language":           "en-IN,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding":           "gzip, deflate, br",
    "Connection":                "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control":             "max-age=0",
}

API_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "*/*",
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.nseindia.com/option-chain",
    "X-Requested-With":"XMLHttpRequest",
    "sec-fetch-dest":  "empty",
    "sec-fetch-mode":  "cors",
    "sec-fetch-site":  "same-origin",
}

def build_fresh_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.nseindia.com", timeout=15)
    time.sleep(1.2)
    s.get("https://www.nseindia.com/option-chain", timeout=15)
    time.sleep(1.0)
    s.get("https://www.nseindia.com/market-data/live-equity-market", timeout=15)
    time.sleep(0.8)
    s.headers.update(API_HEADERS)
    return s

def test_connection(session):
    try:
        url  = "https://www.nseindia.com/api/option-chain-equities?symbol=RELIANCE"
        resp = session.get(url, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            ltp  = data["records"].get("underlyingValue", "?")
            return True, f"RELIANCE LTP = ₹{ltp}"
        else:
            return False, f"HTTP {resp.status_code} — {resp.text[:120]}"
    except Exception as e:
        return False, str(e)

@st.cache_data(ttl=600)
def get_fno_stocks():
    s = build_fresh_session()
    url  = "https://www.nseindia.com/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O"
    resp = s.get(url, timeout=15)
    data = resp.json()
    return sorted({
        item["symbol"] for item in data.get("data", [])
        if item.get("symbol") not in ("", "NIFTY 50", "NIFTY")
    })

def fetch_option_chain(symbol, session, retries=2):
    url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, timeout=12)
            if resp.status_code == 200:
                return resp.json(), None
            if resp.status_code in (401, 403) and attempt < retries:
                session.get("https://www.nseindia.com", timeout=10)
                time.sleep(1.5)
                session.get("https://www.nseindia.com/option-chain", timeout=10)
                time.sleep(1.0)
                continue
            return None, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return None, "Timeout"
        except Exception as e:
            return None, str(e)
    return None, "Max retries exceeded"

def analyse(symbol, data):
    try:
        records = data["records"]["data"]
        ltp     = data["records"].get("underlyingValue", 0)
        expiry  = data["records"]["expiryDates"][0]
        ce_rows, pe_rows = [], []
        for rec in records:
            strike = rec["strikePrice"]
            if "CE" in rec:
                c = rec["CE"]
                ce_rows.append({"strike": strike,
                                "oi":     c.get("openInterest", 0),
                                "volume": c.get("totalTradedVolume", 0)})
            if "PE" in rec:
                p = rec["PE"]
                pe_rows.append({"strike": strike,
                                "oi":     p.get("openInterest", 0),
                                "volume": p.get("totalTradedVolume", 0)})
        if not ce_rows or not pe_rows:
            return None
        total_ce_oi = sum(r["oi"] for r in ce_rows)
        total_pe_oi = sum(r["oi"] for r in pe_rows)
        pcr         = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi else 0
        act_ce = max(ce_rows, key=lambda x: x["volume"])
        act_pe = max(pe_rows, key=lambda x: x["volume"])
        max_ce = max(ce_rows, key=lambda x: x["oi"])
        max_pe = max(pe_rows, key=lambda x: x["oi"])
        if   pcr >= 1.5: sentiment = "🟢 Very Bullish"
        elif pcr >= 1.0: sentiment = "🟩 Bullish"
        elif pcr >= 0.7: sentiment = "🟡 Neutral"
        elif pcr >= 0.5: sentiment = "🟠 Bearish"
        else:            sentiment = "🔴 Very Bearish"
        return {
            "Symbol":         symbol,
            "LTP":            ltp,
            "PCR":            pcr,
            "Sentiment":      sentiment,
            "Active CE":      act_ce["strike"],
            "CE Vol":         act_ce["volume"],
            "Active PE":      act_pe["strike"],
            "PE Vol":         act_pe["volume"],
            "Resist (MaxOI)": max_ce["strike"],
            "Support (MaxOI)":max_pe["strike"],
            "Total CE OI":    total_ce_oi,
            "Total PE OI":    total_pe_oi,
            "Expiry":         expiry,
        }
    except Exception:
        return None

def pcr_color(val):
    if val >= 1.5: return "background-color:#dcfce7"
    if val >= 1.0: return "background-color:#d1fae5"
    if val >= 0.7: return "background-color:#fef9c3"
    if val >= 0.5: return "background-color:#ffedd5"
    return "background-color:#fee2e2"

# ── UI
st.title("📊 NSE F&O Scanner")
st.caption("PCR · Most Active CE/PE Strikes · Free · Live from NSE")

now_utc  = datetime.utcnow()
ist_hour = (now_utc.hour * 60 + now_utc.minute + 330) // 60 % 24
ist_min  = (now_utc.minute + 30) % 60
is_mkt   = (ist_hour == 9 and ist_min >= 15) or (10 <= ist_hour <= 14) or (ist_hour == 15 and ist_min <= 30)
if not is_mkt:
    st.warning(f"⚠️ Market closed (IST ~{ist_hour:02d}:{ist_min:02d}). Showing last session's EOD data.")

with st.sidebar:
    st.header("⚙️ Filters")
    pcr_min    = st.slider("Min PCR",   0.0, 3.0, 0.0, 0.1)
    pcr_max    = st.slider("Max PCR",   0.0, 3.0, 3.0, 0.1)
    sentiments = st.multiselect("Sentiment Filter",
        ["🟢 Very Bullish","🟩 Bullish","🟡 Neutral","🟠 Bearish","🔴 Very Bearish"], default=[])
    sort_col   = st.selectbox("Sort By", ["PCR","LTP","CE Vol","PE Vol"], index=0)
    sort_asc   = st.radio("Order", ["High → Low","Low → High"]) == "Low → High"
    max_stocks = st.slider("Max stocks to scan", 10, 220, 220, 10)
    st.markdown("---")
    st.caption("PCR Guide\n\n>1.5 Very Bullish\n1–1.5 Bullish\n0.7–1 Neutral\n0.5–0.7 Bearish\n<0.5 Very Bearish")

c1, c2 = st.columns([3, 1])
with c1:
    scan_btn = st.button("🔍 Scan All F&O Stocks", use_container_width=True)
with c2:
    test_btn = st.button("🧪 Test", use_container_width=True, help="Test NSE connection first")

if test_btn:
    with st.spinner("Testing NSE connection..."):
        s = build_fresh_session()
        ok, msg = test_connection(s)
    if ok:
        st.success(f"✅ NSE reachable — {msg}")
    else:
        st.error(f"❌ NSE blocked: {msg}")
        st.info("""
**Why:** Streamlit Cloud runs on US AWS servers. NSE blocks non-Indian/cloud IPs.

**Fix:**
1. Run app **locally on your PC** → open on phone via WiFi
2. Try during **market hours (9:15 AM – 3:30 PM IST)**
        """)

if scan_btn:
    try:
        box = st.empty()
        box.info("🔐 Warming up NSE session (3 steps)...")
        session = build_fresh_session()

        ok, msg = test_connection(session)
        if not ok:
            box.empty()
            st.error(f"❌ NSE not reachable: **{msg}**")
            st.info("""
**Root cause:** Streamlit Cloud's server IP is blocked by NSE.

**Solutions:**
- Run locally: `streamlit run app.py` on your PC, then open on phone
- Retry during peak market hours
            """)
            st.stop()

        box.empty()
        symbols = get_fno_stocks()[:max_stocks]
        st.info(f"✅ Connected ({msg}) — scanning {len(symbols)} stocks…")
        progress    = st.progress(0)
        live_status = st.empty()
        results, failed = [], []

        for i, sym in enumerate(symbols):
            live_status.caption(f"⏳ {sym}  ({i+1}/{len(symbols)})  ✅{len(results)}  ❌{len(failed)}")
            data, err = fetch_option_chain(sym, session)
            if data:
                row = analyse(sym, data)
                if row: results.append(row)
                else:   failed.append((sym, "Parse error"))
            else:
                failed.append((sym, err or "No data"))
            progress.progress((i + 1) / len(symbols))
            time.sleep(0.7)

        progress.empty()
        live_status.empty()

        if results:
            df = pd.DataFrame(results)
            st.session_state.results_df = df
            st.session_state.scan_time  = datetime.now().strftime("%d %b %Y, %H:%M")
            st.session_state.failed     = failed
            st.success(f"✅ Done! {len(results)} stocks  |  {len(failed)} failed")
            if failed:
                with st.expander(f"⚠️ {len(failed)} failed"):
                    st.dataframe(pd.DataFrame(failed, columns=["Symbol","Reason"]),
                                 use_container_width=True, hide_index=True)
        else:
            st.error("No data fetched. Tap 🧪 Test to diagnose.")
    except Exception as e:
        st.error(f"Error: {e}")

if st.session_state.get("results_df") is not None:
    df = st.session_state.results_df.copy()
    st.caption(f"Last scan: {st.session_state.get('scan_time','—')}")
    df = df[(df["PCR"] >= pcr_min) & (df["PCR"] <= pcr_max)]
    if sentiments:
        df = df[df["Sentiment"].isin(sentiments)]
    df = df.sort_values(sort_col, ascending=sort_asc).reset_index(drop=True)

    total = len(df)
    bull  = len(df[df["PCR"] >= 1.0])
    bear  = len(df[df["PCR"] <  0.7])
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total",total); c2.metric("🟢",bull); c3.metric("🟡",total-bull-bear); c4.metric("🔴",bear)
    st.divider()

    tab1,tab2,tab3 = st.tabs(["📋 All","🟢 Bullish","🔴 Bearish"])
    def show_table(d):
        cols = ["Symbol","LTP","PCR","Sentiment","Active CE","Active PE","Resist (MaxOI)","Support (MaxOI)","CE Vol","PE Vol"]
        st.dataframe(d[cols].style.applymap(pcr_color,subset=["PCR"]),
                     use_container_width=True, hide_index=True, height=480)
    with tab1: show_table(df)
    with tab2:
        b=df[df["PCR"]>=1.0]; st.caption(f"{len(b)} stocks"); show_table(b)
    with tab3:
        b=df[df["PCR"]<0.7];  st.caption(f"{len(b)} stocks"); show_table(b)

    st.divider()
    st.subheader("🔎 Stock Detail")
    sel = st.selectbox("Pick a stock", df["Symbol"].tolist())
    if sel:
        r = df[df["Symbol"]==sel].iloc[0]
        c1,c2 = st.columns(2)
        with c1: st.markdown(f"<div class='metric-card'><b>{r['Symbol']}</b> — ₹{r['LTP']}<br>Expiry: {r['Expiry']}<br>{r['Sentiment']}</div>",unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='metric-card'>PCR: <b>{r['PCR']}</b><br>CE OI: {r['Total CE OI']:,}<br>PE OI: {r['Total PE OI']:,}</div>",unsafe_allow_html=True)
        c3,c4 = st.columns(2)
        with c3: st.markdown(f"<div class='metric-card' style='border-left-color:#dc2626'>🔴 <b>Most Active CE</b><br>Strike: <b>{r['Active CE']}</b><br>Volume: {int(r['CE Vol']):,}<br>Resistance: {r['Resist (MaxOI)']}</div>",unsafe_allow_html=True)
        with c4: st.markdown(f"<div class='metric-card' style='border-left-color:#15803d'>🟢 <b>Most Active PE</b><br>Strike: <b>{r['Active PE']}</b><br>Volume: {int(r['PE Vol']):,}<br>Support: {r['Support (MaxOI)']}</div>",unsafe_allow_html=True)

    st.divider()
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download CSV", csv,
        file_name=f"fno_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv", use_container_width=True)
else:
    if not scan_btn and not test_btn:
        st.markdown("""
### 👆 Tap "Scan All F&O Stocks" to start
**First time?** Tap 🧪 **Test** first to confirm NSE is reachable.

**Best time to scan:** 10 AM – 3 PM IST (market hours)
        """)
