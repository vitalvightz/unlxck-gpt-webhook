from google.oauth2 import service_account
from googleapiclient.discovery import build
import json

creds = service_account.Credentials.from_service_account_file("clientsecrettallyso.json", scopes=["https://www.googleapis.com/auth/drive"])
drive = build("drive", "v3", credentials=creds)

about = drive.about().get(fields="storageQuota").execute()

print(json.dumps(about, indent=2))