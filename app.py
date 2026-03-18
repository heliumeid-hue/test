import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from bs4 import BeautifulSoup
import re
from datetime import date, datetime
import gspread
import json
import time

# --- CONFIGURATION ---
BACKFILL_START_ID = 2518000 
BACKFILL_END_ID   = 2545000 
SPA_BASE          = "https://www.spa.gov.sa/en/N{}"
CUTOFF_DATE       = date(2026, 2, 1)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
KEYWORDS = ["intercept", "destroy", "shoot down", "drone", "uav", "missile", "ballistic", "houthi"]

st.set_page_config(page_title="KSA Defense Monitor Pro", layout="wide", page_icon="🛡️")

# --- 1. DATABASE CONNECTION ---
@st.cache_resource(ttl=600) # Refresh connection every 10 mins to avoid stale tokens
def get_worksheet():
    try:
        creds_dict = json.loads(st.secrets["google_json"])
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("KSA_Defense_Data")
        return sh.sheet1
    except Exception as e:
        st.error(f"🚨 Database Connection Failed: {e}")
        st.stop()

def ensure_headers(ws):
    if not ws.row_values(1):
        ws.update('A1', [["Date", "Location", "Type", "Count", "ID"]])

# --- 2. THE HARDENED PARSER ---
def parse_spa_article(article_id: int) -> dict | None:
    url = SPA_BASE.format(article_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200 or len(resp.text) < 500:
            return None
        
        soup = BeautifulSoup(resp.text, "html.parser")
        body = soup.find("div", class_=re.compile(r"content|body|article|news", re.I))
        text = body.get_text(" ", strip=True) if body else soup.get_text(" ", strip=True)
        text_lower = text.lower()

        if not any(k in text_lower for k in KEYWORDS):
            return None

        # Robust Date Extraction
        date_match = re.search(r'([A-Z][a-z]+ \d{1,2},?\s*\d{4})', text)
        if date_match:
            try:
                # Cleaning potential weird chars from SPA text
                clean_date = date_match.group(1).replace(',', '').strip()
                art_date = datetime.strptime(clean_date, "%B %d %Y").date()
            except:
                art_date = date.today()
        else:
            art_date = date.today()

        if art_date < CUTOFF_DATE:
            return None

        return {"id": str(article_id), "text": text_lower, "date": art_date, "url": url}
    except:
        return None

def extract_row(article: dict) -> list:
    txt = article["text"]
    
    # Improved Count Logic: Handles "(3) drones", "5 drones", or "a drone"
    def get_count(pattern):
        match = re.search(pattern, txt)
        if not match: return 0
        val = match.group(1) or match.group(2) or match.group(3)
        if val in ['a', 'an', 'one']: return 1
        try: return int(val)
        except: return 1

    d_count = get_count(r'\((\d+)\)\s*(?:drone|uav)|(\d+)\s*(?:drone|uav)|(a|an|one)\s*(?:drone|uav)')
    m_count = get_count(r'\((\d+)\)\s*(?:missile|ballistic)|(\d+)\s*(?:missile|ballistic)|(a|an|one)\s*(?:missile|ballistic)')

    # Determine Threat Type
    if d_count and m_count: threat, val = "Mixed", d_count + m_count
    elif d_count: threat, val = "Drone", d_count
    elif m_count: threat, val = "Missile", m_count
    else: threat, val = ("Drone" if "drone" in txt else "Missile"), 1

    # Regional Mapping
    loc = "Unspecified"
    loc_map = {
        "jazan": "Jazan", "najran": "Najran", "asir": "Asir", "abha": "Asir",
        "khamis mushait": "Asir", "riyadh": "Riyadh", "jeddah": "Makkah",
        "taif": "Makkah", "yanbu": "Madinah", "dammam": "Eastern Province",
        "dhahran": "Eastern Province", "khobar": "Eastern Province",
        "southern": "Southern Border", "frontier": "Southern Border"
    }
    for key, label in loc_map.items():
        if key in txt:
            loc = label
            break

    return [str(article["date"]), loc, threat, val, article["id"]]

# --- 3. SYNC LOGIC ---
def sync_data(ws, current_df, mode="latest"):
    existing_ids = set(current_df['ID'].astype(str)) if not current_df.empty else set()
    
    if mode == "latest":
        max_id = max([int(i) for i in existing_ids if i.isdigit()] or [BACKFILL_START_ID])
        search_range = range(max_id + 1, max_id + 300)
    else:
        search_range = range(BACKFILL_START_ID, BACKFILL_END_ID)

    new_rows = []
    progress_bar = st.sidebar.progress(0)
    
    for i, aid in enumerate(search_range):
        if str(aid) in existing_ids: continue
        
        art = parse_spa_article(aid)
        if art:
            row = extract_row(art)
            new_rows.append(row)
            if len(new_rows) >= 10: # Batch update to save API quota
                ws.append_rows(new_rows)
                new_rows = []
        
        # Stop if we hit a long gap of empty articles (only for latest sync)
        if mode == "latest" and i > 100 and not art: break
        
        time.sleep(0.1) # Polite delay
    
    if new_rows: ws.append_rows(new_rows)
    return len(new_rows) > 0

# --- 4. APP INTERFACE ---
ws = get_worksheet()
ensure_headers(ws)

# Load Data
raw_data = ws.get_all_records()
df = pd.DataFrame(raw_data)
if not df.empty:
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
    df = df.dropna(subset=['Date'])

# Sidebar
st.sidebar.title("Settings")
if st.sidebar.button("🔄 Sync New Reports"):
    with st.spinner("Scanning SPA..."):
        if sync_data(ws, df, mode="latest"):
            st.cache_data.clear()
            st.rerun()

if st.sidebar.button("📥 Full Backfill (Feb 2026+)"):
    sync_data(ws, df, mode="all")
    st.cache_data.clear()
    st.rerun()

# Main UI
st.title("🛡️ KSA Air Defense Monitor")
st.markdown("Real-time tracking of intercepted threats via Saudi Press Agency (SPA).")

if df.empty:
    st.info("No data found. Please run a Sync or Backfill from the sidebar.")
else:
    # Filtering
    date_range = st.sidebar.date_input("Date Range", [df['Date'].min(), date.today()])
    if len(date_range) == 2:
        mask = (df['Date'] >= date_range[0]) & (df['Date'] <= date_range[1])
        f_df = df[mask]
    else:
        f_df = df

    # Top Metrics
    total = f_df['Count'].sum()
    st.metric("Total Interceptions", total)

    col1, col2 = st.columns(2)
    cmap = {"Drone": "#00CCFF", "Missile": "#FF4B4B", "Mixed": "#AA44FF"}

    with col1:
        fig_loc = px.bar(f_df.groupby(['Location', 'Type'])['Count'].sum().reset_index(),
                        x="Location", y="Count", color="Type", title="By Province",
                        template="plotly_dark", color_discrete_map=cmap)
        st.plotly_chart(fig_loc, use_container_width=True)

    with col2:
        fig_time = px.area(f_df.groupby(['Date', 'Type'])['Count'].sum().reset_index(),
                          x="Date", y="Count", color="Type", title="Threat Intensity",
                          template="plotly_dark", color_discrete_map=cmap)
        st.plotly_chart(fig_time, use_container_width=True)

    st.subheader("Intelligence Log")
    st.dataframe(f_df.sort_values(by="Date", ascending=False), use_container_width=True)
