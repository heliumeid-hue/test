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
# SPA Article IDs for March 2026 are currently in the 2,545,000+ range.
BACKFILL_START_ID = 2544000 
SPA_BASE          = "https://www.spa.gov.sa/en/N{}"
HEADERS           = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
KEYWORDS          = ["intercept", "destroy", "shoot down", "drone", "uav", "missile", "ballistic", "houthi"]

st.set_page_config(page_title="KSA Defense Monitor Pro", layout="wide", page_icon="🛡️")

# --- 1. DATABASE CONNECTION ---
@st.cache_resource(ttl=600)
def get_worksheet():
    try:
        raw_json = st.secrets["google_json"]
        # Handle both string and dict formats for secrets
        creds_dict = json.loads(raw_json) if isinstance(raw_json, str) else dict(raw_json)
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("KSA_Defense_Data")
        return sh.sheet1
    except Exception as e:
        st.error(f"🚨 Connection Error: {e}")
        st.info("Check if you shared the Google Sheet with the client_email in your JSON secrets.")
        st.stop()

# --- 2. THE HARDENED PARSER ---
def parse_spa_article(aid):
    try:
        url = SPA_BASE.format(aid)
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code != 200: return None
        
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        text_lower = text.lower()

        if not any(k in text_lower for k in KEYWORDS):
            return None

        # Extract Date
        date_match = re.search(r'([A-Z][a-z]+ \d{1,2},?\s*\d{4})', text)
        art_date = date_match.group(1).replace(',', '').strip() if date_match else str(date.today())
        
        # Extract Type
        threat = "Drone" if "drone" in text_lower or "uav" in text_lower else "Missile"
        
        # Extract Location
        loc = "Unspecified"
        loc_map = {"jazan": "Jazan", "najran": "Najran", "asir": "Asir", "abha": "Asir", 
                   "khamis": "Asir", "riyadh": "Riyadh", "southern": "Southern Border"}
        for key, label in loc_map.items():
            if key in text_lower:
                loc = label
                break

        return [art_date, loc, threat, 1, str(aid)]
    except:
        return None

# --- 3. MAIN APP INTERFACE ---
ws = get_worksheet()

# Ensure headers exist
if not ws.row_values(1):
    ws.update('A1', [["Date", "Location", "Type", "Count", "ID"]])

st.title("🛡️ KSA Air Defense Monitor")
st.markdown("Real-time automated scanning of Saudi Press Agency defense reports.")

# Sidebar Controls
st.sidebar.header("Controls")
if st.sidebar.button("🚀 Start Live Scan"):
    status_placeholder = st.sidebar.empty()
    found_count = 0
    
    # Scan a range of 500 articles starting from our config ID
    for i in range(BACKFILL_START_ID, BACKFILL_START_ID + 500):
        status_placeholder.info(f"Scanning: N{i}...")
        
        # Check if ID already in sheet to avoid duplicates
        existing_ids = ws.col_values(5)
        if str(i) in existing_ids:
            continue
            
        data = parse_spa_article(i)
        if data:
            ws.append_row(data)
            found_count += 1
            st.toast(f"New Report Found! ID: N{i}", icon="✅")
        
        time.sleep(0.05) # Polite delay
        
    status_placeholder.success(f"Scan complete. Found {found_count} matches.")
    st.rerun()

# --- 4. DATA VISUALIZATION ---
try:
    data = ws.get_all_records()
    if data:
        df = pd.DataFrame(data)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        
        # Metrics
        st.metric("Total Interceptions Detected", len(df))
        
        col1, col2 = st.columns(2)
        with col1:
            fig1 = px.pie(df, names='Type', title="Threat Type Distribution", hole=0.4,
                          color_discrete_map={"Drone": "#00CCFF", "Missile": "#FF4B4B"})
            st.plotly_chart(fig1, use_container_width=True)
            
        with col2:
            fig2 = px.bar(df, x='Location', title="Interceptions by Region", 
                          color='Type', template="plotly_dark")
            st.plotly_chart(fig2, use_container_width=True)
            
        st.subheader("📋 Intelligence Log")
        st.dataframe(df.sort_values(by='Date', ascending=False), use_container_width=True)
    else:
        st.warning("No records found in database. Please run 'Start Live Scan' in the sidebar.")
except Exception as e:
    st.info("Database is initializing... run your first scan.")
