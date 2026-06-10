import os
import requests
from supabase import create_client, Client

# --- НАСТРОЙКИ КОНТУР.ТОЛК ---
# Корректный эндпоинт для выгрузки записей в On-Premise пространстве
TALK_API_URL = "https://portalwash.ktalk.ru/api/v1/conference_records"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

TARGET_EMAILS = [
    "a.belikov@portalwash.ru",
    "e.zhuravlev@portalwash.ru",
    "n.kiselyov@portalwash.ru"
]

# --- НАСТРОЙКИ SUPABASE ---
SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_KEY:
    print("🛑 Ошибка: Секретный ключ SUPABASE_SERVICE_KEY не найден в GitHub Secrets!")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def sync_talk_to_supabase():
    print(f"Запрос данных из Контур.Толк: {TALK_API_URL}...")
    headers = {
        "X-Auth-Token": TALK_API_KEY,
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(TALK_API_URL, headers=headers)
        
        if response.status_code != 200:
            print(f"🛑 Сервер Толка вернул ошибку {response.status_code}!")
            print(f"Ответ сервера: {response.text[:500]}")
            return

        try:
            data = response.json()
        except Exception as json_err:
            print(f"🛑 Ответ сервера не является JSON. Первые 300 символов: {response.text[:300]}")
            return

        # Записи в On-Premise обычно лежат в ключе 'conferenceRecords' или 'items'
        if isinstance(data, dict):
            records = data.get('conferenceRecords') or data.get('items') or data.get('data') or []
        else:
            records = data if isinstance(data, list) else []
            
        if not records and isinstance(data, dict):
            # Если вернулся массив сразу в корне объекта
            records = [data] if 'id' in data else []

        if not records:
            print(f"ℹ️ Прочитали JSON, но список записей пуст. Ответ API: {data}")
            return
            
        target_emails_lower = [email.lower() for email in TARGET_EMAILS]
        payload = []
        
        for record in records:
            if not isinstance(record, dict):
                continue
                
            # Проверяем владельца (в зависимости от версии API структура может быть owner -> email)
            owner = record.get('owner', {})
            owner_email = owner.get('email', '') if isinstance(owner, dict) else record.get('ownerEmail', '')
            owner_email = str(owner_email).lower()
            
            if owner_email in target_emails_lower:
                payload.append({
                    "id": str(record.get("id")),
                    "name": record.get("name") or record.get("title") or "Встреча без названия",
                    "created_at": record.get("createdAt") or record.get("startedAt"),
                    "manager_email": owner_email,
                    "view_url": record.get("url") or record.get("viewUrl") or record.get("downloadUrl")
                })
        
        if not payload:
            print("ℹ️ Синхронизация успешна, но звонков от Беликова, Журавлева или Киселёва в этом ответе нет.")
            return

        print(f"🚀 Найдено {len(payload)} записей. Отправка в Supabase...")
        result = supabase.table("talk_records").upsert(payload, on_conflict="id").execute()
        print("✅ Все данные успешно записаны в Supabase!")

    except Exception as e:
        print(f"🛑 Системная ошибка выполнения: {e}")

if __name__ == "__main__":
    sync_talk_to_supabase()
