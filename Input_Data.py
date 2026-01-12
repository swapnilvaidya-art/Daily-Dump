
import os
import time
import json
import requests
import pandas as pd
import gspread
from datetime import datetime
from zoneinfo import ZoneInfo
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials

# -------------------- START TIMER --------------------
start_time = time.time()

# -------------------- ENV & AUTH --------------------
sec = os.getenv("PRABHAT_SECRET_KEY")
User_name = os.getenv("USERNAME")
service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
MB_URl = os.getenv("METABASE_URL")
QUERY_URL = os.getenv("DAILY_INPUT_QUERY")
SAK = os.getenv("SHEET_ACCESS_KEY")
TARGET_SHEET = "Helper Call Dump"
SAK = os.getenv("SHEET_ACCESS_KEY")

if not sec or not service_account_json:
    raise ValueError("❌ Missing environment variables. Check GitHub secrets.")

# Parse service account credentials
service_info = json.loads(service_account_json)
creds = Credentials.from_service_account_info(
    service_info,
    scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
)
gc = gspread.authorize(creds)

# -------------------- CONFIG --------------------
METABASE_HEADERS = {'Content-Type': 'application/json'}

# Create Metabase session
res = requests.post(
    MB_URl,
    headers={"Content-Type": "application/json"},
    json={"username": User_name, "password": sec}
)
res.raise_for_status()
token = res.json()['id']
METABASE_HEADERS['X-Metabase-Session'] = token
print("✅ Metabase session created")

# -------------------- UTILITIES --------------------
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

def safe_update_range(worksheet, df, data_range, retries=5, delay=20):
    print(f"🔄 Preparing to update {worksheet.title} ({data_range})")

    backup_data = worksheet.get(data_range)
    success = False

    for attempt in range(1, retries + 1):
        try:
            set_with_dataframe(worksheet, df, include_index=False, include_column_header=True, resize=False)
            print(f"✅ Successfully updated {worksheet.title}")
            success = True
            break
        except Exception as e:
            print(f"[Sheets] Attempt {attempt} failed for {worksheet.title}: {e}")
            if attempt < retries:
                time.sleep(delay)
            else:
                print(f"❌ All attempts failed for {worksheet.title}. Restoring backup...")
                worksheet.update(data_range, backup_data)
                print(f"✅ Backup restored for {worksheet.title}")
                raise

    return success

# -------------------- MAIN LOGIC --------------------
print("Fetching ONLY Input query...")

# Fetch data
input_response = fetch_with_retry(QUERY_URL, METABASE_HEADERS)
df_Input = pd.DataFrame(input_response.json())

# Columns for Input
common_cols = [
    'lead_created_on', 'modified_on', 'prospect_email', 'prospect_stage',
    'mx_prospect_status', 'crm_user_role', 'sales_user_email', 'mx_utm_medium',
    'mx_utm_source', 'mx_lead_quality_grade', 'mx_lead_inherent_intent',
    'mx_priority_status', 'mx_organic_inbound', 'lead_last_call_status',
    'mx_city', 'event', 'current_stage', 'previous_stage',
    'mx_identifer', 'mx_phoenix_identifer'
]

df_Input = df_Input[common_cols + ['call_type', 'duration']]

print("Connecting to Google Sheets...")

sheet = gc.open_by_key(SAK)
ws_input = sheet.worksheet("Helper Call Dump")

# Update Input sheet safely
print("Updating Helper Call Dump...")
safe_update_range(ws_input, df_Input, "A:X")


# -------------------- TIMER SUMMARY --------------------
end_time = time.time()
elapsed_time = end_time - start_time
mins, secs = divmod(elapsed_time, 60)
print(f"⏱ Total time taken: {int(mins)}m {int(secs)}s")

print("🎯 Only Input Query executed successfully!")

