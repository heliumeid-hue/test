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
        # Load the secret JSON key from Streamlit Secrets
        creds_dict = json.loads(st.secrets["google_json"])
        bot_email = creds_dict.get("client_email")
        
        # Authorize and open the sheet
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("KSA_Defense_Data")
        return sh.sheet1
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"❌ Spreadsheet 'KSA_Defense_Data' not found! Make sure it is named exactly that and shared with: {bot_email}")
        st.stop()
    except Exception as e:
        st.error(f"❌ Database Connection Error: {e}")
        st.info("Check if Google Sheets API and Google Drive API are both ENABLED in Google Cloud Console.")
        st.stop()

# --- 2. HYBRID DATABASE ENGINE ---
@st.cache_data(ttl=300)
def load_and_update_data():
    worksheet = connect_to_database()
    
    # 1. Pull existing data
    existing_data = worksheet.get_all_records()
    df = pd.DataFrame(existing_data)
    
    # 2. IF SHEET IS EMPTY: Inject the 487 Total Historical Baseline
    if df.empty:
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
        worksheet.append_rows(baseline_data)
        existing_data = worksheet.get_all_records()
        df = pd.DataFrame(existing_data)

    df['Date'] = pd.to_datetime(df['Date']).dt.date
    latest_date_in_db = df['Date'].max()

    # 3. LIVE SCRAPER: Bridge the gap from last save to Today
    new_records_to_save = []
    try:
        scraper = Nitter()
        # Increased number to 100 to catch gaps if app is closed for days
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

    # 4. SAVE NEW FINDINGS TO GOOGLE SHEETS
    if len(new_records_to_save) > 0:
        worksheet.append_rows(new_records_to_save)
        new_df = pd.DataFrame(new_records_to_save, columns=["Date", "Location", "Type", "Count"])
        new_df['Date'] = pd.to_datetime(new_df['Date']).dt.date
        df = pd.concat([df, new_df]).drop_duplicates()
        
    return df

# --- 3. LOAD DATA ---
df = load_and_update_data()

# --- 4. SIDEBAR FILTERS ---
st.sidebar.header("⚙️ Dashboard Controls")

min_date = date(2026, 3, 2) 
max_date = date.today()

# Date picker with safeguard
date_sel = st.sidebar.date_input("Select Date Range", [min_date, max_date], min_value=min_date, max_value=max_date)
if isinstance(date_sel, list) or isinstance(date_sel, tuple):
    start_date = date_sel[0]
    end_date = date_sel[1] if len(date_sel) > 1 else start_date
else:
    start_date = end_date = date_sel

all_locations = df['Location'].unique().tolist()
selected_locs = st.sidebar.multiselect("Filter by Area", all_locations, default=all_locations)

all_types = df['Type'].unique().tolist()
selected_types = st.sidebar.multiselect("Filter by Threat Type", all_types, default=all_types)

# --- 5. APPLY FILTERS ---
mask = (
    (df['Date'] >= start_date) & 
    (df['Date'] <= end_date) & 
    (df['Location'].isin(selected_locs)) &
    (df['Type'].isin(selected_types))
)
filtered_df = df[mask]

# --- 6. DASHBOARD UI ---
st.title("🛡️ KSA Regional Defense Monitor")

if filtered_df.empty:
    st.warning("No data found for the selected filters.")
else:
    # Grand Total KPI
    grand_total = filtered_df['Count'].sum()
    st.markdown(f"""
        <div style="background-color:#1F3B4D; padding:20px; border-radius:10px; text-align:center; margin-bottom:20px;">
            <h2 style="margin:0; color:white;">Total Interceptions (Database + Live)</h2>
            <h1 style="margin:0; color:#00CCFF; font-size: 3.5rem;">{grand_total}</h1>
        </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    color_map = {"Drone": "#00CCFF", "Missile": "#FF4B4B", "Unspecified": "#4A6274"}
    
    with col1:
        area_totals = filtered_df.groupby(['Location', 'Type'])['Count'].sum().reset_index()
        fig_area = px.bar(area_totals, x="Location", y="Count", color="Type", 
                          title="Interceptions by Geography", text="Count",
                          template="plotly_dark", color_discrete_map=color_map)
        fig_area.update_traces(textposition='outside')
        st.plotly_chart(fig_area, use_container_width=True)

    with col2:
        timeline_totals = filtered_df.groupby(['Date', 'Type'])['Count'].sum().reset_index()
        fig_time = px.bar(timeline_totals, x="Date", y="Count", color="Type",
                          title="Daily Threat Volume",
                          template="plotly_dark", color_discrete_map=color_map)
        st.plotly_chart(fig_time, use_container_width=True)

    st.subheader("📝 Database Record Logs")
    clean_table = filtered_df.sort_values(by=['Date'], ascending=False).reset_index(drop=True)
    st.dataframe(clean_table, use_container_width=True)
