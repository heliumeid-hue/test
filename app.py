import streamlit as st
import pandas as pd
import plotly.express as px
from ntscraper import Nitter
import re
from deep_translator import GoogleTranslator
from datetime import date, datetime, timedelta
import gspread
import json

st.set_page_config(page_title="KSA Defense Monitor", layout="wide", page_icon="🛡️")

# --- 1. DATABASE CONNECTION ---
def connect_to_database():
    try:
        creds_dict = json.loads(st.secrets["google_json"])
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("KSA_Defense_Data")
        return sh.sheet1
    except Exception as e:
        st.error(f"Database Error: {e}")
        st.stop()

# --- 2. THE ENGINE ---
@st.cache_data(ttl=180) # Reduced to 3 minutes for faster 18 March updates
def load_and_update_data():
    worksheet = connect_to_database()
    try:
        df = pd.DataFrame(worksheet.get_all_records())
    except:
        df = pd.DataFrame()

    # Initialize Baseline if Sheet is blank
    if df.empty or "Date" not in df.columns:
        worksheet.clear()
        headers = ["Date", "Location", "Type", "Count"]
        # The 487 Baseline (Mar 2 - Mar 17)
        baseline = [["2026-03-02","Unspecified","Unspecified",7],["2026-03-03","Unspecified","Unspecified",10],["2026-03-04","Al-Kharj","Missile",2],["2026-03-04","Eastern Region","Drone",1],["2026-03-04","Unspecified","Unspecified",10],["2026-03-05","Unspecified","Unspecified",7],["2026-03-06","Al-Kharj","Missile",3],["2026-03-06","Unspecified","Unspecified",8],["2026-03-07","Unspecified","Unspecified",28],["2026-03-08","Unspecified","Unspecified",35],["2026-03-09","Unspecified","Unspecified",25],["2026-03-10","Unspecified","Unspecified",8],["2026-03-11","Unspecified","Unspecified",30],["2026-03-12","Unspecified","Unspecified",50],["2026-03-13","Eastern Region","Drone",7],["2026-03-13","Unspecified","Unspecified",59],["2026-03-14","Unspecified","Unspecified",23],["2026-03-15","Riyadh","Drone",10],["2026-03-15","Eastern Region","Drone",4],["2026-03-15","Unspecified","Unspecified",17],["2026-03-16","Eastern Region","Drone",36],["2026-03-16","Riyadh","Drone",34],["2026-03-16","Unspecified","Unspecified",28],["2026-03-17","Eastern Region","Drone",24],["2026-03-17","Unspecified","Unspecified",21]]
        worksheet.update('A1', [headers])
        worksheet.append_rows(baseline)
        df = pd.DataFrame(worksheet.get_all_records())

    df['Date'] = pd.to_datetime(df['Date']).dt.date
    latest_db_date = df['Date'].max()

    # SCRAPER: Hunting for 18 March
    new_entries = []
    try:
        scraper = Nitter()
        # Increased to 100 tweets to look deeper into the 18th
        tweets = scraper.get_tweets("modgovksa", mode='user', number=100)
        translator = GoogleTranslator(source='ar', target='en')
        
        for t in tweets.get('tweets', []):
            t_date = pd.to_datetime(t['date']).date()
            
            # Look for everything from the latest date forward
            if t_date >= latest_db_date:
                txt = t['text']
                # Check for duplicates already in the DB for that specific day
                if not ((df['Date'] == t_date) & (df['Count'] > 0)).any() or t_date > latest_db_date:
                    try: eng = translator.translate(txt).lower()
                    except: eng = txt.lower()
                    
                    # Broadened Keyword List
                    if any(w in eng for w in ["intercept", "destroy", "shoot down", "target", "attack", "uav", "drone"]):
                        d_m = re.search(r'(\d+)\s*(?:drone|uav)', eng)
                        m_m = re.search(r'(\d+)\s*(?:missile|ballistic)', eng)
                        
                        val = 1
                        if d_m: val = int(d_m.group(1))
                        elif m_m: val = int(m_m.group(1))
                        
                        threat = "Drone" if "drone" in eng or "uav" in eng else "Missile"
                        loc = "Unspecified"
                        for l in ["eastern", "riyadh", "jazan", "najran", "southern"]:
                            if l in eng: loc = l.capitalize() + " Region"
                        
                        # Only add if it's truly a new record
                        new_entries.append([str(t_date), loc, threat, val])
    except: pass

    if new_entries:
        worksheet.append_rows(new_entries)
        new_df = pd.DataFrame(new_entries, columns=["Date", "Location", "Type", "Count"])
        new_df['Date'] = pd.to_datetime(new_df['Date']).dt.date
        df = pd.concat([df, new_df]).drop_duplicates()
        
    return df

# --- 3. UI ---
df = load_and_update_data()
st.title("🛡️ KSA Regional Defense Monitor")

# Date range: showing everything from the start of the wave
s_d, e_d = st.sidebar.date_input("Analysis Window", [date(2026,3,2), date.today()])

f_df = df[(df['Date'] >= s_d) & (df['Date'] <= e_d)]
total = f_df['Count'].sum()

st.markdown(f"""<div style="background-color:#1F3B4D; padding:20px; border-radius:10px; text-align:center; margin-bottom:20px;">
<h2 style="margin:0; color:white;">Total Interceptions (March 2 - Present)</h2>
<h1 style="margin:0; color:#00CCFF; font-size: 4rem;">{total}</h1>
<p style="color:#A0A0A0; margin:0;">Last Check: {datetime.now().strftime('%H:%M:%S')} (Al Hofuf Time)</p></div>""", unsafe_allow_html=True)

col1, col2 = st.columns(2)
cmap = {"Drone": "#00CCFF", "Missile": "#FF4B4B", "Unspecified": "#4A6274"}

with col1:
    st.plotly_chart(px.bar(f_df.groupby(['Location', 'Type'])['Count'].sum().reset_index(), x="Location", y="Count", color="Type", template="plotly_dark", color_discrete_map=cmap), use_container_width=True)
with col2:
    st.plotly_chart(px.bar(f_df.groupby(['Date', 'Type'])['Count'].sum().reset_index(), x="Date", y="Count", color="Type", template="plotly_dark", color_discrete_map=cmap), use_container_width=True)

st.dataframe(f_df.sort_values(by='Date', ascending=False), use_container_width=True)
