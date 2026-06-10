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
    print(f"Получение данных из Контур.Толк по адресу: {TALK_API_URL}...")
    headers = {
        "X-Auth-Token": TALK_API_KEY,
        "Accept": "application/json"
    }
    
    try:
        # Делаем запрос к API Толка
        response = requests.get(TALK_API_URL, headers=headers)
        
        # Если Толк вернул ошибку (например, 401, 403, 404), выводим её текст в логи
        if response.status_code != 200:
            print(f"🛑 Сервер Толка вернул ошибку {response.status_code}!")
            print(f"Ответ сервера: {response.text}")
            return

        # Безопасно парсим JSON-ответ
        try:
            data = response.json()
        except Exception as json_err:
            print(f"🛑 Не удалось прочитать JSON. Ответ сервера: {response.text}")
            return

        # Извлекаем список записей (он может лежать внутри ключа 'items' или в корне массива)
        records = data.get('items', data) if isinstance(data, dict) else data
        
        # Приводим целевые email к нижнему регистру для точного сравнения
        target_emails_lower = [email.lower() for email in TARGET_EMAILS]
        
        payload = []
        for record in records:
            owner = record.get('owner', {})
            owner_email = owner.get('email', '').lower()
            
            # Фильтруем записи: оставляем только наших менеджеров
            if owner_email in target_emails_lower:
                payload.append({
                    "id": record.get("id"),
                    "name": record.get("name", "Встреча без названия"),
                    "created_at": record.get("createdAt"),
                    "manager_email": owner_email,
                    "view_url": record.get("url") or record.get("viewUrl")
                })
        
        if not payload:
            print("ℹ️ На этой странице API Толка новых записей от указанных менеджеров не найдено.")
            return

        print(f"🚀 Найдено {len(payload)} записей. Отправка в Supabase...")
        
        # Запись в Supabase (UPSERT обновляет существующие ID звонков и добавляет новые)
        result = supabase.table("talk_records").upsert(payload, on_conflict="id").execute()
        print("✅ Синхронизация успешно завершена!")
        
    except Exception as e:
        print(f"🛑 Произошла системная ошибка во время выполнения: {e}")

if __name__ == "__main__":
    sync_talk_to_supabase()
