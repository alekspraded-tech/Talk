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
    
    payload = []
    current_url = TALK_API_URL
    page_number = 1
    
    print("🤖 Запуск полной синхронизации звонков по ID менеджеров...")
    
    while current_url:
        print(f"Сканируем страницу #{page_number}...")
        try:
            response = requests.get(current_url, headers=headers)
            if response.status_code != 200:
                print(f"🛑 Ошибка на странице #{page_number}: Код {response.status_code}")
                break

            data = response.json()
            records = data.get("entities", [])
            print(f"-> Найдено записей на странице: {len(records)}")
            
            for record in records:
                if not isinstance(record, dict):
                    continue
                    
                created_by = record.get("createdBy", {})
                if not isinstance(created_by, dict):
                    continue
                    
                # В вашей системе ID создателя лежит в поле 'login'
                user_id = created_by.get("login")
                
                # Если этот ID принадлежит нашему менеджеру — забираем встречу
                if user_id in MANAGERS:
                    record_id = record.get("id")
                    view_url = f"https://portalwash.ktalk.ru/recordings/{record_id}"
                    manager_info = MANAGERS[user_id]
                    
                    payload.append({
                        "id": str(record_id),
                        "name": record.get("title") or "Встреча без названия",
                        "created_at": record.get("createdDate"),
                        "manager_email": manager_info["email"], # Пишем нормальный email для базы/сайта
                        "view_url": view_url
                    })
            
            # Листаем страницу дальше
            next_token = data.get("nextPageToken")
            if next_token:
                current_url = f"{TALK_API_URL}?pageToken={next_token}"
                page_number += 1
            else:
                current_url = None
                
        except Exception as e:
            print(f"🛑 Системная ошибка на странице #{page_number}: {e}")
            break
            
    if not payload:
        print("\nℹ️ Синхронизация завершена. Звонков от Беликова, Журавлева или Киселевой не найдено.")
        return

    print(f"\n🚀 Найдено звонков целевых менеджеров: {len(payload)}. Отправка в Supabase...")
    try:
        result = supabase.table("talk_records").upsert(payload, on_conflict="id").execute()
        print("✅ ВСЕ ДАННЫЕ УСПЕШНО ЗАПИСАНЫ В SUPABASE!")
    except Exception as e:
        print(f"🛑 Ошибка записи в Supabase: {e}")

if __name__ == "__main__":
    sync_talk_to_supabase()
