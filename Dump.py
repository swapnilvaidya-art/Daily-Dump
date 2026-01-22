# -*- coding: utf-8 -*-

import os
import time
import json
import requests
import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials

start_time = time.time()

# ======================================================
# ENVIRONMENT VARIABLES
# ======================================================
PRABHAT_SECRET_KEY = os.getenv("PRABHAT_SECRET_KEY")
USERNAME = os.getenv("USERNAME")
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON")
METABASE_URL = os.getenv("METABASE_URL")

DAILY_DUMP_QUERY = os.getenv("DAILY_DUMP_QUERY")
DS_ALL_LEAD_STAGES_DOD = os.getenv("DS_ALL_LEAD_STAGES_DOD")

SHEET_ACCESS_KEY = os.getenv("SHEET_ACCESS_KEY")

DAILY_DUMP_SHEET = "Daily Active Dump"
DS_MTD_SHEET = "DS_All_Lead_Stages_MTD"

required_vars = [
    PRABHAT_SECRET_KEY,
    USERNAME,
    SERVICE_ACCOUNT_JSON,
    METABASE_URL,
    DAILY_DUMP_QUERY,
    DS_ALL_LEAD_STAGES_DOD,
    SHEET_ACCESS_KEY
]

missing = [name for name, val in zip(
    [
        "PRABHAT_SECRET_KEY",
        "USERNAME",
        "SERVICE_ACCOUNT_JSON",
        "METABASE_URL",
        "DAILY_DUMP_QUERY",
        "DS_ALL_LEAD_STAGES_DOD",
        "SHEET_ACCESS_KEY"
    ],
    required_vars
) if not val]

if missing:
    raise ValueError(f"❌ Missing environment variables: {missing}")

# ======================================================
# GOOGLE SHEETS AUTH
# ======================================================
service_info = json.loads(SERVICE_ACCOUNT_JSON)

creds = Credentials.from_service_account_info(
    service_info,
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
)

gc = gspread.authorize(creds)

# ======================================================
# METABASE AUTH
# ======================================================
METABASE_HEADERS = {"Content-Type": "application/json"}

res = requests.post(
    METABASE_URL,
    headers=METABASE_HEADERS,
    json={"username": USERNAME, "password": PRABHAT_SECRET_KEY},
    timeout=60
)
res.raise_for_status()

METABASE_HEADERS["X-Metabase-Session"] = res.json()["id"]
print("✅ Metabase session created")

# ======================================================
# UTILITIES
# ======================================================
def fetch_with_retry(url, headers, retries=5, delay=15):
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, headers=headers, timeout=120)
            r.raise_for_status()
            return r
        except Exception as e:
            print(f"[Metabase] Attempt {attempt} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
            else:
                raise


def append_dataframe(worksheet, df):
    """Append-only logic for Daily Active Dump"""
    if df.empty:
        print(f"⚠️ No data for {worksheet.title}")
        return

    existing = worksheet.get_all_values()

    if not existing:
        set_with_dataframe(
            worksheet,
            df,
            include_index=False,
            include_column_header=True
        )
        print(f"📝 First write to {worksheet.title}")
    else:
        start_row = len(existing) + 1
        worksheet.update(
            f"A{start_row}",
            df.values.tolist()
        )
        print(f"➕ Appended {len(df)} rows to {worksheet.title}")


def overwrite_dataframe_preserve_formulas(
    worksheet,
    df,
    data_start_col="A",
    data_end_col="C"
):
    """
    Overwrites ONLY raw data columns (A–C).
    Preserves XLOOKUP / formulas from column D onwards.
    """

    print(f"🔄 Refreshing raw data in {worksheet.title}")

    if df.empty:
        print(f"⚠️ No data for {worksheet.title}")
        return

    total_rows = len(df) + 1  # header included
    clear_range = f"{data_start_col}1:{data_end_col}{total_rows}"

    # Clear only raw data columns
    worksheet.batch_clear([clear_range])
    time.sleep(2)

    # Write header + values
    worksheet.update(
        f"{data_start_col}1",
        [df.columns.tolist()] + df.values.tolist()
    )

    print("✅ Data refreshed — formulas preserved")

# ======================================================
# OPEN GOOGLE SHEET
# ======================================================
sheet = gc.open_by_key(SHEET_ACCESS_KEY)

# ======================================================
# 1️⃣ DAILY ACTIVE DUMP (APPEND)
# ======================================================
print("⏳ Fetching Daily Active Dump data...")
resp_daily = fetch_with_retry(DAILY_DUMP_QUERY, METABASE_HEADERS)
df_daily = pd.DataFrame(resp_daily.json())
print(f"📊 Daily Dump rows: {len(df_daily)}")

ws_daily = sheet.worksheet(DAILY_DUMP_SHEET)
append_dataframe(ws_daily, df_daily)

# ======================================================
# 2️⃣ DS ALL LEAD STAGES MTD (SAFE OVERWRITE A–C)
# ======================================================
print("⏳ Fetching DS All Lead Stages MTD data...")
resp_ds = fetch_with_retry(DS_ALL_LEAD_STAGES_DOD, METABASE_HEADERS)
df_ds = pd.DataFrame(resp_ds.json())
print(f"📊 DS MTD rows: {len(df_ds)}")

ws_ds = sheet.worksheet(DS_MTD_SHEET)
overwrite_dataframe_preserve_formulas(
    worksheet=ws_ds,
    df=df_ds,
    data_start_col="A",
    data_end_col="C"  # 👈 XLOOKUP starts from column D
)

# ======================================================
# TIMER SUMMARY
# ======================================================
elapsed = int(time.time() - start_time)
print(f"⏱ Done in {elapsed} seconds")
print("🎯 Daily Active + DS Lead Stages automation completed successfully!")
