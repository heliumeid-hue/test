import streamlit as st
import pandas as pd
import plotly.express as px
from ntscraper import Nitter

# 1. UI Setup
st.set_page_config(page_title="KSA Defense Monitor", layout="wide")
st.title("🛡️ Saudi Defense Official Monitor")
st.markdown("---")

# 2. Free Data Scraper
@st.cache_data(ttl=3600) # Only refreshes once per hour to keep it fast
def get_live_data():
    try:
        scraper = Nitter()
        # Pull last 20 tweets from @modgovksa
        tweets = scraper.get_tweets("modgovksa", mode='user', number=20)
        
        results = []
        for t in tweets['tweets']:
            text = t['text']
            # Basic Categorization
            kind = "Drone" if "مسيرة" in text or "drone" in text.lower() else "Missile"
            loc = "Eastern Province" if "الشرقية" in text else "Riyadh" if "الرياض" in text else "Southern Border"
            
            results.append({
                "Date": pd.to_datetime(t['date']).date(),
                "Location": loc,
                "Type": kind,
                "Count": 1
            })
        return pd.DataFrame(results)
    except:
        # Fallback data if the scraper hits a snag
        return pd.DataFrame([{"Date": "2026-03-18", "Location": "Sample Region", "Type": "Drone", "Count": 0}])

# 3. Display Data
df = get_live_data()
df['Date'] = pd.to_datetime(df['Date'])
df = df.sort_values(by=['Date', 'Location'], ascending=[False, True])

# Visuals
fig = px.bar(df, x="Date", y="Count", color="Type", facet_col="Location", 
             template="plotly_dark", color_discrete_map={"Drone": "#00CCFF", "Missile": "#1F3B4D"})
st.plotly_chart(fig, use_container_width=True)

# Table
st.subheader("Official Log Feed")
st.dataframe(df, use_container_width=True)
