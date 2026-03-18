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

# --- 1. Secure Database Connection ---
# FIX: Use @st.cache_resource (not cache_data) for connection objects.
# gspread objects are not serializable — cache_data would crash on Cloud.
# cache_resource creates a single shared instance across all reruns.
@st.cache_resource
def get_worksheet():
    try:
        creds_dict = json.loads(st.secrets["google_json"])
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("KSA_Defense_Data")
        return sh.sheet1
    except Exception as e:
        st.error(f"Critical Database Error: {e}")
        st.stop()

# --- 2. Sheet Initializer (separated from data loader) ---
# FIX: Side effects (writes) must never live inside a @st.cache_data block.
def ensure_headers(worksheet):
    try:
        first_row = worksheet.row_values(1)
        if not first_row:
            worksheet.update('A1', [["Date", "Location", "Type", "Count", "ID"]])
    except Exception:
        pass

# --- 3. Data Synchronization ---
def sync_latest_tweets(worksheet, current_df):
    """Checks for new tweets and updates the Google Sheet safely."""
    new_rows = []
    translator = GoogleTranslator(source='ar', target='en')

    try:
        scraper = Nitter(log_level=1, skip_instance_check=False)
        tweets_data = scraper.get_tweets("modgovksa", mode='user', number=20)
    except Exception as e:
        st.sidebar.warning(f"Scraper unavailable: {e}")
        return False

    try:
        existing_ids = set(current_df['ID'].astype(str)) if not current_df.empty else set()

        for t in tweets_data.get('tweets', []):
            t_id = str(t.get('link', '').split('/')[-1])
            if not t_id or t_id in existing_ids:
                continue

            txt = t.get('text', '')
            t_date = pd.to_datetime(t['date']).date()

            try:
                eng = translator.translate(txt).lower()
            except Exception:
                eng = txt.lower()

            keywords = ["intercept", "destroy", "shoot down", "drone", "uav", "missile"]
            if any(w in eng for w in keywords):
                d_m = re.search(r'(\d+)\s*(?:drone|uav)', eng)
                m_m = re.search(r'(\d+)\s*(?:missile|ballistic)', eng)

                val = 1
                if d_m:
                    val = int(d_m.group(1))
                elif m_m:
                    val = int(m_m.group(1))

                threat = "Drone" if "drone" in eng or "uav" in eng else "Missile"

                loc = "Unspecified"
                for l in ["eastern", "riyadh", "jazan", "najran", "southern", "kharj"]:
                    if l in eng:
                        loc = l.capitalize() + " Region"
                        break

                new_rows.append([str(t_date), loc, threat, val, t_id])

        if new_rows:
            worksheet.append_rows(new_rows)
            st.toast(f"Added {len(new_rows)} new interception records!", icon="🚀")
            return True

    except Exception as e:
        st.sidebar.warning(f"Sync issue: {e}")

    return False

# --- 4. Optimized Data Loader ---
# FIX: load_data now only reads data — no writes, no connection creation.
# The worksheet is passed in from the cached resource, not created here.
@st.cache_data(ttl=300)
def load_data(_worksheet):
    # Underscore prefix on _worksheet tells Streamlit not to hash this arg
    data = _worksheet.get_all_records()
    if not data:
        return pd.DataFrame(columns=["Date", "Location", "Type", "Count", "ID"])

    df = pd.DataFrame(data)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df

# --- 5. Main Execution ---
# FIX: Single call to get_worksheet() via the cached resource.
worksheet = get_worksheet()
ensure_headers(worksheet)
df = load_data(worksheet)

# Sidebar Sync Button
if st.sidebar.button("🔄 Check for Live Updates"):
    if sync_latest_tweets(worksheet, df):
        st.cache_data.clear()
        st.rerun()

# --- UI & Analysis ---
st.title("🛡️ KSA Air Defense Monitor")

# FIX: Guard against empty df before calling .min() — crashes on first run.
min_date = df['Date'].min() if not df.empty else date.today()
date_range = st.sidebar.date_input("Analysis Range", [min_date, date.today()])

if len(date_range) == 2:
    start_d, end_d = date_range
    f_df = df[(df['Date'] >= start_d) & (df['Date'] <= end_d)]

    total_val = f_df['Count'].sum()

    st.markdown(f"""
        <div style="background-color:#0E1117; padding:25px; border-radius:15px; text-align:center; border: 2px solid #00CCFF; margin-bottom: 25px;">
            <p style="color:#888; margin:0; font-size:1.2rem;">Total Interceptions (Filtered Period)</p>
            <h1 style="margin:0; color:#00CCFF; font-size: 5rem;">{total_val}</h1>
        </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    cmap = {"Drone": "#00CCFF", "Missile": "#FF4B4B", "Unspecified": "#4A6274"}

    with col1:
        fig1 = px.bar(f_df.groupby(['Location', 'Type'])['Count'].sum().reset_index(),
                      x="Location", y="Count", color="Type", title="By Region",
                      template="plotly_dark", color_discrete_map=cmap)
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        fig2 = px.area(f_df.groupby(['Date', 'Type'])['Count'].sum().reset_index(),
                       x="Date", y="Count", color="Type", title="Threat Timeline",
                       template="plotly_dark", color_discrete_map=cmap)
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("📋 Raw Intelligence Log")
    st.dataframe(f_df.sort_values(by='Date', ascending=False), use_container_width=True, hide_index=True)

else:
    st.info("Please select a start and end date in the sidebar.")
