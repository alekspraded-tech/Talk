import os
import requests
from datetime import datetime, timedelta
from supabase import create_client, Client

# --- НАСТРОЙКИ ---
TALK_API_URL = "https://portalwash.ktalk.ru/api/Domain/recordings/v2"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

# Сюда добавим ID, если диагностика покажет новые
MANAGERS = {
    "45cd0d96-9fb7-40db-88bf-e1350dc28fe1": {"name": "Алексей Беликов", "email": "a.belikov@portalwash.ru"},
    "3ae59251-f4b6-4b38-9cda-ef6a56cc7127": {"name": "Евгений Журавлев", "email": "e.zhuravlev@portalwash.ru"},
    "01c7dc8e-b715-470e-9766-43c8363a2760": {"name": "Николай Киселев", "email": "n.kiselyov@portalwash.ru"}
}

SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("🤖 Запуск синхронизации с расширенным поиском авторов...")

date_limit = datetime.utcnow() - timedelta(days=7)

# Загружаем текущие ID из базы
existing_ids = set()
try:
    response = supabase.table("talk_records").select("id").execute()
    if response.data:
        existing_ids = {str(row["id"]) for row in response.data}
except Exception as e:
    print(f"⚠️ База пуста или недоступна: {e}")

headers = {"X-Auth-Token": TALK_API_KEY, "Accept": "application/json"}
collected_records = []

for page in range(1, 6):
    print(f"📦 Сканирование страницы {page}...")
    response = requests.get(TALK_API_URL, headers=headers, params={"page": page, "size": 50})
    if response.status_code != 200: break
    
    records = response.json().get("entities", [])
    if not records: break
    
    for record in records:
        # Пытаемся найти ID автора в разных местах
        created_by = record.get("createdBy") or {}
        # Проверяем основной login, затем запасные поля
        user_id = created_by.get("login") or record.get("ownerId") or record.get("creatorId")
        
        # Диагностика: если запись выглядит важной, но менеджер не найден
        if user_id not in MANAGERS:
            # Можно раскомментировать принт ниже для тотальной отладки
            # print(f"DEBUG: Пропущена запись '{record.get('title')}', автор ID: {user_id}")
            continue
            
        # Проверка даты
        created_date_str = record.get("createdDate", "").replace("Z", "").split(".")[0]
        try:
            if datetime.strptime(created_date_str, "%Y-%m-%dT%H:%M:%S") < date_limit:
                continue
        except: continue
        
        # Уникальный ID для базы (id комнаты + дата)
        raw_id = str(record.get("id"))
        unique_db_id = f"{raw_id}_{created_date_str.replace(':', '').replace('-', '')}"
        
        if unique_db_id in existing_ids: continue
        
        manager_info = MANAGERS[user_id]
        collected_records.append({
            "id": unique_db_id,
            "name": record.get("title") or "Встреча без названия",
            "created_at": record.get("createdDate"),
            "manager_email": manager_info["email"],
            "view_url": f"https://portalwash.ktalk.ru/recordings/{raw_id}"
        })

# Фильтрация дублей в рамках одного запуска
unique_payload = {item["id"]: item for item in collected_records}.values()
final_payload = list(unique_payload)

if final_payload:
    print(f"🚀 Загружаем {len(final_payload)} новых встреч в базу...")
    supabase.table("talk_records").insert(final_payload).execute()
    print("✅ Успешно!")
else:
    print("ℹ️ Новых встреч не найдено.")
