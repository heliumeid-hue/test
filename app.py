import streamlit as st
import pandas as pd
import plotly.express as px
from ntscraper import Nitter
import re # This is the new tool that "reads" the numbers

st.set_page_config(page_title="KSA Defense Monitor", layout="wide")

# --- 1. THE SMART DATA ENGINE ---
@st.cache_data(ttl=600)
def fetch_mod_data():
    try:
        scraper = Nitter()
        tweets = scraper.get_tweets("modgovksa", mode='user', number=50)
        
        results = []
        for t in tweets['tweets']:
            txt = t['text']
            
            # Step 1: Is this an interception report?
            if any(word in txt for word in ["اعتراض", "تدمير", "إسقاط"]):
                
                # Step 2: Extract the exact NUMBER of projectiles using Regex
                # Looks for digits (\d+) right before or after the drone/missile words
                drone_match = re.search(r'(\d+)\s*(?:مسيّرة|مسيرة|طائرة)', txt)
                missile_match = re.search(r'(\d+)\s*(?:صاروخ|صواريخ|باليستي)', txt)
                
                count = 1 # Default to 1 if no specific number is mentioned
                threat = "Unknown"
                
                if drone_match:
                    count = int(drone_match.group(1))
                    threat = "Drone"
                elif missile_match:
                    count = int(missile_match.group(1))
                    threat = "Missile"
                elif "مسيرة" in txt or "مسيّرة" in txt:
                    threat = "Drone"
                elif "صاروخ" in txt:
                    threat = "Missile"
                
                # Step 3: Exact Location Mapping
                loc = "Other / Unspecified"
                if "الخرج" in txt: loc = "Al-Kharj"
                elif "الشرقية" in txt: loc = "Eastern Province"
                elif "الرياض" in txt: loc = "Riyadh"
                elif "جازان" in txt: loc = "Jazan"
                elif "نجران" in txt: loc = "Najran"
                elif "خميس مشيط" in txt: loc = "Khamis Mushait"
                
                if threat != "Unknown":
                    results.append({
                        "Date": pd.to_datetime(t['date']).date(),
                        "Location": loc,
                        "Type": threat,
                        "Count": count # Now uses the real extracted number (e.g., 11)
                    })
                    
        return pd.DataFrame(results)
    except:
        return pd.DataFrame()

# --- 2. HEADER ---
st.title("🛡️ Saudi Arabia Defense Monitor")
st.caption("Live, parsed data from @modgovksa")

df = fetch_mod_data()

# --- 3. DISPLAY ---
if not df.empty:
    df['Date'] = pd.to_datetime(df['Date'])
    
    # Aggregate data: If there are multiple tweets on the same day for the same location, add them up
    df_grouped = df.groupby(['Date', 'Location', 'Type'])['Count'].sum().reset_index()
    df_grouped = df_grouped.sort_values(by=['Date', 'Location'], ascending=[False, True])
    
    # KPI Row
    st.markdown("### 📊 Latest Real-Time Totals")
    col1, col2 = st.columns(2)
    col1.metric("Total Intercepted in Feed", df_grouped['Count'].sum())
    col2.metric("Most Active Region", df_grouped.groupby('Location')['Count'].sum().idxmax())
    
    st.markdown("---")
    
    # The Chart
    fig = px.bar(df_grouped, x="Date", y="Count", color="Type", facet_col="Location",
                 template="plotly_dark", barmode="group",
                 color_discrete_map={"Drone": "#00CCFF", "Missile": "#1F3B4D"},
                 title="Interceptions by Date and Region")
    st.plotly_chart(fig, use_container_width=True)
    
    # The Table
    st.subheader("Extracted Data Log")
    st.dataframe(df_grouped, use_container_width=True)
else:
    st.error("Live feed currently empty or blocked by X. Try refreshing in a few minutes.")
