import streamlit as st
import pandas as pd
import plotly.express as px
from ntscraper import Nitter
import re
from deep_translator import GoogleTranslator

st.set_page_config(page_title="KSA Defense Monitor", layout="wide")

# --- 1. THE TRANSLATION DATA ENGINE ---
@st.cache_data(ttl=300)
def fetch_translated_data():
    try:
        scraper = Nitter()
        tweets = scraper.get_tweets("modgovksa", mode='user', number=30)
        
        if not tweets.get('tweets'):
            raise ValueError("Blocked")
            
        results = []
        translator = GoogleTranslator(source='ar', target='en')
        
        for t in tweets['tweets']:
            original_text = t['text']
            
            # Step A: Translate to English
            try:
                eng_text = translator.translate(original_text).lower()
            except:
                eng_text = original_text.lower() # Fallback if translator hiccups
                
            # Step B: Filter using English Keywords
            if any(word in eng_text for word in ["intercept", "destroy", "shoot down"]):
                
                # Step C: Extract exact numbers in English
                # Looks for a number followed by drone/uav or missile
                drone_match = re.search(r'(\d+)\s*(?:drone|uav)', eng_text)
                missile_match = re.search(r'(\d+)\s*(?:missile|ballistic)', eng_text)
                
                count, threat = 1, "Unknown"
                if drone_match: count, threat = int(drone_match.group(1)), "Drone"
                elif missile_match: count, threat = int(missile_match.group(1)), "Missile"
                elif "drone" in eng_text or "uav" in eng_text: threat = "Drone"
                elif "missile" in eng_text: threat = "Missile"
                
                # Step D: Location Mapping
                loc = "Other"
                if "kharj" in eng_text: loc = "Al-Kharj"
                elif "eastern" in eng_text: loc = "Eastern Province"
                elif "riyadh" in eng_text: loc = "Riyadh"
                elif any(city in eng_text for city in ["jazan", "najran", "khamis", "southern"]): 
                    loc = "Southern Border"
                
                if threat != "Unknown":
                    results.append({"Date": pd.to_datetime(t['date']).date(), "Location": loc, "Type": threat, "Count": count})
                    
        return pd.DataFrame(results), "Live Data Connected & Translated 🟢"
    
    except Exception:
        # Fallback Data if X blocks the scraper
        fallback = [
            {"Date": "2026-03-17", "Location": "Eastern Province", "Type": "Drone", "Count": 24},
            {"Date": "2026-03-16", "Location": "Al-Kharj", "Type": "Drone", "Count": 11},
            {"Date": "2026-03-15", "Location": "Riyadh", "Type": "Drone", "Count": 10},
            {"Date": "2026-03-15", "Location": "Southern Border", "Type": "Missile", "Count": 2}
        ]
        return pd.DataFrame(fallback), "Backup Mode Active (Live Feed Blocked by X) ⚠️"

# --- 2. HEADER ---
st.title("🛡️ Saudi Arabia Defense Monitor")
st.caption("Using Translate-Then-Filter Logic")

df, status_message = fetch_translated_data()

if "Backup" in status_message:
    st.warning(status_message)
else:
    st.success(status_message)

# --- 3. DISPLAY ---
if not df.empty:
    df['Date'] = pd.to_datetime(df['Date'])
    df_grouped = df.groupby(['Date', 'Location', 'Type'])['Count'].sum().reset_index()
    df_grouped = df_grouped.sort_values(by=['Date', 'Location'], ascending=[False, True])
    
    col1, col2 = st.columns(2)
    col1.metric("Total Intercepted in Log", df_grouped['Count'].sum())
    col2.metric("Most Targeted Region", df_grouped.groupby('Location')['Count'].sum().idxmax())
    
    st.markdown("---")
    
    fig = px.bar(df_grouped, x="Date", y="Count", color="Type", facet_col="Location",
                 template="plotly_dark", barmode="group",
                 color_discrete_map={"Drone": "#00CCFF", "Missile": "#1F3B4D"})
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df_grouped, use_container_width=True)
