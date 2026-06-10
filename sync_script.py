import os
import requests
from supabase import create_client, Client

# --- НАСТРОЙКИ КОНТУР.ТОЛК ---
# Официальный публичный эндпоинт для работы с записями в вашем пространстве
TALK_API_URL = "https://portalwash.ktalk.ru/api/v1/public/records"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

# Список почт менеджеров, чьи звонки мы собираем
TARGET_EMAILS = [
    "a.belikov@portalwash.ru",
    "e.zhuravlev@portalwash.ru",
    "n.kiselyov@portalwash.ru"
]

# --- НАСТРОЙКИ SUPABASE ---
# Ваш зафиксированный URL проекта
SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 

# Секретный ключ автоматически подтягивается из GitHub Secrets (переменная SUPABASE_SERVICE_KEY)
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_KEY:
    print("🛑 Ошибка: Секретный ключ SUPABASE_SERVICE_KEY не найден в GitHub Secrets!")
    exit(1)

# Инициализация клиента Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def sync_talk_to_supabase():
    headers = {
        "X-Auth-Token": TALK_API_KEY,
        "Accept": "application/json"
    }
    
    # Список возможных эндпоинтов для On-Premise / корпоративных версий Толка
    possible_urls = [
        "https://portalwash.ktalk.ru/api/v1/records",
        "https://portalwash.ktalk.ru/api/v1/public/records",
        "https://api.ktalk.ru/v1/public/records"
    ]
    
    response = None
    working_url = None
    
    # Перебираем адреса, пока не найдем рабочий (который вернет код 200)
    for url in possible_urls:
        print(f"Проверяем адрес API: {url}...")
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                response = res
                working_url = url
                print(f"🎯 Найдено рабочее API! Ответил адрес: {url}")
                break
            else:
                print(f"❌ Мимо (Код {res.status_code})")
        except Exception as e:
            print(f"❌ Ошибка подключения к {url}: {e}")
            
    if not response:
        print("🛑 Ни один из стандартных адресов API Контур.Толка не подошел (везде 404 или ошибки доступа).")
        return

    # Разбираем успешный ответ
    try:
        data = response.json()
    except Exception as json_err:
        print(f"🛑 Не удалось прочитать JSON. Ответ сервера: {response.text}")
        return

    records = data.get('items', data) if isinstance(data, dict) else data
    
    if not isinstance(records, list):
        # Если Толк вернул объект, где записи лежат в другом месте
        if isinstance(data, dict) and 'data' in data:
            records = data['data']
        else:
            print(f"🛑 Структура ответа не распознана как список. Ответ: {data}")
            return
            
    target_emails_lower = [email.lower() for email in TARGET_EMAILS]
    
    payload = []
    for record in records:
        if not isinstance(record, dict):
            continue
            
        owner = record.get('owner', {})
        owner_email = owner.get('email', '').lower()
        
        if owner_email in target_emails_lower:
            payload.append({
                "id": record.get("id"),
                "name": record.get("name", "Встреча без названия"),
                "created_at": record.get("createdAt"),
                "manager_email": owner_email,
                "view_url": record.get("url") or record.get("viewUrl")
            })
    
    if not payload:
        print("ℹ️ Синхронизация выполнена успешно, но свежих записей от указанных менеджеров не найдено.")
        return

    print(f"🚀 Найдено {len(payload)} записей. Отправка в Supabase...")
    result = supabase.table("talk_records").upsert(payload, on_conflict="id").execute()
    print("✅ Все данные успешно записаны в Supabase!")

if __name__ == "__main__":
    sync_talk_to_supabase()
    sync_talk_to_supabase()
