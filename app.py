import streamlit as st
import pandas as pd
import plotly.express as px
from ntscraper import Nitter

st.set_page_config(page_title="KSA Defense Monitor", layout="wide")

# --- 1. DATA COLLECTION ---
@st.cache_data(ttl=300) # Refreshes every 5 minutes
def fetch_data():
    try:
        scraper = Nitter()
        # We pull 50 tweets to make sure we don't miss anything
        tweets = scraper.get_tweets("modgovksa", mode='user', number=50)
        
        results = []
        for t in tweets['tweets']:
            txt = t['text']
            # Improved detection: looks for any mention of drones/missiles/interception
            if any(word in txt for word in ["اعتراض", "تدمير", "مسيرة", "صاروخ", "drone", "missile"]):
                # Determine type
                threat = "Drone" if ("مسيرة" in txt or "drone" in txt.lower()) else "Missile"
                # Determine Location
                loc = "Eastern Province" if "الشرقية" in txt else "Riyadh" if "الرياض" in txt else "Southern Border"
                
                results.append({
                    "Date": pd.to_datetime(t['date']).date(),
                    "Location": loc,
                    "Type": threat,
                    "Count": 1
                })
        return pd.DataFrame(results)
    except:
        return pd.DataFrame()

# --- 2. THE DASHBOARD ---
st.title("🛡️ Saudi Defense Official Monitor")
live_df = fetch_data()

# Manual Data entry (If the scraper is blocked or empty)
st.sidebar.header("Manual Data Override")
if st.sidebar.checkbox("Add Manual Data (If Live Feed is empty)"):
    m_date = st.sidebar.date_input("Date")
    m_loc = st.sidebar.selectbox("Location", ["Eastern Province", "Riyadh", "Southern Border", "Jazan"])
    m_type = st.sidebar.radio("Type", ["Drone", "Missile"])
    m_count = st.sidebar.number_input("Count", min_value=1, value=1)
    
    manual_df = pd.DataFrame([{"Date": m_date, "Location": m_loc, "Type": m_type, "Count": m_count}])
    df = pd.concat([live_df, manual_df], ignore_index=True)
else:
    df = live_df

# --- 3. DISPLAY ---
if not df.empty:
    df['Date'] = pd.to_datetime(df['Date'])
    # SORTED BY DAY AND LOCATION
    df = df.sort_values(by=['Date', 'Location'], ascending=[False, True])
    
    # Chart
    fig = px.bar(df, x="Date", y="Count", color="Type", facet_col="Location",
                 template="plotly_dark", barmode="group",
                 color_discrete_map={"Drone": "#00CCFF", "Missile": "#1F3B4D"})
    st.plotly_chart(fig, use_container_width=True)
    
    # Table
    st.dataframe(df, use_container_width=True)
else:
    st.error("No data found in the last 50 tweets. Use the Sidebar to add data manually.")
