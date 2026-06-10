import os
import requests
from supabase import create_client, Client

# --- НАСТРОЙКИ КОНТУР.ТОЛК ---
# Новый эндпоинт v2 с учетом имени вашего домена portalwash
TALK_API_URL = "https://portalwash.ktalk.ru/api/portalwash/recordings/v2"
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
    print(f"Запрос данных из Контур.Толк по новому API v2: {TALK_API_URL}...")
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
            print(f"🛑 Ответ сервера не является JSON. Текст ответа: {response.text[:300]}")
            return

        # В API v2 список записей обычно возвращается в ключе 'recordings' или 'items'
        records = []
        if isinstance(data, dict):
            records = data.get('recordings') or data.get('items') or data.get('data') or []
        elif isinstance(data, list):
            records = data

        if not records and isinstance(data, dict):
            # Проверяем, вдруг записи пришли в корневом объекте без обертки в массив
            if 'id' in data:
                records = [data]

        if not records:
            print(f"ℹ️ Ответ от API получен успешно, но список записей пуст. Ответ: {data}")
            return
            
        target_emails_lower = [email.lower() for email in TARGET_EMAILS]
        payload = []
        
        for record in records:
            if not isinstance(record, dict):
                continue
                
            # Ищем почту создателя записи в API v2
            # Проверяем вложенный объект owner -> email или напрямую поле ownerEmail / creatorEmail
            owner = record.get('owner', {})
            owner_email = ""
            if isinstance(owner, dict):
                owner_email = owner.get('email') or owner.get('username') or ""
            
            if not owner_email:
                owner_email = record.get('ownerEmail') or record.get('creatorEmail') or ""
                
            owner_email = str(owner_email).lower()
            
            # Проверяем, принадлежит ли звонок одному из наших менеджеров
            if owner_email in target_emails_lower:
                payload.append({
                    "id": str(record.get("id")),
                    "name": record.get("name") or record.get("title") or "Встреча без названия",
                    "created_at": record.get("createdAt") or record.get("startedAt") or record.get("date"),
                    "manager_email": owner_email,
                    "view_url": record.get("url") or record.get("viewUrl") or record.get("downloadUrl")
                })
        
        if not payload:
            print("ℹ️ Записи успешно получены, но звонков от Беликова, Журавлева или Киселёва среди них не обнаружено.")
            return

        print(f"🚀 Найдено {len(payload)} актуальных записей. Отправка в Supabase...")
        result = supabase.table("talk_records").upsert(payload, on_conflict="id").execute()
        print("✅ Все данные успешно записаны в Supabase!")

    except Exception as e:
        print(f"🛑 Системная ошибка выполнения: {e}")

if __name__ == "__main__":
    sync_talk_to_supabase()
