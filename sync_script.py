import os
import requests
from supabase import create_client, Client

TALK_API_URL = "https://portalwash.ktalk.ru/api/Domain/recordings/v2"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

# Ключ от Supabase
SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

headers = {"X-Auth-Token": TALK_API_KEY, "Accept": "application/json"}

print(f"🕵️ Ищем записи по вашим ссылкам...")

# ID из ваших ссылок (последняя часть URL)
target_ids = ["LQkycroHPleWOb7J5M5a", "GQc6RuIfwq7MZ2Moc50E"]

for page in range(1, 4):
    response = requests.get(TALK_API_URL, headers=headers, params={"page": page, "size": 50})
    records = response.json().get("entities", [])
    
    for record in records:
        if record.get("id") in target_ids:
            created_by = record.get("createdBy") or {}
            print(f"--- НАЙДЕНО ---")
            print(f"Встреча: {record.get('title')}")
            print(f"ID записи: {record.get('id')}")
            print(f"АВТОР (createdBy): {created_by}")
            print(f"Владелец (owner): {record.get('owner')}")
            print(f"----------------")
