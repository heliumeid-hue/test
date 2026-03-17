import streamlit as st
import pandas as pd
import plotly.express as px
from ntscraper import Nitter
import re
from deep_translator import GoogleTranslator
from datetime import date, datetime

st.set_page_config(page_title="KSA Defense Monitor", layout="wide", page_icon="🛡️")

# --- 1. HYBRID DATA ENGINE ---
@st.cache_data(ttl=300)
def load_and_merge_data():
    # 1. Base Historical Data (March 1 - March 17)
    historical_data = [
        {"Date": "2026-03-17", "Location": "Eastern Region", "Type": "Drone", "Count": 24},
        {"Date": "2026-03-16", "Location": "Eastern Region", "Type": "Drone", "Count": 36},
        {"Date": "2026-03-16", "Location": "Riyadh", "Type": "Drone", "Count": 34},
        {"Date": "2026-03-15", "Location": "Riyadh", "Type": "Drone", "Count": 10},
        {"Date": "2026-03-15", "Location": "Eastern Region", "Type": "Drone", "Count": 4},
        {"Date": "2026-03-13", "Location": "Eastern Region", "Type": "Drone", "Count": 7},
        {"Date": "2026-03-06", "Location": "Al-Kharj", "Type": "Missile", "Count": 3},
        {"Date": "2026-03-04", "Location": "Al-Kharj", "Type": "Missile", "Count": 2},
        {"Date": "2026-03-04", "Location": "Eastern Region", "Type": "Drone", "Count": 1},
    ]
    df_history = pd.DataFrame(historical_data)
    df_history['Date'] = pd.to_datetime(df_history['Date']).dt.date
    
    # 2. Live Scraper for Today's Data
    live_results = []
    try:
        scraper = Nitter()
        tweets = scraper.get_tweets("modgovksa", mode='user', number=20)
        translator = GoogleTranslator(source='ar', target='en')
        
        if tweets.get('tweets'):
            for t in tweets['tweets']:
                tweet_date = pd.to_datetime(t['date']).date()
                
                if tweet_date >= date(2026, 3, 17): 
                    orig_txt = t['text']
                    try:
                        eng_txt = translator.translate(orig_txt).lower()
                    except:
                        eng_txt = orig_txt.lower()
                    
                    if any(word in eng_txt for word in ["intercept", "destroy", "shoot down"]):
                        drone_match = re.search(r'(\d+)\s*(?:drone|uav)', eng_txt)
                        missile_match = re.search(r'(\d+)\s*(?:missile|ballistic)', eng_txt)
                        
                        count, threat = 1, "Unknown"
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
                        
                        if threat != "Unknown":
                            live_results.append({"Date": tweet_date, "Location": loc, "Type": threat, "Count": count})
    except:
        pass 

    if live_results:
        df_live = pd.DataFrame(live_results)
        df_combined = pd.concat([df_history, df_live]).drop_duplicates(subset=['Date', 'Location', 'Type', 'Count'])
    else:
        df_combined = df_history
        
    return df_combined

# --- 2. LOAD DATA ---
df = load_and_merge_data()

# --- 3. SIDEBAR (WORKING FILTERS) ---
st.sidebar.header("⚙️ Dashboard Controls")
st.sidebar.markdown("Use these filters to adjust all charts and totals below.")

min_date = date(2026, 3, 1)
max_date = date.today()

# Safeguard added here for the Date Picker!
date_selection = st.sidebar.date_input("Select Date Range", [min_date, max_date], min_value=date(2026, 1, 1), max_value=max_date)
if len(date_selection) == 2:
    start_date, end_date = date_selection
else:
    start_date = end_date = date_selection[0]

all_locations = df['Location'].unique().tolist()
selected_locs = st.sidebar.multiselect("Filter by Area", all_locations, default=all_locations)

all_types = df['Type'].unique().tolist()
selected_types = st.sidebar.multiselect("Filter by Threat Type", all_types, default=all_types)

# --- 4. APPLY FILTERS TO DATA ---
mask = (
    (df['Date'] >= start_date) & 
    (df['Date'] <= end_date) & 
    (df['Location'].isin(selected_locs)) &
    (df['Type'].isin(selected_types))
)
filtered_df = df[mask]

# --- 5. DASHBOARD UI ---
st.title("🛡️ KSA Regional Defense Monitor")
st.caption("Aggregating official reports. Translation-engine active.")

if filtered_df.empty:
    st.warning("No data found for the selected filters.")
else:
    # Grand Total KPI (Fixed the unsafe_allow_html typo here!)
    grand_total = filtered_df['Count'].sum()
    st.markdown(f"""
        <div style="background-color:#1F3B4D; padding:20px; border-radius:10px; text-align:center; margin-bottom:20px;">
            <h2 style="margin:0; color:white;">Total Interceptions (Filtered)</h2>
            <h1 style="margin:0; color:#00CCFF; font-size: 3rem;">{grand_total}</h1>
        </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    
    with col1:
        area_totals = filtered_df.groupby(['Location', 'Type'])['Count'].sum().reset_index()
        fig_area = px.bar(area_totals, x="Location", y="Count", color="Type", 
                          title="Total Interceptions by Area", text="Count",
                          template="plotly_dark", color_discrete_map={"Drone": "#00CCFF", "Missile": "#FF4B4B"})
        fig_area.update_traces(textposition='outside')
        st.plotly_chart(fig_area, use_container_width=True)

    with col2:
        timeline_totals = filtered_df.groupby(['Date', 'Type'])['Count'].sum().reset_index()
        fig_time = px.bar(timeline_totals, x="Date", y="Count", color="Type",
                          title="Interception Timeline",
                          template="plotly_dark", color_discrete_map={"Drone": "#00CCFF", "Missile": "#FF4B4B"})
        st.plotly_chart(fig_time, use_container_width=True)

    st.subheader("Filtered Data Logs")
    clean_table = filtered_df.groupby(['Date', 'Location', 'Type'])['Count'].sum().reset_index()
    clean_table = clean_table.sort_values(by=['Date'], ascending=False).reset_index(drop=True)
    st.dataframe(clean_table, use_container_width=True)
