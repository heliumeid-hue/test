import streamlit as st
import pandas as pd
import plotly.express as px
from ntscraper import Nitter
import re
from deep_translator import GoogleTranslator
from datetime import date
import gspread
import json

st.set_page_config(page_title="KSA Defense Monitor", layout="wide", page_icon="🛡️")

# --- 1. GOOGLE SHEETS CONNECTION ---
def connect_to_database():
    try:
        creds_dict = json.loads(st.secrets["google_json"])
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("KSA_Defense_Data")
        return sh.sheet1
    except Exception as e:
        st.error(f"❌ Database Connection Error: {e}")
        st.stop()

# --- 2. HYBRID DATABASE ENGINE ---
@st.cache_data(ttl=300)
def load_and_update_data():
    worksheet = connect_to_database()
    
    # 1. Pull all existing data safely
    try:
        existing_data = worksheet.get_all_records()
        df = pd.DataFrame(existing_data)
    except:
        # If the sheet is brand new/empty, get_all_records fails
        df = pd.DataFrame()
    
    # 2. IF SHEET IS EMPTY OR HEADERS MISSING: Inject the 487 Total Baseline
    if df.empty or "Date" not in df.columns:
        st.info("Initializing Database for the first time...")
        # Clear anything in the sheet and start fresh with headers
        worksheet.clear()
        headers = ["Date", "Location", "Type", "Count"]
        baseline_data = [
            ["2026-03-02", "Unspecified", "Unspecified", 7],
            ["2026-03-03", "Unspecified", "Unspecified", 10],
            ["2026-03-04", "Al-Kharj", "Missile", 2],
            ["2026-03-04", "Eastern Region", "Drone", 1],
            ["2026-03-04", "Unspecified", "Unspecified", 10],
            ["2026-03-05", "Unspecified", "Unspecified", 7],
            ["2026-03-06", "Al-Kharj", "Missile", 3],
            ["2026-03-06", "Unspecified", "Unspecified", 8],
            ["2026-03-07", "Unspecified", "Unspecified", 28],
            ["2026-03-08", "Unspecified", "Unspecified", 35],
            ["2026-03-09", "Unspecified", "Unspecified", 25],
            ["2026-03-10", "Unspecified", "Unspecified", 8],
            ["2026-03-11", "Unspecified", "Unspecified", 30],
            ["2026-03-12", "Unspecified", "Unspecified", 50],
            ["2026-03-13", "Eastern Region", "Drone", 7],
            ["2026-03-13", "Unspecified", "Unspecified", 59],
            ["2026-03-14", "Unspecified", "Unspecified", 23],
            ["2026-03-15", "Riyadh", "Drone", 10],
            ["2026-03-15", "Eastern Region", "Drone", 4],
            ["2026-03-15", "Unspecified", "Unspecified", 17],
            ["2026-03-16", "Eastern Region", "Drone", 36],
            ["2026-03-16", "Riyadh", "Drone", 34],
            ["2026-03-16", "Unspecified", "Unspecified", 28],
            ["2026-03-17", "Eastern Region", "Drone", 24],
            ["2026-03-17", "Unspecified", "Unspecified", 21],
        ]
        worksheet.update('A1', [headers])
        worksheet.append_rows(baseline_data)
        
        # Reload after initialization
        existing_data = worksheet.get_all_records()
        df = pd.DataFrame(existing_data)

    # Standardize data
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    latest_date_in_db = df['Date'].max()

    # 3. LIVE SCRAPER: Bridge from database end to today
    new_records_to_save = []
    try:
        scraper = Nitter()
        tweets = scraper.get_tweets("modgovksa", mode='user', number=100)
        translator = GoogleTranslator(source='ar', target='en')
        
        if tweets.get('tweets'):
            for t in tweets['tweets']:
                tweet_date = pd.to_datetime(t['date']).date()
                
                if tweet_date > latest_date_in_db: 
                    orig_txt = t['text']
                    try:
                        eng_txt = translator.translate(orig_txt).lower()
                    except:
                        eng_txt = orig_txt.lower()
                    
                    if any(word in eng_txt for word in ["intercept", "destroy", "shoot down"]):
                        drone_match = re.search(r'(\d+)\s*(?:drone|uav)', eng_txt)
                        missile_match = re.search(r'(\d+)\s*(?:missile|ballistic)', eng_txt)
                        
                        count, threat = 1, "Unspecified" 
                        if drone_match: count, threat = int(drone_match.group(1)), "Drone"
                        elif missile_match: count, threat = int(missile_match.group(1)), "Missile"
                        elif "drone" in eng_txt or "uav" in eng_txt: threat = "Drone"
                        elif "missile" in eng_txt: threat = "Missile"
                        
                        loc = "Unspecified"
                        if "eastern" in eng_txt: loc = "Eastern Region"
                        elif "riyadh" in eng_txt: loc = "Riyadh"
                        elif "jazan" in eng_txt: loc = "Jazan"
                        elif "najran" in eng_txt: loc = "Najran"
                        elif "kharj" in eng_txt: loc = "Al-Kharj"
                        elif "southern" in eng_txt or "khamis" in eng_txt: loc = "Southern Region"
                        
                        new_records_to_save.append([str(tweet_date), loc, threat, count])
    except:
        pass 

    # 4. Save to Sheets
    if new_records_to_save:
        worksheet.append_rows(new_records_to_save)
        new_df = pd.DataFrame(new_records_to_save, columns=["Date", "Location", "Type", "Count"])
        new_df['Date'] = pd.to_datetime(new_df['Date']).dt.date
        df = pd.concat([df, new_df]).drop_duplicates()
        
    return df

# --- 3. UI LOGIC ---
df = load_and_update_data()

st.sidebar.header("⚙️ Dashboard Controls")
min_date = date(2026, 3, 2)
max_date = date.today()
date_sel = st.sidebar.date_input("Date Range", [min_date, max_date])

# Filter logic
if isinstance(date_sel, list) and len(date_sel) == 2:
    start_d, end_d = date_sel
else:
    start_d = end_d = (date_sel[0] if isinstance(date_sel, list) else date_sel)

mask = (df['Date'] >= start_d) & (df['Date'] <= end_d)
f_df = df[mask]

# --- 4. DISPLAY ---
st.title("🛡️ KSA Regional Defense Monitor")
total = f_df['Count'].sum()

st.markdown(f"""
    <div style="background-color:#1F3B4D; padding:20px; border-radius:10px; text-align:center; margin-bottom:20px;">
        <h2 style="margin:0; color:white;">Total Interceptions (Verified Database)</h2>
        <h1 style="margin:0; color:#00CCFF; font-size: 3.5rem;">{total}</h1>
    </div>
""", unsafe_allow_html=True)

c1, c2 = st.columns(2)
cmap = {"Drone": "#00CCFF", "Missile": "#FF4B4B", "Unspecified": "#4A6274"}

with c1:
    st.plotly_chart(px.bar(f_df.groupby(['Location', 'Type'])['Count'].sum().reset_index(), 
                    x="Location", y="Count", color="Type", template="plotly_dark", color_discrete_map=cmap), use_container_width=True)
with c2:
    st.plotly_chart(px.bar(f_df.groupby(['Date', 'Type'])['Count'].sum().reset_index(), 
                    x="Date", y="Count", color="Type", template="plotly_dark", color_discrete_map=cmap), use_container_width=True)

st.dataframe(f_df.sort_values(by='Date', ascending=False), use_container_width=True)
