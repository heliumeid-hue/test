import streamlit as st
import pandas as pd
import plotly.express as px
from ntscraper import Nitter
import re
from deep_translator import GoogleTranslator
from datetime import date, datetime
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

# --- 2. DATA ENGINE ---
@st.cache_data(ttl=300)
def load_and_update_data():
    worksheet = connect_to_database()
    
    try:
        existing_data = worksheet.get_all_records()
        df = pd.DataFrame(existing_data)
    except:
        df = pd.DataFrame()
    
    # Initialize if empty
    if df.empty or "Date" not in df.columns:
        worksheet.clear()
        headers = ["Date", "Location", "Type", "Count"]
        baseline = [
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
        worksheet.append_rows(baseline)
        df = pd.DataFrame(worksheet.get_all_records())

    # CRITICAL FIX: Ensure Date is a proper date object for comparison
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    latest_date_in_db = df['Date'].max()

    # Live Scraper
    new_rows = []
    try:
        scraper = Nitter()
        tweets = scraper.get_tweets("modgovksa", mode='user', number=50)
        translator = GoogleTranslator(source='ar', target='en')
        
        for t in tweets.get('tweets', []):
            t_date = pd.to_datetime(t['date']).date()
            if t_date > latest_date_in_db:
                txt = t['text']
                try: eng = translator.translate(txt).lower()
                except: eng = txt.lower()
                
                if any(w in eng for w in ["intercept", "destroy", "shoot down"]):
                    d_m = re.search(r'(\d+)\s*(?:drone|uav)', eng)
                    m_m = re.search(r'(\d+)\s*(?:missile|ballistic)', eng)
                    c = int(d_m.group(1)) if d_m else (int(m_m.group(1)) if m_m else 1)
                    th = "Drone" if "drone" in eng or "uav" in eng else ("Missile" if "missile" in eng else "Unspecified")
                    
                    loc = "Unspecified"
                    for l in ["eastern", "riyadh", "jazan", "najran", "kharj", "southern"]:
                        if l in eng: loc = l.capitalize() + (" Region" if l in ["eastern", "southern"] else "")
                    
                    new_rows.append([str(t_date), loc, th, c])
    except: pass

    if new_rows:
        worksheet.append_rows(new_rows)
        ndf = pd.DataFrame(new_rows, columns=["Date", "Location", "Type", "Count"])
        ndf['Date'] = pd.to_datetime(ndf['Date']).dt.date
        df = pd.concat([df, ndf]).drop_duplicates()
        
    return df

# --- 3. UI ---
df = load_and_update_data()

st.sidebar.header("⚙️ Controls")
date_sel = st.sidebar.date_input("Range", [date(2026, 3, 2), date.today()])

# Date filter with format safety
if isinstance(date_sel, list) and len(date_sel) == 2:
    s_d, e_d = date_sel
elif isinstance(date_sel, tuple) and len(date_sel) == 2:
    s_d, e_d = date_sel
else:
    s_d = e_d = (date_sel[0] if isinstance(date_sel, (list, tuple)) else date_sel)

# Final comparison mask
f_df = df[(df['Date'] >= s_d) & (df['Date'] <= e_d)]

st.title("🛡️ KSA Regional Defense Monitor")
total = f_df['Count'].sum()
st.markdown(f"""<div style="background-color:#1F3B4D; padding:20px; border-radius:10px; text-align:center; margin-bottom:20px;">
<h2 style="margin:0; color:white;">Total Interceptions</h2>
<h1 style="margin:0; color:#00CCFF; font-size: 3.5rem;">{total}</h1></div>""", unsafe_allow_html=True)

c1, c2 = st.columns(2)
cmap = {"Drone": "#00CCFF", "Missile": "#FF4B4B", "Unspecified": "#4A6274"}

with c1:
    st.plotly_chart(px.bar(f_df.groupby(['Location', 'Type'])['Count'].sum().reset_index(), 
    x="Location", y="Count", color="Type", template="plotly_dark", color_discrete_map=cmap), use_container_width=True)
with c2:
    st.plotly_chart(px.bar(f_df.groupby(['Date', 'Type'])['Count'].sum().reset_index(), 
    x="Date", y="Count", color="Type", template="plotly_dark", color_discrete_map=cmap), use_container_width=True)

st.dataframe(f_df.sort_values(by='Date', ascending=False), use_container_width=True)
