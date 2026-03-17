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
    # 1. Base Historical Data extracted directly from Horizon OSINT Chart (March 2-17, 2026)
    historical_data = [
        {"Date": "2026-03-02", "Location": "Unspecified", "Type": "Unspecified", "Count": 7},
        {"Date": "2026-03-03", "Location": "Unspecified", "Type": "Unspecified", "Count": 10},
        {"Date": "2026-03-04", "Location": "Unspecified", "Type": "Unspecified", "Count": 13},
        {"Date": "2026-03-05", "Location": "Unspecified", "Type": "Unspecified", "Count": 7},
        {"Date": "2026-03-06", "Location": "Unspecified", "Type": "Unspecified", "Count": 11},
        {"Date": "2026-03-07", "Location": "Unspecified", "Type": "Unspecified", "Count": 28},
        {"Date": "2026-03-08", "Location": "Unspecified", "Type": "Unspecified", "Count": 35},
        {"Date": "2026-03-09", "Location": "Unspecified", "Type": "Unspecified", "Count": 25},
        {"Date": "2026-03-10", "Location": "Unspecified", "Type": "Unspecified", "Count": 8},
        {"Date": "2026-03-11", "Location": "Unspecified", "Type": "Unspecified", "Count": 30},
        {"Date": "2026-03-12", "Location": "Unspecified", "Type": "Unspecified", "Count": 50},
        {"Date": "2026-03-13", "Location": "Unspecified", "Type": "Unspecified", "Count": 66},
        {"Date": "2026-03-14", "Location": "Unspecified", "Type": "Unspecified", "Count": 23},
        {"Date": "2026-03-15", "Location": "Unspecified", "Type": "Unspecified", "Count": 31},
        {"Date": "2026-03-16", "Location": "Unspecified", "Type": "Unspecified", "Count": 98},
        {"Date": "2026-03-17", "Location": "Unspecified", "Type": "Unspecified", "Count": 45},
    ]
    df_history = pd.DataFrame(historical_data)
    df_history['Date'] = pd.to_datetime(df_history['Date']).dt.date
    
    # 2. Live Scraper for Today's Data (March 18 onwards)
    live_results = []
    try:
        scraper = Nitter()
        tweets = scraper.get_tweets("modgovksa", mode='user', number=20)
        translator = GoogleTranslator(source='ar', target='en')
        
        if tweets.get('tweets'):
            for t in tweets['tweets']:
                tweet_date = pd.to_datetime(t['date']).date()
                
                # Only process new tweets to prevent duplicating history
                if tweet_date > date(2026, 3, 17): 
                    orig_txt = t['text']
                    try:
                        eng_txt = translator.translate(orig_txt).lower()
                    except:
                        eng_txt = orig_txt.lower()
                    
                    if any(word in eng_txt for word in ["intercept", "destroy", "shoot down"]):
                        drone_match = re.search(r'(\d+)\s*(?:drone|uav)', eng_txt)
                        missile_match = re.search(r'(\d+)\s*(?:missile|ballistic)', eng_txt)
                        
                        count, threat = 1, "Unspecified" # Default to Unspecified to match history
                        if drone_match: count, threat = int(drone_match.group(1)), "Drone"
                        elif missile_match: count, threat = int(missile_match.group(1)), "Missile"
                        elif "drone" in eng_txt or "uav" in eng_txt: threat = "Drone"
                        elif "missile" in eng_txt: threat = "Missile"
                        
                        loc = "Unspecified"
                        if "eastern" in eng_txt: loc = "Eastern Region"
                        elif "riyadh" in eng_txt: loc = "Riyadh"
                        elif "jaz
