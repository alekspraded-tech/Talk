import requests
from supabase import create_client, Client

# --- НАСТРОЙКИ КОНТУР.ТОЛК ---
TALK_API_URL = "https://portalwash.ktalk.ru/api/v1"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

TARGET_EMAILS = [
    "a.belikov@portalwash.ru",
    "e.zhuravlev@portalwash.ru",
    "n.kiselyov@portalwash.ru"
]

# --- НАСТРОЙКИ SUPABASE ---
# Скопируйте эти данные из настроек вашего проекта Supabase (Project Settings -> API)
SUPABASE_URL = "https://your-project-id.supabase.co" 
SUPABASE_KEY = "your-service-role-or-anon-key" 

# Инициализация клиента Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def sync_talk_to_supabase():
    print("Получение данных из Контур.Толк...")
    headers = {
        "X-Auth-Token": TALK_API_KEY,
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(f"{TALK_API_URL}/records", headers=headers)
        if response.status_code != 200:
            print(f"Ошибка получения данных из Толка: {response.status_code}")
            return

        data = response.json()
        records = data.get('items', data) if isinstance(data, dict) else data
        
        # Переводим целевые email в нижний регистр для корректного сравнения
        target_emails_lower = [email.lower() for email in TARGET_EMAILS]
        
        payload = []
        for record in records:
            owner = record.get('owner', {})
            owner_email = owner.get('email', '').lower()
            
            # Фильтруем: только нужные менеджеры
            if owner_email in target_emails_lower:
                payload.append({
                    "id": record.get("id"),
                    "name": record.get("name", "Встреча без названия"),
                    "created_at": record.get("createdAt"),
                    "manager_email": owner_email,
                    "view_url": record.get("url") or record.get("viewUrl")
                })
        
        if not payload:
            print("Новых записей от указанных менеджеров в Толке не найдено.")
            return

        print(f"Найдено {len(payload)} записей для отправки в Supabase.")
        
        # Отправляем данные в Supabase с использованием логики UPSERT
        # Если запись с таким ID уже есть, она обновится, если нет — создастся новая
        result = supabase.table("talk_records").upsert(payload, on_conflict="id").execute()
        
        print("✅ Синхронизация успешно завершена!")
        
    except Exception as e:
        print(f"Произошла ошибка во время выполнения скрипта: {e}")

if __name__ == "__main__":
    sync_talk_to_supabase()
