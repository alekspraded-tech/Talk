import os
import requests
from datetime import datetime, timedelta
from supabase import create_client, Client

# --- НАСТРОЙКИ ---
TALK_API_URL = "https://portalwash.ktalk.ru/api/Domain/recordings/v2"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

MANAGERS = {
    "45cd0d96-9fb7-40db-88bf-e1350dc28fe1": {"name": "Алексей Беликов", "email": "a.belikov@portalwash.ru"},
    "3ae59251-f4b6-4b38-9cda-ef6a56cc7127": {"name": "Евгений Журавлев", "email": "e.zhuravlev@portalwash.ru"},
    "01c7dc8e-b715-470e-9766-43c8363a2760": {"name": "Николай Киселев", "email": "n.kiselyov@portalwash.ru"},
    "db318192-e04a-4d2b-b39b-23e77643d4da": {"name": "Александр Прадед", "email": "a.praded@portalwash.ru"}
}

SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("🚀 Запуск синхронизации для всех менеджеров, включая Александра Прадеда...")

date_limit = datetime.utcnow() - timedelta(days=7)
existing_ids = {str(r['id']) for r in supabase.table("talk_records").select("id").execute().data or []}

headers = {"X-Auth-Token": TALK_API_KEY, "Accept": "application/json"}

for page in range(1, 6):
    response = requests.get(TALK_API_URL, headers=headers, params={"page": page, "size": 50})
    records = response.json().get("entities", [])
    if not records: break
    
    to_insert = []
    for record in records:
        # Ищем ID автора в login (надежный способ)
        created_by = record.get("createdBy") or {}
        user_id = created_by.get("login")
        
        if user_id in MANAGERS:
            # Генерация уникального ID для базы (id комнаты + дата)
            raw_id = record.get("id") or record.get("key")
            created_date = record.get("createdDate", "").replace("Z", "").replace(":", "").replace("-", "").replace("T", "_")
            unique_db_id = f"{raw_id}_{created_date}"
            
            if unique_db_id not in existing_ids:
                to_insert.append({
                    "id": unique_db_id,
                    "name": record.get("title", "Без названия"),
                    "created_at": record.get("createdDate"),
                    "manager_email": MANAGERS[user_id]["email"],
                    "view_url": f"https://portalwash.ktalk.ru/recordings/{raw_id}"
                })
    
    if to_insert:
        supabase.table("talk_records").insert(to_insert).execute()
        print(f"✅ Добавлено записей: {len(to_insert)}")

print("🎉 Синхронизация завершена!")
