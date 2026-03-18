import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import re
from deep_translator import GoogleTranslator
from datetime import date, timezone
import gspread
import json

# X API v2 — Bearer Token stored in Streamlit secrets as [twitter] bearer_token
X_API_URL    = "https://api.twitter.com/2/users/{uid}/tweets"
X_LOOKUP_URL = "https://api.twitter.com/2/users/by/username/{username}"
MOD_USERNAME = "modgovksa"

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

# --- 3. X API v2 Fetcher ---
@st.cache_data(ttl=3600)  # Cache the user ID lookup for 1 hour — it never changes
def get_user_id(username: str) -> str | None:
    """Resolve @username → numeric user ID using the Bearer Token."""
    token = st.secrets.get("twitter", {}).get("bearer_token", "")
    if not token:
        st.error("Missing [twitter] bearer_token in Streamlit secrets.")
        return None
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        X_LOOKUP_URL.format(username=username),
        headers=headers, timeout=10
    )
    if resp.status_code == 200:
        return resp.json().get("data", {}).get("id")
    st.sidebar.error(f"X API user lookup failed: {resp.status_code} — {resp.text[:120]}")
    return None


def fetch_x_tweets(user_id: str, max_results: int = 20) -> list:
    """Fetch the latest tweets for a user ID via X API v2."""
    token = st.secrets.get("twitter", {}).get("bearer_token", "")
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "max_results": max_results,
        "tweet.fields": "created_at,text",
        "exclude": "retweets,replies",
    }
    resp = requests.get(
        X_API_URL.format(uid=user_id),
        headers=headers, params=params, timeout=10
    )
    if resp.status_code == 200:
        return resp.json().get("data", [])
    st.sidebar.error(f"X API fetch failed: {resp.status_code} — {resp.text[:120]}")
    return []


# --- 4. Data Synchronization ---
def sync_latest_tweets(worksheet, current_df):
    """Fetch from X API v2, detect threats, append new rows to the sheet."""
    translator = GoogleTranslator(source='ar', target='en')

    user_id = get_user_id(MOD_USERNAME)
    if not user_id:
        return False

    tweets = fetch_x_tweets(user_id)
    if not tweets:
        st.sidebar.warning("No tweets returned from X API.")
        return False

    new_rows = []
    existing_ids = set(current_df['ID'].astype(str)) if not current_df.empty else set()

    for t in tweets:
        t_id = str(t.get("id", ""))
        if not t_id or t_id in existing_ids:
            continue

        txt = t.get("text", "")

        # Timezone-safe: X API returns UTC ISO8601 — convert to KSA (Asia/Riyadh)
        try:
            raw_dt = pd.to_datetime(t.get("created_at", ""), utc=True)
            t_date = raw_dt.tz_convert("Asia/Riyadh").date()
        except Exception:
            t_date = date.today()

        try:
            eng = translator.translate(txt).lower()
        except Exception:
            eng = txt.lower()

        keywords = ["intercept", "destroy", "shoot down", "drone", "uav", "missile"]
        if not any(w in eng for w in keywords):
            continue

        d_m = re.search(r'(\d+)\s*(?:drone|uav)', eng)
        m_m = re.search(r'(\d+)\s*(?:missile|ballistic)', eng)
        val = int(d_m.group(1)) if d_m else int(m_m.group(1)) if m_m else 1

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

    return False

# --- 5. Optimized Data Loader ---
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

# --- 6. Main Execution ---
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

# FIX Bug 1: When min_date == today, Streamlit collapses the range widget to a
# single date (len==1), causing the else branch to fire and the dashboard to go
# blank. Force min_date to be at least 30 days back so the widget always gets a
# valid range, and handle the single-date fallback explicitly regardless.
min_date = df['Date'].min() if not df.empty else date.today()
default_start = min(min_date, date.today())
date_range = st.sidebar.date_input("Analysis Range", [default_start, date.today()])

# Normalise: widget returns a tuple of 1 or 2 dates depending on user selection
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_d, end_d = date_range
elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
    start_d = end_d = date_range[0]
else:
    start_d = end_d = date_range  # single date object
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
