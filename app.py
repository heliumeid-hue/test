import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from bs4 import BeautifulSoup
import re
from datetime import date, datetime
import gspread
import json
import time

# SPA article ID range for Feb 2026 onward (confirmed from search results)
# N2526213 = Mar 2, 2026 | N2520000 ≈ early Feb 2026
BACKFILL_START_ID = 2518000   # ~late Jan 2026, safe lower bound
BACKFILL_END_ID   = 2540000   # upper bound — scraper stops at today
SPA_BASE          = "https://www.spa.gov.sa/en/N{}"
CUTOFF_DATE       = date(2026, 2, 1)  # only keep records from Feb 2026 onward

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
KEYWORDS = ["intercept", "destroy", "shoot down", "drone", "uav", "missile", "ballistic"]

st.set_page_config(page_title="KSA Defense Monitor", layout="wide", page_icon="🛡️")

# --- 1. Database Connection ---
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

def ensure_headers(worksheet):
    try:
        if not worksheet.row_values(1):
            worksheet.update('A1', [["Date", "Location", "Type", "Count", "ID"]])
    except Exception:
        pass

# --- 2. SPA Article Parser ---
def parse_spa_article(article_id: int) -> dict | None:
    """Fetch a single SPA article by ID. Returns parsed dict or None."""
    url = SPA_BASE.format(article_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200 or len(resp.text) < 300:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract full article text
        body = soup.find("div", class_=re.compile(r"content|body|article|news", re.I))
        text = body.get_text(" ", strip=True) if body else soup.get_text(" ", strip=True)
        text_lower = text.lower()

        if not any(k in text_lower for k in KEYWORDS):
            return None

        # Extract date — SPA format: "Riyadh, March 10, 2026, SPA --"
        date_match = re.search(
            r'(\w+ \d{1,2},\s*\d{4})',
            text
        )
        if date_match:
            try:
                art_date = datetime.strptime(date_match.group(1).strip(), "%B %d, %Y").date()
            except ValueError:
                art_date = date.today()
        else:
            art_date = date.today()

        if art_date < CUTOFF_DATE:
            return None  # outside our window

        return {"id": str(article_id), "text": text_lower, "date": art_date, "url": url}

    except Exception:
        return None

def extract_row(article: dict) -> list:
    """Convert a parsed article dict into a sheet row."""
    eng = article["text"]

    d_m = re.search(r'\((\d+)\)\s*(?:drone|uav)|(\d+)\s*(?:drone|uav)', eng)
    m_m = re.search(r'\((\d+)\)\s*(?:missile|ballistic)|(\d+)\s*(?:missile|ballistic)', eng)
    drone_count = int(d_m.group(1) or d_m.group(2)) if d_m else 0
    missile_count = int(m_m.group(1) or m_m.group(2)) if m_m else 0

    if drone_count and missile_count:
        threat = "Mixed"
        val = drone_count + missile_count
    elif drone_count:
        threat = "Drone"
        val = drone_count
    elif missile_count:
        threat = "Missile"
        val = missile_count
    else:
        threat = "Drone" if "drone" in eng or "uav" in eng else "Missile"
        val = 1

    loc = "Unspecified"
    loc_map = {
        "eastern": "Eastern Region", "riyadh": "Riyadh Region",
        "jazan": "Jazan Region", "najran": "Najran Region",
        "southern": "Southern Region", "kharj": "Kharj Region",
        "shaybah": "Eastern Region", "ras tanura": "Eastern Region",
        "sultan air base": "Riyadh Region",
    }
    for key, label in loc_map.items():
        if key in eng:
            loc = label
            break

    return [str(article["date"]), loc, threat, val, article["id"]]

# --- 3. Sync (latest articles only) ---
def sync_latest(worksheet, current_df):
    """Check the most recent ~100 article IDs for new interceptions."""
    existing_ids = set(current_df['ID'].astype(str)) if not current_df.empty else set()

    # Find highest known ID to start from
    if existing_ids:
        try:
            max_known = max(int(i) for i in existing_ids if i.isdigit())
            start_id = max_known + 1
        except ValueError:
            start_id = BACKFILL_END_ID - 100
    else:
        start_id = BACKFILL_END_ID - 100

    new_rows = []
    checked = 0
    consecutive_misses = 0

    for article_id in range(start_id, start_id + 500):
        article = parse_spa_article(article_id)
        checked += 1
        if article:
            consecutive_misses = 0
            if article["id"] not in existing_ids:
                new_rows.append(extract_row(article))
        else:
            consecutive_misses += 1
            if consecutive_misses > 80:
                break  # ID range exhausted
        time.sleep(0.15)

    if new_rows:
        worksheet.append_rows(new_rows)
        st.toast(f"Added {len(new_rows)} new interception records!", icon="🚀")
        return True

    st.sidebar.info(f"Checked {checked} articles — no new interceptions found.")
    return False

# --- 4. Backfill (one-time, paginate full Feb 2026 onward range) ---
def run_backfill(worksheet, current_df):
    """Scan full ID range from Feb 2026 onward. Shows live progress."""
    existing_ids = set(current_df['ID'].astype(str)) if not current_df.empty else set()
    new_rows = []

    progress = st.sidebar.progress(0, text="Starting backfill…")
    status   = st.sidebar.empty()
    total    = BACKFILL_END_ID - BACKFILL_START_ID
    found    = 0

    for i, article_id in enumerate(range(BACKFILL_START_ID, BACKFILL_END_ID)):
        pct = i / total
        progress.progress(pct, text=f"Scanning N{article_id}… ({found} found)")

        if str(article_id) in existing_ids:
            continue

        article = parse_spa_article(article_id)
        if article:
            row = extract_row(article)
            new_rows.append(row)
            existing_ids.add(article["id"])
            found += 1
            status.info(f"Found: {article['date']} — {row[2]} ({row[1]})")

            # Batch write every 10 records
            if len(new_rows) % 10 == 0:
                worksheet.append_rows(new_rows[-10:])

        time.sleep(0.2)  # be polite to SPA server

    # Write any remaining
    remainder = len(new_rows) % 10
    if remainder:
        worksheet.append_rows(new_rows[-remainder:])

    progress.progress(1.0, text="Backfill complete!")
    status.success(f"Backfill done — {found} interception records added.")
    return found > 0

# --- 5. Data Loader ---
@st.cache_data(ttl=300)
def load_data(_worksheet):
    data = _worksheet.get_all_records()
    if not data:
        return pd.DataFrame(columns=["Date", "Location", "Type", "Count", "ID"])
    df = pd.DataFrame(data)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df

# --- 6. Main Execution ---
worksheet = get_worksheet()
ensure_headers(worksheet)
df = load_data(worksheet)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Check for Live Updates"):
    if sync_latest(worksheet, df):
        st.cache_data.clear()
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("**One-time setup**")
if st.sidebar.button("📥 Backfill Feb 2026 → Now"):
    if run_backfill(worksheet, df):
        st.cache_data.clear()
        st.rerun()

# --- UI & Analysis ---
st.title("🛡️ KSA Air Defense Monitor")

min_date = df['Date'].min() if not df.empty else date.today()
default_start = min(min_date, date.today())
date_range = st.sidebar.date_input("Analysis Range", [default_start, date.today()])

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_d, end_d = date_range
elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
    start_d = end_d = date_range[0]
else:
    start_d = end_d = date_range

f_df = df[(df['Date'] >= start_d) & (df['Date'] <= end_d)]
total_val = f_df['Count'].sum()

st.markdown(f"""
    <div style="background-color:#0E1117; padding:25px; border-radius:15px; text-align:center; border: 2px solid #00CCFF; margin-bottom: 25px;">
        <p style="color:#888; margin:0; font-size:1.2rem;">Total Interceptions (Filtered Period)</p>
        <h1 style="margin:0; color:#00CCFF; font-size: 5rem;">{total_val}</h1>
    </div>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)
cmap = {"Drone": "#00CCFF", "Missile": "#FF4B4B", "Mixed": "#AA44FF", "Unspecified": "#4A6274"}

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
