import os
import requests
from supabase import create_client, Client

# --- НАСТРОЙКИ КОНТУР.ТОЛК ---
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
    headers = {
        "X-Auth-Token": TALK_API_KEY,
        "Accept": "application/json"
    }
    
    # Список возможных комбинаций путей, проверяем их на наличие ключа 'entities'
    possible_endpoints = [
        "https://portalwash.ktalk.ru/api/portalwash/recordings/v2",
        "https://portalwash.ktalk.ru/api/v1/recordings",
        "https://portalwash.ktalk.ru/api/recordings/v2",
        "https://api.ktalk.ru/v1/public/records"
    ]
    
    response = None
    working_url = None
    data = None
    
    print("🤖 Запуск сканирования эндпоинтов по официальной структуре v2...")
    
    for url in possible_endpoints:
        print(f"Проверка: {url} ... ", end="")
        try:
            res = requests.get(url, headers=headers)
            print(f"Статус: {res.status_code}")
            
            if res.status_code == 200:
                # Проверяем, что это JSON и внутри есть 'entities' из документации
                try:
                    json_data = res.json()
                    if isinstance(json_data, dict) and "entities" in json_data:
                        response = res
                        data = json_data
                        working_url = url
                        print(f"🎯 РАБОЧИЙ ЭНДПОИНТ НАЙДЕН: {url}")
                        break
                except:
                    print("❌ Ответ — не JSON")
        except Exception as e:
            print(f"Ошибка: {e}")
            
    if not data:
        print("\n🛑 Не удалось получить JSON со структурой 'entities'.")
        print("Проверьте, пожалуйста, точный адрес в документации или кабинете Толка.")
        return

    # Извлекаем записи по верному ключу 'entities'
    records = data.get("entities", [])
    print(f"Всего записей на странице от API: {len(records)}")
    
    target_emails_lower = [email.lower() for email in TARGET_EMAILS]
    payload = []
    
    for record in records:
        if not isinstance(record, dict):
            continue
            
        # Строго по структуре: createdBy -> email
        created_by = record.get("createdBy", {})
        owner_email = ""
        if isinstance(created_by, dict):
            owner_email = created_by.get("email") or ""
            
        owner_email = str(owner_email).lower()
        
        # Фильтруем по вашим 3 менеджерам
        if owner_email in target_emails_lower:
            # Собираем ссылку на просмотр. Если в структуре нет url, 
            # формируем стандартную ссылку на запись внутри вашего пространства:
            record_id = record.get("id")
            view_url = f"https://portalwash.ktalk.ru/recordings/{record_id}"
            
            payload.append({
                "id": str(record_id),
                "name": record.get("title") or "Встреча без названия",
                "created_at": record.get("createdDate"),
                "manager_email": owner_email,
                "view_url": view_url
            })
    
    if not payload:
        print(f"ℹ️ Подключение успешно, но звонков от нужных менеджеров в списке 'entities' нет.")
        return

    print(f"🚀 Найдено {len(payload)} записей менеджеров. Отправка в Supabase...")
    result = supabase.table("talk_records").upsert(payload, on_conflict="id").execute()
    print("✅ ВСЕ ДАННЫЕ УСПЕШНО ЗАПИСАНЫ В SUPABASE!")

if __name__ == "__main__":
    sync_talk_to_supabase()
