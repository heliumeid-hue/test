import streamlit as st
import pandas as pd
import plotly.express as px
from ntscraper import Nitter
import re
from deep_translator import GoogleTranslator
from datetime import date

st.set_page_config(page_title="KSA Defense Monitor", layout="wide", page_icon="🛡️")

# --- 1. HYBRID DATA ENGINE ---
@st.cache_data(ttl=300)
def load_and_merge_data():
    # 1. Base Historical Data: Merging known OSINT logs with the Horizon Line Chart totals
    historical_data = [
        {"Date": "2026-03-02", "Location": "Unspecified", "Type": "Unspecified", "Count": 7},
        {"Date": "2026-03-03", "Location": "Unspecified", "Type": "Unspecified", "Count": 10},
        
        # March 4: Chart total = 13. (3 Known + 10 Unspecified)
        {"Date": "2026-03-04", "Location": "Al-Kharj", "Type": "Missile", "Count": 2},
        {"Date": "2026-03-04", "Location": "Eastern Region", "Type": "Drone", "Count": 1},
        {"Date": "2026-03-04", "Location": "Unspecified", "Type": "Unspecified", "Count": 10},
        
        {"Date": "2026-03-05", "Location": "Unspecified", "Type": "Unspecified", "Count": 7},
        
        # March 6: Chart total = 11. (3 Known + 8 Unspecified)
        {"Date": "2026-03-06", "Location": "Al-Kharj", "Type": "Missile", "Count": 3},
        {"Date": "2026-03-06", "Location": "Unspecified", "Type": "Unspecified", "Count": 8},
        
        {"Date": "2026-03-07", "Location": "Unspecified", "Type": "Unspecified", "Count": 28},
        {"Date": "2026-03-08", "Location": "Unspecified", "Type": "Unspecified", "Count": 35},
        {"Date": "2026-03-09", "Location": "Unspecified", "Type": "Unspecified", "Count": 25},
        {"Date": "2026-03-10", "Location": "Unspecified", "Type": "Unspecified", "Count": 8},
        {"Date": "2026-03-11", "Location": "Unspecified", "Type": "Unspecified", "Count": 30},
        {"Date": "2026-03-12", "Location": "Unspecified", "Type": "Unspecified", "Count": 50},
        
        # March 13: Chart total = 66. (7 Known + 59 Unspecified)
        {"Date": "2026-03-13", "Location": "Eastern Region", "Type": "Drone", "Count": 7},
        {"Date": "2026-03-13", "Location": "Unspecified", "Type": "Unspecified", "Count": 59},
        
        {"Date": "2026-03-14", "Location": "Unspecified", "Type": "Unspecified", "Count": 23},
        
        # March 15: Chart total = 31. (14 Known + 17 Unspecified)
        {"Date": "2026-03-15", "Location": "Riyadh", "Type": "Drone", "Count": 10},
        {"Date": "2026-03-15", "Location": "Eastern Region", "Type": "Drone", "Count": 4},
        {"Date": "2026-03-15", "Location": "Unspecified", "Type": "Unspecified", "Count": 17},
        
        # March 16: Chart total = 98. (70 Known + 28 Unspecified)
        {"Date": "2026-03-16", "Location": "Eastern Region", "Type": "Drone", "Count": 36},
        {"Date": "2026-03-16", "Location": "Riyadh", "Type": "Drone", "Count": 34},
        {"Date": "2026-03-16", "Location": "Unspecified", "Type": "Unspecified", "Count": 28},
        
        # March 17: Chart total = 45. (24 Known + 21 Unspecified)
        {"Date": "2026-03-17", "Location": "Eastern Region", "Type": "Drone", "Count": 24},
        {"Date": "2026-03-17", "Location": "Unspecified", "Type
