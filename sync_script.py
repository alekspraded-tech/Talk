import os
import requests
from datetime import datetime, timedelta
from supabase import create_client, Client

# --- НАСТРОЙКИ КОНТУР.ТОЛК ---
TALK_API_URL = "https://portalwash.ktalk.ru/api/Domain/recordings/v2"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

MANAGERS = {
    "45cd0d96-9fb7-40db-88bf-e1350dc28fe1": {"name": "Алексей Беликов", "email": "a.belikov@portalwash.ru"},
    "3ae59251-f4b6-4b38-9cda-ef6a56cc7127": {"name": "Евгений Журавлев", "email": "e.zhuravlev@portalwash.ru"},
    "01c7dc8e-b715-470e-9766-43c8363a2760": {"name": "Николай Киселев", "email": "n.kiselyov@portalwash.ru"}
}

# --- НАСТРОЙКИ SUPABASE ---
SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_KEY:
    print("🛑 Ошибка: Ключ SUPABASE_SERVICE_KEY не найден в GitHub Secrets!")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ОСНОВНОЙ СКРИПТ ВЫГРУЗКИ (30 ДНЕЙ) ---
print("🤖 Запуск глубокой синхронизации записей за последние 30 дней...")

# Вычисляем дедлайн (текущая дата минус 30 дней)
date_limit = datetime.utcnow() - timedelta(days=30)
print(f"📅 Ищем встречи, начиная с: {date_limit.strftime('%Y-%m-%d %H:%M:%S')} UTC")

headers = {
    "X-Auth-Token": TALK_API_KEY,
    "Accept": "application/json"
}

payload = []
page = 1
page_size = 30
has_more = True

try:
    while has_more:
        print(f"📦 Запрашиваем страницу {page}...")
        
        # Передаем параметры страницы в API Контура
        params = {
            "page": page,
            "size": page_size
        }
        
        response = requests.get(TALK_API_URL, headers=headers, params=params)
        if response.status_code != 200:
            print(f"🛑 Ошибка Толка: Код {response.status_code}")
            break

        data = response.json()
        records = data.get("entities", [])
        
        if not records:
            print("-> Больше записей в API нет.")
            break
            
        print(f"-> На странице найдено {len(records)} записей. Анализируем...")
        
        reached_end_of_period = False
        
        for record in records:
            if not isinstance(record, dict):
                continue
                
            # Проверяем дату создания встречи
            created_date_str = record.get("createdDate")
            if not created_date_str:
                continue
                
            # Парсим дату (убираем 'Z' для корректной работы в Python)
            clean_date_str = created_date_str.replace("Z", "")
            # Берем только основную часть времени без микросекунд, если они есть
            clean_date_str = clean_date_str.split(".")[0]
            
            try:
                record_date = datetime.strptime(clean_date_str, "%Y-%m-%dT%H:%M:%S")
            except Exception as parse_err:
                # На случай другого формата даты
                continue
                
            # Если запись старше 30 дней — останавливаем весь цикл пагинации
            if record_date < date_limit:
                print(f"⏳ Дошли до старых записей от {record_date}. Прекращаем поиск.")
                reached_end_of_period = True
                break
                
            # Если дата подходит, проверяем менеджера
            created_by = record.get("createdBy", {}) or {}
            user_id = created_by.get("login")
            
            if user_id in MANAGERS:
                record_id = record.get("id")
                view_url = f"https://portalwash.ktalk.ru/recordings/{record_id}"
                manager_info = MANAGERS[user_id]
                
                payload.append({
                    "id": str(record_id),
                    "name": record.get("title") or "Встреча без названия",
                    "created_at": created_date_str,
                    "manager_email": manager_info["email"],
                    "view_url": view_url
                })

        if reached_end_of_period:
            break
            
        # Переходим на следующую страницу
        page += 1
        
    # --- ОТПРАВКА В БАЗУ ДАННЫХ ---
    if not payload:
        print("ℹ️ За последние 30 дней встреч выбранных менеджеров не найдено.")
    else:
        # Исключаем дубликаты комнат
        unique_payload = {item["id"]: item for item in payload}.values()
        unique_payload = list(unique_payload)
        
        print(f"🚀 Всего найдено звонков за 30 дней: {len(unique_payload)} (уникальных). Запись в Supabase...")
        result = supabase.table("talk_records").upsert(unique_payload, on_conflict="id").execute()
        print("✅ База данных успешно наполнена архивом звонков!")
        
except Exception as e:
    print(f"🛑 Системная ошибка: {e}")
