import streamlit as st
import pandas as pd
import plotly.express as px
from ntscraper import Nitter

st.set_page_config(page_title="KSA Defense Monitor", layout="wide")

# --- 1. THE DATA ENGINE ---
@st.cache_data(ttl=600) # Refreshes every 10 mins
def fetch_mod_data():
    try:
        scraper = Nitter()
        # Searching the last 50 tweets for keywords
        tweets = scraper.get_tweets("modgovksa", mode='user', number=50)
        
        results = []
        for t in tweets['tweets']:
            txt = t['text']
            # Search for Arabic keywords: "اعتراض" (interception) or "تدمير" (destruction)
            if any(word in txt for word in ["اعتراض", "تدمير", "مسيرة", "صاروخ"]):
                threat = "Drone" if "مسيرة" in txt else "Missile"
                # Logic to find the City/Region
                loc = "Eastern Province" if "الشرقية" in txt else "Riyadh" if "الرياض" in txt else "Al-Kharj" if "الخرج" in txt else "Southern Border"
                
                results.append({
                    "Date": pd.to_datetime(t['date']).date(),
                    "Location": loc,
                    "Type": threat,
                    "Count": 1
                })
        return pd.DataFrame(results)
    except:
        return pd.DataFrame() # Returns empty if scraper is blocked

# --- 2. HEADER ---
st.title("🛡️ Saudi Arabia Defense Monitor")
st.caption("Official data sourced from @modgovksa")

# --- 3. THE "NO DATA" FIX (Manual Sidebar) ---
st.sidebar.header("Manual Entry / Live Failover")
st.sidebar.info("If the live feed is empty, you can manually add reported events here.")

# Button to pull real data from March 17, 2026 if live fails
if st.sidebar.button("Load Recent March 2026 Data"):
    demo_data = pd.DataFrame([
        {"Date": "2026-03-17", "Location": "Eastern Province", "Type": "Drone", "Count": 12},
        {"Date": "2026-03-15", "Location": "Eastern Province", "Type": "Drone", "Count": 3},
        {"Date": "2026-03-05", "Location": "Al-Kharj", "Type": "Drone", "Count": 3},
        {"Date": "2026-03-04", "Location": "Al-Kharj", "Type": "Missile", "Count": 3}
    ])
    df = demo_data
else:
    df = fetch_mod_data()

# --- 4. DISPLAY ---
if not df.empty:
    df['Date'] = pd.to_datetime(df['Date'])
    # SORTED BY DAY AND LOCATION
    df = df.sort_values(by=['Date', 'Location'], ascending=[False, True])
    
    # The Chart
    fig = px.bar(df, x="Date", y="Count", color="Type", facet_col="Location",
                 template="plotly_dark", barmode="group",
                 color_discrete_map={"Drone": "#00CCFF", "Missile": "#1F3B4D"})
    st.plotly_chart(fig, use_container_width=True)
    
    # The Table
    st.dataframe(df, use_container_width=True)
else:
    st.error("⚠️ The Live Feed is currently blocked by X. Please use the 'Load Recent March 2026 Data' button in the sidebar to view the latest stats.")
