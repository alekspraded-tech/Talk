import os
import requests
from supabase import create_client, Client

# --- НАСТРОЙКИ КОНТУР.ТОЛК ---
TALK_API_URL = "https://portalwash.ktalk.ru/api/Domain/recordings/v2"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

# Маппинг внутренних ID Толка на читаемые данные для дашборда
MANAGERS = {
    "45cd0d96-9fb7-40db-88bf-e1350dc28fe1": {"name": "Алексей Беликов", "email": "a.belikov@portalwash.ru"},
    "3ae59251-f4b6-4b38-9cda-ef6a56cc7127": {"name": "Евгений Журавлев", "email": "e.zhuravlev@portalwash.ru"},
    "01c7dc8e-b715-470e-9766-43c8363a2760": {"name": "Юлия Киселева", "email": "n.kiselyov@portalwash.ru"}
}

# --- НАСТРОЙКИ SUPABASE ---
SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_KEY:
    print("🛑 Ошибка: Ключ SUPABASE_SERVICE_KEY не найден в GitHub Secrets!")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def sync_talk_to_supabase():
    headers = {
        "X-Auth-Token": TALK_API_KEY,
        "Accept": "application/json"
    }
    
    print("🤖 Запуск быстрой синхронизации свежих звонков (только 1-я страница)...")
    
    try:
        # Делаем запрос только один раз — забираем самые последние 30 записей компании
        response = requests.get(TALK_API_URL, headers=headers)
        if response.status_code != 200:
            print(f"🛑 Ошибка API: Код {response.status_code}")
            return

        data = response.json()
        records = data.get("entities", [])
        print(f"-> Проверяем {len(records)} последних записей в Толке...")
        
        payload = []
        for record in records:
            if not isinstance(record, dict):
                continue
                
            created_by = record.get("createdBy", {})
            if not isinstance(created_by, dict):
                continue
                
            user_id = created_by.get("login")
            
            if user_id in MANAGERS:
                record_id = record.get("id")
                view_url = f"https://portalwash.ktalk.ru/recordings/{record_id}"
                manager_info = MANAGERS[user_id]
                
                payload.append({
                    "id": str(record_id),
                    "name": record.get("title") or "Встреча без названия",
                    "created_at": record.get("createdDate"),
                    "manager_email": manager_info["email"],
                    "view_url": view_url
                })
                
        if not payload:
            print("ℹ️ Свежих звонков от Беликова, Журавлева или Киселевой за сегодня не найдено.")
            return

        print(f"🚀 Найдено свежих звонков: {len(payload)}. Отправка в Supabase...")
        result = supabase.table("talk_records").upsert(payload, on_conflict="id").execute()
        print("✅ Данные успешно обновлены!")
            
    except Exception as e:
        print(f"🛑 Системная ошибка: {e}")
