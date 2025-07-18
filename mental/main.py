import os
import json
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Decode service account credentials from environment variable
creds_b64 = os.getenv("GOOGLE_CREDS_B64")
creds_json = json.loads(base64.b64decode(creds_b64))

# Authenticate
creds = service_account.Credentials.from_service_account_info(
    creds_json, scopes=["https://www.googleapis.com/auth/drive"]
)
drive = build("drive", "v3", credentials=creds)

# Query storage quota
about = drive.about().get(fields="storageQuota").execute()
print(json.dumps(about, indent=2))